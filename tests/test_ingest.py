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


def test_ingest_company_writes_all_six_tables(tmp_path):
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    n = ingest_company(storage, MockDataSource(), "600519")

    assert n == 1 + 10 + 2 + 2 + 2 + 1  # 基本信息1 + 财务10 + 行情2 + 估值2 + 分红2 + 治理事件1（6.1）
    assert len(storage.records_before("company", "600519")) == 1
    assert len(storage.records_before("financials", "600519")) == 10
    assert len(storage.records_before("daily_price", "600519")) == 2
    assert len(storage.records_before("valuation_history", "600519")) == 2
    assert len(storage.records_before("dividends", "600519")) == 2
    assert len(storage.records_before("governance_events", "600519")) == 1


def test_ingest_company_filters_invalid_records(tmp_path):
    storage = SqliteMarketStorage(str(tmp_path / "market.db"))
    n = ingest_company(storage, _BadFinancialsSource(), "600519")

    # 无效财务记录被剔除：财务只写入 10 条有效记录（含治理事件共 18）
    assert n == 1 + 10 + 2 + 2 + 2 + 1
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
