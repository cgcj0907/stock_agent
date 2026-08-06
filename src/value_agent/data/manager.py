"""数据管理器：存储优先（Supabase/SQLite），缺失时回退实时源并后台回写。

- 本地/部署：优先读已入库数据（快、稳定、海外可用）
- 未入库或库为空：回退实时源（AkShare/mock），并把拉取结果**后台回写**进存储
  （读穿缓存：首次命中实时源，之后命中存储；回写失败只记日志，不影响本次结果）
- 组合源：分红走 AkShare 巨潮（见 sources/combined.py）
"""
from __future__ import annotations

import logging
import threading

from value_agent.core.config import load_settings

from .sources.base import DataSource
from .sources.mock_source import MockDataSource
from .sources.urls import source_url

logger = logging.getLogger(__name__)

_TABLES = ("company", "financials", "daily_price", "valuation_history", "dividends")


def _default_source() -> DataSource:
    """按 settings 依次尝试数据源：primary → fallback → mock。"""
    settings = load_settings()
    order: list[str] = [settings.get("data_sources", {}).get("primary", "mock")]
    order += list(settings.get("data_sources", {}).get("fallback", ["mock"]))
    seen: set[str] = set()
    base: DataSource | None = None
    for name in order:
        if name in seen:
            continue
        seen.add(name)
        try:
            if name == "akshare":
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
    return base


class DataManager:
    def __init__(
        self,
        source: DataSource | None = None,
        market_storage=None,
        *,
        storage_factory=None,
    ) -> None:
        """source：实时数据源；market_storage：存储实例；storage_factory：后台回写用。

        storage_factory 返回一个**独立的新存储连接**（SQLite/psycopg2 连接不可跨线程
        共享），默认与 market_storage 同源（读 settings 创建）。
        """
        self._source = source if source is not None else _default_source()
        self._storage = market_storage
        if self._storage is None:
            try:
                from .storage.factory import create_storage

                self._storage = create_storage(load_settings())
            except Exception as exc:  # noqa: BLE001
                logger.warning("市场存储不可用（回退实时源）：%s", exc)
                self._storage = None
        self._storage_factory = storage_factory or self._new_storage
        self._cache: dict[str, dict] = {}
        # 已发起回写的 (table, code)：同一进程内避免重复后台写
        self._written: set[tuple[str, str]] = set()

    @property
    def source(self) -> DataSource:
        return self._source

    @property
    def storage(self):
        return self._storage

    def _new_storage(self):
        """后台回写用的默认存储工厂：与主存储同源（同 settings/DATABASE_URL）。"""
        from .storage.factory import create_storage

        return create_storage(load_settings())

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

    def _fetch(self, table: str, code: str, key: str, fetcher) -> dict:
        """实时源拉取 + 进程内缓存 + 后台回写存储（只在真正拉取时回写一次）。"""
        if key not in self._cache:
            data = fetcher()
            self._cache[key] = data
            self._write_back(table, code, data.get("records", []))
        return self._cache[key]

    def _write_back(self, table: str, code: str, records: list[dict]) -> None:
        """存储缺失时把实时源结果后台写进存储（读穿缓存）。

        后台线程用独立存储连接，勾稽校验后 upsert；任何失败只记日志，
        绝不影响本次请求结果。同一 (table, code) 本进程内只回写一次。
        """
        if self._storage is None or not records:
            return
        key = (table, code)
        if key in self._written:
            return
        self._written.add(key)

        def _job() -> None:
            try:
                from .validate import valid_records

                st = self._storage_factory()
                try:
                    valid, report = valid_records(table, records)
                    if report.issues:
                        logger.warning(
                            "[cache] %s %s：%d/%d 条校验无效，跳过",
                            table, code, report.invalid, report.total,
                        )
                    if valid:
                        n = st.upsert(table, code, valid)
                        logger.info("[cache] %s %s 后台回写 %d 条", table, code, n)
                finally:
                    st.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[cache] %s %s 后台回写失败（不影响本次结果）：%s",
                    table, code, exc,
                )

        threading.Thread(
            target=_job, name=f"cache-write-{table}-{code}", daemon=True
        ).start()

    def _with_url(self, data: dict, dataset: str, code: str) -> dict:
        """确保返回数据带文章级数据来源 URL（存储命中时也无缺失）。"""
        data = dict(data)
        data.setdefault("url", source_url(dataset, code))
        return data

    def company_info(self, code: str) -> dict:
        recs = self._stored("company", code)
        if recs:
            r = recs[0]
            return {k: r.get(k) for k in ("code", "ts_code", "name", "industry", "list_date")}
        info = self._cached(f"info:{code}", lambda: self._source.company_info(code))
        self._write_back("company", code, [info])
        return self._with_url(info, "company", code)

    def financials(self, code: str, years: int = 10) -> dict:
        recs = self._stored("financials", code)
        if recs is not None:
            return self._with_url(
                {"records": recs, "source": f"storage({self._storage.name})"},
                "financials", code,
            )
        return self._with_url(
            self._fetch(
                "financials", code, f"fin:{code}:{years}",
                lambda: self._source.financials(code, years),
            ),
            "financials", code,
        )

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        recs = self._stored("daily_price", code)
        if recs is not None:
            return self._with_url(
                {"records": recs, "source": f"storage({self._storage.name})"},
                "daily_price", code,
            )
        return self._with_url(
            self._fetch(
                "daily_price", code, f"price:{code}:{start}:{end}",
                lambda: self._source.daily_prices(code, start, end),
            ),
            "daily_price", code,
        )

    def valuation_history(self, code: str) -> dict:
        recs = self._stored("valuation_history", code)
        if recs is not None:
            return self._with_url(
                {"records": recs, "source": f"storage({self._storage.name})"},
                "valuation_history", code,
            )
        return self._with_url(
            self._fetch(
                "valuation_history", code, f"val:{code}",
                lambda: self._source.valuation_history(code),
            ),
            "valuation_history", code,
        )

    def dividends(self, code: str) -> dict:
        recs = self._stored("dividends", code)
        if recs is not None:
            return self._with_url(
                {"records": recs, "source": f"storage({self._storage.name})"},
                "dividends", code,
            )
        return self._with_url(
            self._fetch(
                "dividends", code, f"div:{code}",
                lambda: self._source.dividends(code),
            ),
            "dividends", code,
        )
