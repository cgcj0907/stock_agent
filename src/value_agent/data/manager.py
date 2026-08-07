"""数据管理器：存储优先（Supabase/SQLite），缺失时回退实时源并后台回写。

- 本地/部署：优先读已入库数据（快、稳定、海外可用）
- 未入库或库为空：回退实时源（AkShare/mock），并把拉取结果**后台回写**进存储
  （读穿缓存：首次命中实时源，之后命中存储；回写失败只记日志，不影响本次结果）
- 组合源：分红走 AkShare 巨潮（见 sources/combined.py）
"""
from __future__ import annotations

import datetime
import logging
import os
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

    def _incremental_daily(self, code: str, recs: list[dict], end: str | None) -> list[dict]:
        """日线增量刷新：只拉存储中最新交易日之后的数据并只写新增，失败回退缓存。

        避免「只缺最新一个月就全量重写 2400 行」；每次分析自动补上最新行情。
        返回合并后的 records（旧 + 新）。
        """
        latest = max((str(r.get("trade_date") or "") for r in recs), default="")
        if not latest:
            return recs
        try:
            inc_start_d = datetime.date(int(latest[:4]), int(latest[4:6]), int(latest[6:8])) + datetime.timedelta(days=1)
        except (ValueError, TypeError, IndexError):
            return recs
        inc_start = inc_start_d.strftime("%Y%m%d")
        try:
            inc = self._fetch(
                "daily_price", code, f"price:{code}:{inc_start}:{end}",
                lambda: self._source.daily_prices(code, inc_start, end),
            )
            new_recs = [r for r in inc.get("records", []) if str(r.get("trade_date") or "") > latest]
            if new_recs:
                return recs + new_recs
        except Exception as exc:  # noqa: BLE001
            logger.warning("[daily] %s 增量刷新失败，使用缓存：%s", code, exc)
        return recs

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

    def _fetch_with_retry(self, fn, attempts: int = 3, delay: float = 0.5):
        """实时源瞬时断连/限流时轻量重试（指数退避）；全部失败才向上抛，由调用方降级。

        背景：AkShare 底层东财/新浪接口偶发 SSL 断连、连接被重置，M4 一次拉 4 个数据集，
        任何一个瞬时失败都会把整个模块降级成空白，重试可显著降低这类空白率。
        """
        import time

        last: Exception | None = None
        for i in range(attempts):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last = exc
                logger.warning(
                    "实时源拉取失败（第 %d/%d 次）：%s", i + 1, attempts, exc
                )
                time.sleep(delay * (i + 1))
        raise last  # type: ignore[misc]

    def _fetch(self, table: str, code: str, key: str, fetcher) -> dict:
        """实时源拉取 + 进程内缓存 + 后台回写存储（只在真正拉取时回写一次）。"""
        if key not in self._cache:
            data = self._fetch_with_retry(fetcher)
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

        # serverless（FC 等）请求结束后会冻结/回收实例，daemon 线程可能来不及写完；
        # 设 DATA_WRITE_BACK=sync 时改为同步写入，保证落库后再返回。
        if os.getenv("DATA_WRITE_BACK", "").strip().lower() in ("sync", "1", "true"):
            try:
                _job()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[cache] %s %s 同步回写失败：%s", table, code, exc)
        else:
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
        info = self._cached(
            f"info:{code}",
            lambda: self._fetch_with_retry(lambda: self._source.company_info(code)),
        )
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
        # 进程内缓存合并结果：一次分析只做一次增量刷新
        merged_key = f"daily:{code}:merged"
        if merged_key in self._cache:
            return self._cache[merged_key]
        recs = self._stored("daily_price", code)
        if recs is not None:
            # 有缓存时增量刷新（只拉最新之后、只写新增），失败回退缓存
            recs = self._incremental_daily(code, recs, end)
            data = self._with_url(
                {"records": recs, "source": f"storage({self._storage.name})+incremental"},
                "daily_price", code,
            )
        else:
            data = self._with_url(
                self._fetch(
                    "daily_price", code, f"price:{code}:{start}:{end}",
                    lambda: self._source.daily_prices(code, start, end),
                ),
                "daily_price", code,
            )
        self._cache[merged_key] = data
        return data

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
