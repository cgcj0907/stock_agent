"""Mock 数据源：确定性假数据，用于本地开发/测试（无网络、无 token）。

字段已与 storage SCHEMA 对齐（trade_date/period + 规范指标列）。
"""
from __future__ import annotations

from .base import DataSource


class MockDataSource(DataSource):
    name = "mock"

    def company_info(self, code: str) -> dict:
        return {
            "code": code,
            "ts_code": f"{code}.SH" if code.startswith("6") else f"{code}.SZ",
            "name": f"示例公司{code}",
            "industry": "示例行业",
            "list_date": "20150101",
            "source": self.name,
        }

    def financials(self, code: str, years: int = 10) -> dict:
        records = []
        for i in range(years):
            year = 2026 - i
            records.append(
                {
                    "period": f"{year}1231",
                    "roe": round(18.0 - i * 0.15, 2),
                    "grossprofit_margin": round(45.0 - i * 0.1, 2),
                    "netprofit_margin": round(25.0 - i * 0.1, 2),
                    "debt_to_assets": round(0.35 + i * 0.002, 3),
                    "ocfps": round(6.0 - i * 0.05, 2),
                    "eps": round(4.5 - i * 0.05, 2),
                    "ocf_to_np": round(1.2 - i * 0.01, 2),
                }
            )
        return {"records": records, "source": self.name}

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        return {
            "records": [
                {"trade_date": "20260731", "open": 99.5, "close": 100.0, "high": 101.0, "low": 98.5, "volume": 1_000_000, "turnover": 2.5},
                {"trade_date": "20260803", "open": 100.2, "close": 101.5, "high": 102.0, "low": 99.8, "volume": 1_200_000, "turnover": 2.8},
            ],
            "source": self.name,
        }

    def valuation_history(self, code: str) -> dict:
        return {
            "records": [
                {"trade_date": "20260731", "pe": 22.0, "pe_ttm": 21.0, "pb": 3.1, "ps": 8.0, "dv_ttm": 0.021, "total_mv": 1_200_000_000_000},
                {"trade_date": "20260803", "pe": 22.4, "pe_ttm": 21.3, "pb": 3.2, "ps": 8.1, "dv_ttm": 0.02, "total_mv": 1_220_000_000_000},
            ],
            "source": self.name,
        }

    def dividends(self, code: str) -> dict:
        return {
            "records": [
                {"period": "20241231", "cash_div_tax": 2.0, "div_proc": "实施"},
                {"period": "20251231", "cash_div_tax": 2.2, "div_proc": "实施"},
            ],
            "source": self.name,
        }

    def governance_events(self, code: str) -> dict:
        """治理事件（M6 非分红证据）：mock 返回 1 条回购 + 无质押/减持，供端到端验证。"""
        return {
            "records": [
                {"kind": "buybacks", "event_date": "20260115", "holder": "",
                 "ratio": None, "description": "回购进展：累计回购 1.2 亿元"},
            ],
            "source": self.name,
        }
