"""组合数据源测试：方法级覆盖 + 失败回退。"""
import pytest

from value_agent.data.sources.base import DataSource
from value_agent.data.sources.combined import CombinedDataSource


class _Base(DataSource):
    name = "mock"
    def company_info(self, code):
        return {"name": "primary"}
    def financials(self, code, years=10):
        return {"records": [], "source": "mock"}
    def daily_prices(self, code, start=None, end=None):
        return {"records": [], "source": "mock"}
    def valuation_history(self, code):
        return {"records": [], "source": "mock"}
    def dividends(self, code):
        return {"records": [{"period": "20241231", "cash_div_tax": 1.0}], "source": "mock"}


class _Div(DataSource):
    name = "akshare"
    def company_info(self, code):
        return {"name": "ak"}
    def financials(self, code, years=10):
        return {"records": [], "source": "akshare"}
    def daily_prices(self, code, start=None, end=None):
        return {"records": [], "source": "akshare"}
    def valuation_history(self, code):
        return {"records": [], "source": "akshare"}
    def dividends(self, code):
        return {"records": [{"period": "20251231", "cash_div_tax": 2.2}], "source": "akshare"}


class _Broken(DataSource):
    name = "broken"
    def company_info(self, code):
        return {"name": "broken"}
    def financials(self, code, years=10):
        return {"records": [], "source": "broken"}
    def daily_prices(self, code, start=None, end=None):
        return {"records": [], "source": "broken"}
    def valuation_history(self, code):
        return {"records": [], "source": "broken"}
    def dividends(self, code):
        raise RuntimeError("网络失败")


def test_dividends_use_override():
    ds = CombinedDataSource(_Base(), overrides={"dividends": _Div()})
    assert ds.dividends("600519")["records"][0]["cash_div_tax"] == 2.2


def test_override_failure_falls_back_to_primary():
    ds = CombinedDataSource(_Base(), overrides={"dividends": _Broken()})
    assert ds.dividends("600519")["records"][0]["cash_div_tax"] == 1.0


def test_other_methods_use_primary():
    ds = CombinedDataSource(_Base(), overrides={"dividends": _Div()})
    assert ds.company_info("600519")["name"] == "primary"


def test_name_marks_combination():
    ds = CombinedDataSource(_Base(), overrides={"dividends": _Div()})
    assert "akshare" in ds.name and "mock" in ds.name
