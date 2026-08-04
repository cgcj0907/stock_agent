"""point-in-time 数据快照：回测防前视偏差（docs/01-design.md §9.1）。"""
from __future__ import annotations

from datetime import datetime, timezone

from value_agent.data.storage.base import MarketStorage

_TABLES = ("financials", "daily_price", "valuation_history", "dividends")


def create_snapshot(
    storage: MarketStorage, code: str, as_of: str | None = None
) -> dict:
    """生成某公司在 as_of（YYYYMMDD，含）时的数据快照。

    as_of=None 表示当前全部数据（生成快照时刻）。
    快照内容：{code, as_of, created_at, tables: {table: [records]}}
    """
    snapshot = {
        "code": code,
        "as_of": as_of,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
    }
    for table in _TABLES:
        snapshot["tables"][table] = storage.records_before(table, code, as_of)
    return snapshot


def snapshot_summary(snapshot: dict) -> dict:
    return {
        "code": snapshot["code"],
        "as_of": snapshot["as_of"],
        "counts": {t: len(recs) for t, recs in snapshot["tables"].items()},
    }
