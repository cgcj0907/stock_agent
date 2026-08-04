"""数据管理器：存储优先（Supabase/SQLite），缺失时回退实时数据源。

- 本地/部署：优先读已入库数据（快、稳定、海外可用）
- 未入库或库为空：回退实时源（BaoStock/AkShare/mock）
- 组合源：分红走 AkShare 巨潮（见 sources/combined.py）
"""
from __future__ import annotations

import logging

from value_agent.core.config import load_settings

from .sources.base import DataSource
from .sources.mock_source import MockDataSource

logger = logging.getLogger(__name__)

_TABLES = ("company", "financials", "daily_price", "valuation_history", "dividends")


def _default_source() -> DataSource:
    """按 settings 依次尝试数据源：primary → fallback → mock，并叠加组合分红。"""
    settings = load_settings()
    order: list[str] = [settings.get("data_sources", {}).get("primary", "mock")]
    order += list(settings.get("data_sources", {}).get("fallback", ["akshare", "mock"]))
    seen: set[str] = set()
    base: DataSource | None = None
    for name in order:
        if name in seen:
            continue
        seen.add(name)
        try:
            if name == "baostock":
                from .sources.baostock_source import BaoStockDataSource

                base = BaoStockDataSource()
            elif name == "akshare":
                from .sources.akshare_source import AkShareDataSource

                base = AkShareDataSource()
            elif name == "mock":
                base = MockDataSource()
            if base is not None:
                break
        except Exception as exc:  # noqa: BLE001
            logger.warning("数据源 %s 不可用：%s", name, exc)
    if base is None:
        raise RuntimeError("没有可用数据源")
    try:
        from .sources.akshare_source import AkShareDataSource
        from .sources.combined import CombinedDataSource

        return CombinedDataSource(base, overrides={"dividends": AkShareDataSource()})
    except Exception as exc:  # noqa: BLE001
        logger.warning("AkShare 分红不可用，仅用 %s：%s", base.name, exc)
        return base


class DataManager:
    def __init__(self, source: DataSource | None = None, market_storage=None) -> None:
        self._source = source if source is not None else _default_source()
        self._storage = market_storage
        if self._storage is None:
            try:
                from .storage.factory import create_storage

                self._storage = create_storage(load_settings())
            except Exception as exc:  # noqa: BLE001
                logger.warning("市场存储不可用（回退实时源）：%s", exc)
                self._storage = None
        self._cache: dict[str, dict] = {}

    @property
    def source(self) -> DataSource:
        return self._source

    @property
    def storage(self):
        return self._storage

    def _stored(self, table: str, code: str):
        """优先读存储；无存储/无数据返回 None。"""
        if self._storage is None:
            return None
        try:
            recs = self._storage.records_before(table, code)
            return recs or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("读 %s/%s 失败（回退实时源）：%s", table, code, exc)
            return None

    def _cached(self, key: str, fetcher):
        if key not in self._cache:
            self._cache[key] = fetcher()
        return self._cache[key]

    def company_info(self, code: str) -> dict:
        recs = self._stored("company", code)
        if recs:
            r = recs[0]
            return {k: r.get(k) for k in ("code", "ts_code", "name", "industry", "list_date")}
        return self._cached(f"info:{code}", lambda: self._source.company_info(code))

    def financials(self, code: str, years: int = 10) -> dict:
        recs = self._stored("financials", code)
        if recs is not None:
            return {"records": recs, "source": f"storage({self._storage.name})"}
        return self._cached(f"fin:{code}:{years}", lambda: self._source.financials(code, years))

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        recs = self._stored("daily_price", code)
        if recs is not None:
            return {"records": recs, "source": f"storage({self._storage.name})"}
        return self._cached(
            f"price:{code}:{start}:{end}",
            lambda: self._source.daily_prices(code, start, end),
        )

    def valuation_history(self, code: str) -> dict:
        recs = self._stored("valuation_history", code)
        if recs is not None:
            return {"records": recs, "source": f"storage({self._storage.name})"}
        return self._cached(f"val:{code}", lambda: self._source.valuation_history(code))

    def dividends(self, code: str) -> dict:
        recs = self._stored("dividends", code)
        if recs is not None:
            return {"records": recs, "source": f"storage({self._storage.name})"}
        return self._cached(f"div:{code}", lambda: self._source.dividends(code))
