"""DataManager 读穿缓存测试：存储缺失 → 实时源拉取 + 后台回写存储。"""
from __future__ import annotations

import time
from typing import Callable

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
