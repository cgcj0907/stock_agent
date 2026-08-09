"""ETL 管线：数据源 → 存储（全量初始化 / 每日增量更新）。"""
from __future__ import annotations

import logging

from value_agent.data.sources.base import DataSource
from value_agent.data.storage.base import MarketStorage
from value_agent.data.validate import valid_records

logger = logging.getLogger(__name__)


def _upsert_valid(storage: MarketStorage, table: str, code: str, records: list[dict]) -> int:
    """勾稽校验后入库，剔除无效记录并告警（quality_flag 机制）。"""
    valid, report = valid_records(table, records)
    if report.issues:
        logger.warning("[validate] %s %s：%d/%d 条无效（%s）",
                       table, code, report.invalid, report.total,
                       report.issues[0]["message"])
    if valid:
        return storage.upsert(table, code, valid)
    return 0


def _with_retry(fn, attempts: int = 3, delay: float = 0.5):
    """预取管道里的数据源轻量重试（东财/巨潮偶发断连/DNS 抖动）。"""
    import time

    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(delay * (i + 1))
    raise last  # type: ignore[misc]


def ingest_company(storage: MarketStorage, source: DataSource, code: str, years: int = 10) -> int:
    """全量入库一家公司：基本信息 + 财报 + 行情 + 估值 + 分红（含勾稽校验）。返回写入记录数。"""
    n = 0
    # company_info（巨潮）失败不阻塞：基本信息只是名称/行业增强，M4 等只需下面 4 张数据表
    try:
        info = _with_retry(lambda: source.company_info(code))
        n += storage.upsert("company", code, [info])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ingest] %s company_info 失败（跳过基本信息）：%s", code, exc)
    n += _upsert_valid(storage, "financials", code, _with_retry(lambda: source.financials(code, years)["records"]))
    n += _upsert_valid(storage, "daily_price", code, _with_retry(lambda: source.daily_prices(code)["records"]))
    n += _upsert_valid(storage, "valuation_history", code, _with_retry(lambda: source.valuation_history(code)["records"]))
    n += _upsert_valid(storage, "dividends", code, _with_retry(lambda: source.dividends(code)["records"]))
    # 6.1：治理事件（best-effort，失败返回空；表未接入时不影响评分）
    try:
        gov = source.governance_events(code) if hasattr(source, "governance_events") else {}
        n += storage.upsert("governance_events", code, (gov or {}).get("records", []) or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ingest] %s governance_events 失败（跳过治理事件）：%s", code, exc)
    # 7.1/7.2：北向持股 + 两融余额（best-effort，快照入库供 M7 分位）
    for table, fetcher in (("northbound", lambda: source.northbound(code)),
                           ("margin", lambda: source.margin(code))):
        try:
            if hasattr(source, table):
                n += storage.upsert(table, code, fetcher().get("records", []) or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ingest] %s %s 失败（跳过）：%s", code, table, exc)
    logger.info("[ingest] %s 入库 %d 条", code, n)
    return n


def daily_update(
    storage: MarketStorage,
    source: DataSource,
    codes: list[str],
    lookback_days: int = 10,
) -> dict:
    """每日增量：只更新行情与估值（财报季用全量 ingest）。返回各表新增条数。"""
    stats = {"daily_price": 0, "valuation_history": 0, "skipped": 0}
    for code in codes:
        latest = storage.latest("daily_price", code)
        # 真增量：有缓存时只拉最新交易日之后（start=latest），避免每次全量拉 10 年历史
        start = latest
        prices = [r for r in source.daily_prices(code, start=start)["records"]
                  if latest is None or r["trade_date"] > latest]
        valuations = [
            r for r in source.valuation_history(code, start=start)["records"]
            if latest is None or r["trade_date"] > latest
        ]
        if not prices and not valuations:
            stats["skipped"] += 1
            continue
        stats["daily_price"] += storage.upsert("daily_price", code, prices)
        stats["valuation_history"] += storage.upsert("valuation_history", code, valuations)
        logger.info("[update] %s 新增行情 %d / 估值 %d", code, len(prices), len(valuations))
    return stats
