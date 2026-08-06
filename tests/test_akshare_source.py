"""AkShare 数据源容错测试：东财个股信息失败时回退巨潮公司概况。"""
from __future__ import annotations

import json

import pandas as pd

from value_agent.data.sources.akshare_source import AkShareDataSource


def test_company_info_falls_back_to_cninfo(monkeypatch):
    ds = AkShareDataSource()

    def boom(symbol: str = ""):
        raise json.JSONDecodeError("Expecting value", "", 0)

    monkeypatch.setattr(ds._ak, "stock_individual_info_em", boom)
    monkeypatch.setattr(
        ds._ak,
        "stock_profile_cninfo",
        lambda symbol: pd.DataFrame(
            [{"A股简称": "美的集团", "所属行业": "白色家电", "上市日期": "2013-09-18"}]
        ),
    )

    info = ds.company_info("000333")
    assert info["code"] == "000333"
    assert info["name"] == "美的集团"
    assert info["industry"] == "白色家电"
    assert info["list_date"] == "2013-09-18"


def test_company_info_cninfo_empty_returns_minimal(monkeypatch):
    ds = AkShareDataSource()
    monkeypatch.setattr(
        ds._ak, "stock_individual_info_em",
        lambda symbol="": (_ for _ in ()).throw(json.JSONDecodeError("x", "", 0)),
    )
    monkeypatch.setattr(ds._ak, "stock_profile_cninfo", lambda symbol: pd.DataFrame())

    info = ds.company_info("000333")
    assert info["name"] == "000333"
    assert info["industry"] == ""
