"""point-in-time 快照测试：as_of 不得包含未来数据。"""
import pytest

from value_agent.data.snapshots import create_snapshot
from value_agent.data.storage.sqlite_storage import SqliteMarketStorage


@pytest.fixture
def storage(tmp_path):
    return SqliteMarketStorage(str(tmp_path / "market.db"))


def test_snapshot_excludes_future_data(storage):
    storage.upsert("daily_price", "600519", [
        {"trade_date": "20260731", "close": 100.0},
        {"trade_date": "20260803", "close": 101.5},
    ])
    storage.upsert("financials", "600519", [
        {"period": "20251231", "roe": 18.0},
        {"period": "20260630", "roe": 19.0},
    ])
    snap = create_snapshot(storage, "600519", as_of="20260731")
    dates = [r["trade_date"] for r in snap["tables"]["daily_price"]]
    assert dates == ["20260731"]                      # 20260803 被排除（防前视）
    periods = [r["period"] for r in snap["tables"]["financials"]]
    assert periods == ["20251231", "20260630"]        # 20260630 ≤ 20260731，保留


def test_snapshot_without_as_of_returns_all(storage):
    storage.upsert("daily_price", "600519", [
        {"trade_date": "20260731", "close": 100.0},
        {"trade_date": "20260803", "close": 101.5},
    ])
    snap = create_snapshot(storage, "600519")
    assert len(snap["tables"]["daily_price"]) == 2
