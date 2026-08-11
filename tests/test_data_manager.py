"""DataManager 读穿缓存测试：存储缺失 → 实时源拉取 + 后台回写存储。"""
from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from value_agent.data.manager import DataManager
from value_agent.data.sources.mock_source import MockDataSource
from value_agent.data.storage.sqlite_storage import SqliteMarketStorage


class _RecordingSource(MockDataSource):
    """记录实时源被调用的次数（验证存储命中时不再拉取）。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls: dict[str, int] = {"company_info": 0, "financials": 0}

    def company_info(self, code: str) -> dict:
        self.calls["company_info"] += 1
        return super().company_info(code)

    def financials(self, code: str, years: int = 10) -> dict:
        self.calls["financials"] += 1
        return super().financials(code, years)


def _wait_until(pred, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _storage_factory(db) -> Callable:
    return lambda: SqliteMarketStorage(str(db))


def test_miss_fetches_from_source_and_writes_back(tmp_path):
    db = tmp_path / "cache.db"
    storage = SqliteMarketStorage(str(db))
    source = _RecordingSource()
    dm = DataManager(
        source=source, market_storage=storage, storage_factory=_storage_factory(db)
    )

    info = dm.company_info("600519")
    assert info["name"] == "示例公司600519"  # 存储缺失 → 实时源
    assert source.calls["company_info"] == 1
    # 后台回写完成后，存储里应有该公司
    assert _wait_until(lambda: bool(storage.records_before("company", "600519")))
    assert storage.records_before("company", "600519")[0]["name"] == "示例公司600519"

    fin = dm.financials("600519")
    assert len(fin["records"]) == 10
    assert _wait_until(lambda: len(storage.records_before("financials", "600519")) == 10)


def test_storage_hit_skips_source(tmp_path):
    db = tmp_path / "hit.db"
    storage = SqliteMarketStorage(str(db))
    storage.upsert("company", "600519", [
        {"code": "600519", "name": "库里公司", "industry": "白酒", "list_date": "20010101"},
    ])
    source = _RecordingSource()
    dm = DataManager(
        source=source, market_storage=storage, storage_factory=_storage_factory(db)
    )

    info = dm.company_info("600519")
    assert info["name"] == "库里公司"
    assert source.calls["company_info"] == 0  # 存储命中，不碰实时源


def test_write_back_failure_does_not_break_read(tmp_path):
    storage = SqliteMarketStorage(str(tmp_path / "x.db"))

    def broken_factory():
        raise RuntimeError("db down")

    dm = DataManager(
        source=MockDataSource(), market_storage=storage, storage_factory=broken_factory
    )
    info = dm.company_info("600519")
    assert info["name"]  # 回写失败也不影响本次返回


class _FlakySource(MockDataSource):
    """前 N 次调用抛瞬时断连，之后恢复正常（模拟 AkShare 网络抖动）。"""

    def __init__(self, fails: int = 2) -> None:
        super().__init__()
        self.fails = fails
        self.calls = 0

    def financials(self, code: str, years: int = 10) -> dict:
        self.calls += 1
        if self.calls <= self.fails:
            raise ConnectionError("RemoteDisconnected")
        return super().financials(code, years)


def test_transient_source_failure_retries(tmp_path):
    """实时源瞬时断连应自动重试，成功后再正常返回并后台回写。"""
    db = tmp_path / "retry.db"
    storage = SqliteMarketStorage(str(db))
    source = _FlakySource(fails=2)
    dm = DataManager(
        source=source, market_storage=storage, storage_factory=_storage_factory(db)
    )
    fin = dm.financials("600519")
    assert len(fin["records"]) == 10
    assert source.calls == 3  # 2 次失败 + 1 次成功
    assert _wait_until(lambda: len(storage.records_before("financials", "600519")) == 10)


def test_persistent_source_failure_raises(tmp_path):
    """持续失败时重试耗尽仍向上抛异常（由模块降级处理，不静默返回空）。"""
    db = tmp_path / "fail.db"
    storage = SqliteMarketStorage(str(db))
    source = _FlakySource(fails=999)
    dm = DataManager(
        source=source, market_storage=storage, storage_factory=_storage_factory(db)
    )
    import pytest

    with pytest.raises(ConnectionError):
        dm.financials("600519")
    assert source.calls == 3  # 重试 3 次后放弃


def test_sync_write_back_writes_before_return(monkeypatch, tmp_path):
    """DATA_WRITE_BACK=sync 时，写入在返回前同步完成（serverless 友好）。"""
    monkeypatch.setenv("DATA_WRITE_BACK", "sync")
    db = tmp_path / "sync.db"
    storage = SqliteMarketStorage(str(db))
    dm = DataManager(
        source=MockDataSource(), market_storage=storage, storage_factory=_storage_factory(db)
    )
    dm.company_info("600519")
    assert storage.records_before("company", "600519"), "同步模式返回前应已写入"


def test_daily_prices_incremental_refresh_only_fetches_new(tmp_path):
    """缓存命中时增量刷新：只拉最新日期之后的数据、只写新增；一次分析只拉一次。"""
    db = tmp_path / "inc.db"
    storage = SqliteMarketStorage(str(db))
    storage.upsert("daily_price", "600519", [
        {"code": "600519", "trade_date": "20240101", "open": 10.0, "close": 11.0, "high": 12.0, "low": 9.0, "volume": 100.0},
    ])
    calls = {"n": 0}

    class _IncSource(MockDataSource):
        def daily_prices(self, code, start=None, end=None):
            calls["n"] += 1
            return {"records": [
                {"trade_date": start, "open": 11.0, "close": 12.0, "high": 13.0, "low": 10.0, "volume": 200.0},
            ]}

    dm = DataManager(
        source=_IncSource(), market_storage=storage, storage_factory=_storage_factory(db)
    )
    d = dm.daily_prices("600519")
    assert [r["trade_date"] for r in d["records"]] == ["20240101", "20240102"], "旧+新合并"
    assert calls["n"] == 1, "只拉一次增量（从 20240102 开始）"
    assert _wait_until(lambda: len(storage.records_before("daily_price", "600519")) == 2), "新增已回写"
    # 同进程第二次调用命中合并缓存，不再拉取
    dm.daily_prices("600519")
    assert calls["n"] == 1


def test_postgres_storage_reconnects_after_stale_connection(monkeypatch):
    """生产稽核回归：pooler 静默断开（SSL EOF）后，下一次读取自动重连而非无限阻塞。

    M7 卡「价格与估值分位」根因之一：单连接被断开后无重连，后续读取永久挂起。
    """
    import psycopg2

    from value_agent.data.storage.postgres_storage import PostgresMarketStorage

    state = {"connect": 0, "select": 0}

    class _FakeCursor:
        def __init__(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            if sql.lstrip().startswith("SELECT"):
                state["select"] += 1
                if state["select"] == 1:
                    raise psycopg2.OperationalError("SSL SYSCALL error: EOF detected")

        def fetchone(self):
            return ("20260801",)

        def fetchall(self):
            return []

    class _FakeConn:
        closed = False
        autocommit = True

        def __init__(self):
            state["connect"] += 1

        def cursor(self):
            return _FakeCursor()

        def close(self):
            self.closed = True

    monkeypatch.setattr(PostgresMarketStorage, "_connect", lambda self: _FakeConn())
    st = PostgresMarketStorage("postgresql://fake")
    # 第一次 SELECT 触发 OperationalError → 重连（_connect 第 2 次）后重试成功
    assert st.latest("valuation_history", "600519") == "20260801"
    assert state["connect"] == 2, "断线后应自动重连一次"


def test_postgres_upsert_does_not_mask_error_with_set_session(monkeypatch):
    """生产稽核回归：financials 缺 bvps 列时 upsert 应把原始 ProgrammingError
    （column "bvps" does not exist）抛给上层，而不是被 finally 里的
    "set_session cannot be used inside a transaction" 掩盖。"""
    import psycopg2

    from value_agent.data.storage.postgres_storage import PostgresMarketStorage

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            # DDL / 迁移在 __init__ 里跑（no-op），只模拟 INSERT 报缺列
            if sql.lstrip().upper().startswith("INSERT"):
                raise psycopg2.ProgrammingError('column "bvps" does not exist')

        def executemany(self, sql, rows):
            self.execute(sql)

    class _FakeConn:
        closed = False

        def __init__(self):
            self._autocommit = True
            self._txn = False
            self.rollbacks = 0

        @property
        def autocommit(self):
            return self._autocommit

        @autocommit.setter
        def autocommit(self, value):
            # 模拟 psycopg2：事务未结束时切 autocommit 会抛 set_session 错误
            if value and self._txn:
                raise psycopg2.ProgrammingError(
                    "set_session cannot be used inside a transaction"
                )
            self._autocommit = value
            self._txn = not value

        def rollback(self):
            self._txn = False
            self.rollbacks += 1

        def cursor(self):
            return _FakeCursor()

        def close(self):
            self.closed = True

    monkeypatch.setattr(PostgresMarketStorage, "_connect", lambda self: _FakeConn())
    st = PostgresMarketStorage("postgresql://fake")
    with pytest.raises(psycopg2.ProgrammingError, match="bvps"):
        st.upsert("financials", "600519", [
            {"period": "20231231", "roe": 18.0, "eps": 5.0, "bvps": 30.0},
        ])
    # 修复后：finally 先 rollback 清事务再复位 autocommit，原始异常不被掩盖
    assert st._conn.rollbacks >= 1, "应先 rollback 再复位 autocommit"
    assert st._conn.autocommit is True, "autocommit 应复位为 True"
