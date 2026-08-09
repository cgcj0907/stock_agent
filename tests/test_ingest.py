"""ETL 管线测试：ingest_company 全量入库 + daily_update 每日增量（只写新增行）。

覆盖 src/value_agent/data/pipelines/ingest.py（此前无任何测试）：
- 全量入库 5 张表并做勾稽校验（无效记录剔除）；
- 每日增量只 upsert 比本地最新日期更新的行，无新增时跳过。
"""
from __future__ import annotations

from value_agent.data.pipelines.ingest import daily_update, ingest_company
from value_agent.data.sources.mock_source import MockDataSource
from value_agent.data.storage.sqlite_storage import SqliteMarketStorage


class _BadFinancialsSource(MockDataSource):
    """财务数据里混入一条无效记录（period 非法），应被勾稽校验剔除。"""

    def financials(self, code: str, years: int = 10) -> dict:
        out = super().financials(code, years)
        out["records"].append({"period": "BAD", "roe": 1.0, "grossprofit_margin": 1.0})
        return out


def test_ingest_company_writes_all_eight_tables(tmp_path):
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    n = ingest_company(storage, MockDataSource(), "600519")

    assert n == 1 + 10 + 2 + 2 + 2 + 1 + 20 + 20  # 基本信息1+财务10+行情2+估值2+分红2+治理1+北向20+两融20
    assert len(storage.records_before("company", "600519")) == 1
    assert len(storage.records_before("financials", "600519")) == 10
    assert len(storage.records_before("daily_price", "600519")) == 2
    assert len(storage.records_before("valuation_history", "600519")) == 2
    assert len(storage.records_before("dividends", "600519")) == 2
    assert len(storage.records_before("governance_events", "600519")) == 1
    assert len(storage.records_before("northbound", "600519")) == 20
    assert len(storage.records_before("margin", "600519")) == 20


def test_ingest_company_filters_invalid_records(tmp_path):
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    n = ingest_company(storage, _BadFinancialsSource(), "600519")

    # 无效财务记录被剔除：财务只写入 10 条有效记录（含治理/北向/两融共 58）
    assert n == 1 + 10 + 2 + 2 + 2 + 1 + 20 + 20
    assert len(storage.records_before("financials", "600519")) == 10


def test_daily_update_only_upserts_rows_newer_than_latest(tmp_path):
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    # 本地已有截至 20260731 的数据 → 增量只应写 20260803 的行情/估值
    storage.upsert("daily_price", "600519", [
        {"trade_date": "20260731", "open": 99.5, "close": 100.0, "high": 101.0, "low": 98.5, "volume": 1_000_000},
    ])
    storage.upsert("valuation_history", "600519", [
        {"trade_date": "20260731", "pe": 22.0, "pe_ttm": 21.0, "pb": 3.1},
    ])

    stats = daily_update(storage, MockDataSource(), ["600519"])

    assert stats == {"daily_price": 1, "valuation_history": 1, "skipped": 0}
    prices = storage.records_before("daily_price", "600519")
    assert sorted(r["trade_date"] for r in prices) == ["20260731", "20260803"]
    valuations = storage.records_before("valuation_history", "600519")
    assert sorted(r["trade_date"] for r in valuations) == ["20260731", "20260803"]


def test_daily_update_skips_when_nothing_new(tmp_path):
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    # 本地已是最新（20260803 已入库）→ 无新增，应跳过
    storage.upsert("daily_price", "600519", [
        {"trade_date": "20260803", "open": 100.2, "close": 101.5, "high": 102.0, "low": 99.8, "volume": 1_200_000},
    ])
    storage.upsert("valuation_history", "600519", [
        {"trade_date": "20260803", "pe": 22.4, "pe_ttm": 21.3, "pb": 3.2},
    ])

    stats = daily_update(storage, MockDataSource(), ["600519"])

    assert stats == {"daily_price": 0, "valuation_history": 0, "skipped": 1}


