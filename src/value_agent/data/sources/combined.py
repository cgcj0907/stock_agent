"""组合数据源：不同方法可来自不同数据源。

典型用法：行情/财报/估值走 BaoStock（免费稳定），分红走 AkShare 巨潮接口
（BaoStock 无分红）。某方法的主源返回空或抛错时，回退到 primary。
"""
from __future__ import annotations

import logging

from .base import DataSource

logger = logging.getLogger(__name__)


class CombinedDataSource(DataSource):
    name = "combined"

    def __init__(
        self,
        primary: DataSource,
        overrides: dict[str, DataSource] | None = None,
    ) -> None:
        """overrides: {方法名: 专用数据源}，如 {"dividends": ak_ds}。"""
        self._primary = primary
        self._overrides = overrides or {}

    @property
    def name(self) -> str:
        parts = [self._primary.name]
        for method, src in self._overrides.items():
            parts.append(f"{method}:{src.name}")
        return "combined(" + "+".join(parts) + ")"

    def _dispatch(self, method: str, code: str, *args):
        src = self._overrides.get(method, self._primary)
        try:
            result = getattr(src, method)(code, *args)
            if result.get("records"):
                return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("[combined] %s 用 %s 失败（%s），回退 %s", method, src.name, exc, self._primary.name)
        return getattr(self._primary, method)(code, *args)

    def company_info(self, code: str) -> dict:
        return self._primary.company_info(code)

    def financials(self, code: str, years: int = 10) -> dict:
        return self._primary.financials(code, years)

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        return self._primary.daily_prices(code, start, end)

    def valuation_history(self, code: str) -> dict:
        return self._primary.valuation_history(code)

    def dividends(self, code: str) -> dict:
        return self._dispatch("dividends", code)
