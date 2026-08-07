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


def test_eastmoney_kline_parsing(monkeypatch):
    """curl_cffi 东财 kline 解析：klines 字符串 → DataFrame（日期/开收高低/成交量）。"""
    from value_agent.data.sources.akshare_source import AkShareDataSource

    class _Resp:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {
                "data": {
                    "klines": [
                        "2024-01-05,10,11,12,9,1000,2000,3,5,0.5,1.2",
                        "2024-01-08,11,12,13,10,1200,2400,2,9,1,1.3",
                    ]
                }
            }

    def fake_get(url, params=None, headers=None, impersonate=None, timeout=None):
        assert params["secid"] == "0.000858"
        assert impersonate == "chrome"
        assert "Referer" in headers and "User-Agent" in headers
        return _Resp()

    monkeypatch.setattr("curl_cffi.requests.get", fake_get)
    src = AkShareDataSource()
    df = src._eastmoney_kline("000858", "20240101", "20240131")
    assert len(df) == 2
    assert df.iloc[-1]["日期"] == "2024-01-08"
    assert df.iloc[-1]["收盘"] == "12"
