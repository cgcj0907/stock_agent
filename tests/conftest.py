"""共享测试夹具。

StubData：为依赖数据源的智能体提供可复现的测试数据，
避免测试依赖真实数据源（AkShare）或真实数据库。
"""
from __future__ import annotations

import pytest

# 先加载 agents 包（agents/__init__ → builtin → 全部内置 agent），
# 避免后续直接 import moat.agent 等触发「builtin → moat.agent」循环导入。
import value_agent.agents.base  # noqa: F401


@pytest.fixture(autouse=True)
def _no_real_peer_medians(monkeypatch):
    """单测不联网：M5 真实同行中位数拉取替换为空实现（回退静态基准）。

    真实 provider（moat/peer_benchmarks.py）有独立单测（注入假 akshare）；
    这里只保证全量测试不触发网络、不慢。
    """
    monkeypatch.setattr(
        "value_agent.moat.agent._fetch_peer_medians", lambda code, industry: None
    )


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
                    # 1.1/5.2/5.4 派生字段（NAV/NCAV、有息负债、研发）
                    "bvps": 30.0,
                    "ncav_ps": 12.0,
                    "rd_ratio": 0.06,
                    "interest_debt_ratio": 0.15,
                    "contract_liability_ratio": 0.10,
                    "ocf_to_np_parent": 1.15,
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
        # 10 条、都在近 10 年窗口内（2016-12-31 ~ 2025-12-31），M7 分位口径稳定
        return {
            "records": [
                {
                    "trade_date": f"{y}-12-31",
                    "pe_ttm": 25.0,
                    "pb": 5.0,
                    "dv_ttm": 2.0,
                }
                for y in range(2025, 2015, -1)
            ]
        }

    def governance_events(self, code: str) -> dict:
        # M6 非分红证据：1 条回购（+分），无质押/减持
        return {
            "records": [
                {"kind": "buybacks", "event_date": "20260115", "holder": "",
                 "ratio": None, "description": "回购进展：累计回购 1.2 亿元"},
            ],
        }

    def daily_prices(self, code: str) -> dict:
        # 12 条带换手率（情绪指标）：最新换手率偏低 → M7 情绪偏冷；最新收盘 101.5 供 M4 现价
        dates = ["20250804", "20250901", "20251008", "20251103", "20251201",
                 "20260105", "20260202", "20260302", "20260401", "20260506",
                 "20260601", "20260803"]
        turnovers = [3.5, 3.2, 3.0, 2.8, 2.6, 2.4, 2.2, 2.0, 1.9, 1.8, 1.6, 1.5]
        return {
            "records": [
                {
                    "trade_date": d,
                    "open": 99.5 + i * 0.1,
                    "close": 100.0 + i * 0.15,
                    "high": 101.0 + i * 0.1,
                    "low": 98.5 + i * 0.1,
                    "volume": 1_000_000 + i * 20_000,
                    "turnover": t,
                }
                for i, (d, t) in enumerate(zip(dates, turnovers))
            ],
        }


@pytest.fixture
def stub_data() -> StubData:
    return StubData()
