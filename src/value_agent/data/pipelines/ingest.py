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


def ingest_company(storage: MarketStorage, source: DataSource, code: str, years: int = 10) -> int:
    """全量入库一家公司：基本信息 + 财报 + 行情 + 估值 + 分红（含勾稽校验）。返回写入记录数。"""
    n = 0
    info = source.company_info(code)
    n += storage.upsert("company", code, [info])
    n += _upsert_valid(storage, "financials", code, source.financials(code, years)["records"])
    n += _upsert_valid(storage, "daily_price", code, source.daily_prices(code)["records"])
    n += _upsert_valid(storage, "valuation_history", code, source.valuation_history(code)["records"])
    n += _upsert_valid(storage, "dividends", code, source.dividends(code)["records"])
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
        prices = [r for r in source.daily_prices(code)["records"] if latest is None or r["trade_date"] > latest]
        valuations = [
            r for r in source.valuation_history(code)["records"]
            if latest is None or r["trade_date"] > latest
        ]
        if not prices and not valuations:
            stats["skipped"] += 1
            continue
        stats["daily_price"] += storage.upsert("daily_price", code, prices)
        stats["valuation_history"] += storage.upsert("valuation_history", code, valuations)
        logger.info("[update] %s 新增行情 %d / 估值 %d", code, len(prices), len(valuations))
    return stats
