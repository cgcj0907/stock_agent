"""共享测试夹具。

StubData：为依赖数据源的智能体提供可复现的测试数据，
避免测试依赖真实数据源（BaoStock/AkShare）或真实数据库。
"""
from __future__ import annotations

import pytest


class StubData:
    """数据桩：实现 DataManager 的查询接口，返回固定记录。"""

    def financials(self, code: str, years: int = 10) -> dict:
        recs = []
        for i in range(years):
            year = 2024 - i
            recs.append(
                {
                    "period": f"{year}1231",
                    "roe": 18.0,
                    "grossprofit_margin": 45.0,
                    "netprofit_margin": 25.0,
                    "debt_to_assets": 0.35,
                    "ocfps": 2.0,
                    "eps": 5.0,
                    "ocf_to_np": 1.2,
                }
            )
        return {"records": recs}

    def company_info(self, code: str) -> dict:
        return {"name": f"测试公司{code}", "industry": "白酒", "code": code}

    def dividends(self, code: str) -> dict:
        return {
            "records": [
                {"period": f"{y}1231", "cash_div_tax": 2.0}
                for y in range(2024, 2014, -1)
            ]
        }

    def valuation_history(self, code: str) -> dict:
        return {
            "records": [
                {
                    "trade_date": f"{y}-06-30",
                    "pe_ttm": 25.0,
                    "pb": 5.0,
                    "dv_ttm": 2.0,
                }
                for y in range(2024, 2014, -1)
            ]
        }

    def daily_prices(self, code: str) -> dict:
        return {
            "records": [{"trade_date": "2024-06-30", "close": 100.0}]
        }


@pytest.fixture
def stub_data() -> StubData:
    return StubData()