def test_governance_events_table_roundtrip(tmp_path):
    """6.1：治理事件表读写（SCHEMA 自动建表 + upsert + records_before）。"""
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    n = storage.upsert("governance_events", "600519", [
        {"event_date": "20260115", "kind": "pledges", "holder": "大股东", "ratio": 0.6,
         "description": "质押 60%"},
    ])
    assert n == 1
    recs = storage.records_before("governance_events", "600519")
    assert len(recs) == 1 and recs[0]["kind"] == "pledges" and recs[0]["ratio"] == 0.6
    # 同 (code, event_date, kind) 幂等覆盖
    storage.upsert("governance_events", "600519", [
        {"event_date": "20260115", "kind": "pledges", "holder": "大股东", "ratio": 0.8,
         "description": "质押 80%"},
    ])
    assert len(storage.records_before("governance_events", "600519")) == 1
    assert storage.records_before("governance_events", "600519")[0]["ratio"] == 0.8


def test_daily_price_existing_rows_are_not_overwritten(tmp_path):
    """只追加策略：已存在的交易日保留首次入库值，新日期正常插入。"""
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    storage.upsert("daily_price", "600519", [
        {"trade_date": "20260731", "open": 99.5, "close": 100.0, "high": 101.0, "low": 98.5, "volume": 1_000_000},
    ])

    # 再次写入同一交易日（值不同）+ 一个新交易日 → 旧行应保持原值
    storage.upsert("daily_price", "600519", [
        {"trade_date": "20260731", "open": 1.0, "close": 2.0, "high": 3.0, "low": 0.5, "volume": 999},
        {"trade_date": "20260803", "open": 100.2, "close": 101.5, "high": 102.0, "low": 99.8, "volume": 1_200_000},
    ])

    rows = storage.records_before("daily_price", "600519")
    by_date = {r["trade_date"]: r for r in rows}
    assert sorted(by_date) == ["20260731", "20260803"]
    assert by_date["20260731"]["close"] == 100.0, "已存在交易日应保留首次入库值"
    assert by_date["20260803"]["close"] == 101.5, "新交易日应正常插入"


def test_valuation_history_existing_rows_are_not_overwritten(tmp_path):
    """估值历史同属只追加表：已存在交易日保留首次入库值，新日期正常插入。"""
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    storage.upsert("valuation_history", "600519", [
        {"trade_date": "20260731", "pe": 22.0, "pe_ttm": 21.0, "pb": 3.1},
    ])

    storage.upsert("valuation_history", "600519", [
        {"trade_date": "20260731", "pe": 99.0, "pe_ttm": 99.0, "pb": 99.0},
        {"trade_date": "20260803", "pe": 22.4, "pe_ttm": 21.3, "pb": 3.2},
    ])

    rows = storage.records_before("valuation_history", "600519")
    by_date = {r["trade_date"]: r for r in rows}
    assert sorted(by_date) == ["20260731", "20260803"]
    assert by_date["20260731"]["pe"] == 22.0, "已存在交易日应保留首次入库值"
    assert by_date["20260803"]["pe"] == 22.4, "新交易日应正常插入"


class _SpySource(MockDataSource):
    """记录 daily_prices / valuation_history 收到的 start，验证真增量传参。"""

    def __init__(self) -> None:
        self.daily_starts: list[str | None] = []
        self.val_starts: list[str | None] = []

    def daily_prices(self, code, start=None, end=None):
        self.daily_starts.append(start)
        return super().daily_prices(code, start, end)

    def valuation_history(self, code, start=None):
        self.val_starts.append(start)
        return super().valuation_history(code, start)


def test_daily_update_passes_incremental_start(tmp_path):
    """真增量：库里有缓存 → 给 source 传 start=最新交易日；无缓存 → 传 None（全量）。"""
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    storage.upsert("daily_price", "600519", [
        {"trade_date": "20260731", "open": 99.5, "close": 100.0, "high": 101.0, "low": 98.5, "volume": 1_000_000},
    ])
    spy = _SpySource()
    daily_update(storage, spy, ["600519"])
    assert spy.daily_starts == ["20260731"]
    assert spy.val_starts == ["20260731"]

    spy2 = _SpySource()
    daily_update(SqliteMarketStorage(str(tmp_path / "m2.db")), spy2, ["600519"])
    assert spy2.daily_starts == [None]
    assert spy2.val_starts == [None]


def test_storage_list_codes(tmp_path):
    """company 表代码枚举（daily 默认遍历这些代码）。"""
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    ingest_company(storage, MockDataSource(), "600519")
    ingest_company(storage, MockDataSource(), "000333")
    assert storage.list_codes() == sorted(["600519", "000333"])
