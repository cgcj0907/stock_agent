"""数据源抽象：业务代码只依赖此接口，不感知具体数据源。"""
from __future__ import annotations

from abc import ABC, abstractmethod


def to_float(value, divisor: float = 1.0) -> float | None:
    """把字符串/百分比/千分位转 float，失败返回 None（各数据源共用）。"""
    if value in (None, "", "-", "nan"):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "")) / divisor
    except (TypeError, ValueError):
        return None


class DataSource(ABC):
    """统一数据接口。返回普通 dict（含 records 列表 + source 标记）。

    生产用 AkShareDataSource（全免费）；本地开发/离线用 MockDataSource。
    """

    name: str = "base"

    @abstractmethod
    def company_info(self, code: str) -> dict:
        """公司基本信息：{code, name, industry, ...}。"""

    @abstractmethod
    def financials(self, code: str, years: int = 10) -> dict:
        """财务指标（ROE/毛利率/现金流…）：{records: [{period, roe, ...}]}。"""

    @abstractmethod
    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        """日行情：{records: [{date, open, close, high, low, volume}]}。"""

    @abstractmethod
    def valuation_history(self, code: str) -> dict:
        """估值历史（PE/PB/股息率）：{records: [{date, pe, pb, dividend_yield}]}。"""

    @abstractmethod
    def dividends(self, code: str) -> dict:
        """分红历史：{records: [{year, per_share, total}]}。"""

    def governance_events(self, code: str) -> dict:
        """治理事件（M6 非分红证据）：{records: [...]}，默认无数据。

        数据源可实现覆盖，records 元素建议字段：
        {kind: pledges|reductions|regulatory|auditor_changes|acquisitions|buybacks,
         holder, period/date, ratio, reason}。
        M6 引擎（governance/engine.py::assess_governance）按事件类别扣分/加分，
        并映射为结构化治理风险码。未实现时返回空，治理按中性计，不臆测。
        """
        return {"records": [], "source": self.name}
