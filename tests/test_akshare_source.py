"""AkShare 数据源容错测试：东财个股信息失败时回退巨潮公司概况。"""
from __future__ import annotations

import json

import pandas as pd
import pytest

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


def _fake_financials_df(with_ratio: bool = True) -> pd.DataFrame:
    """模拟新浪财务指标接口返回（displaytype=4 的列名，含/不含 ocf_to_np 比率列）。"""
    rows = [
        {
            "日期": "2023-12-31",
            "净资产收益率(%)": 30.0,
            "毛利率(%)": 90.0,
            "净利率(%)": 50.0,
            "资产负债率(%)": 20.0,
            "摊薄每股收益(元)": 60.0,
            "每股经营性现金流(元)": 50.0,
            "经营现金净流量与净利润的比率(%)": 0.8333,  # akshare 原始值即比率（列名带%但别÷100）
        },
        {
            "日期": "2024-12-31",
            "净资产收益率(%)": 31.0,
            "毛利率(%)": 91.0,
            "净利率(%)": 51.0,
            "资产负债率(%)": 19.0,
            "摊薄每股收益(元)": 66.0,
            "每股经营性现金流(元)": 66.0,
            "经营现金净流量与净利润的比率(%)": 1.0,
        },
    ]
    if not with_ratio:
        for r in rows:
            r.pop("经营现金净流量与净利润的比率(%)")
    return pd.DataFrame(rows)


def test_financials_parses_ocf_to_np_ratio(monkeypatch):
    """新浪财务指标接口的「经营现金净流量与净利润的比率(%)」应解析为 ocf_to_np。

    注意：列名带 (%)，但 akshare 原始值已是比率（如茅台 2024=1.0350），不得再 ÷100。
    """
    ds = AkShareDataSource()
    monkeypatch.setattr(ds._ak, "stock_financial_analysis_indicator",
                        lambda symbol="": _fake_financials_df(with_ratio=True))

    out = ds.financials("600519")
    recs = out["records"]
    assert len(recs) == 2
    r_2023 = next(r for r in recs if r["period"] == "20231231")
    r_2024 = next(r for r in recs if r["period"] == "20241231")
    assert r_2023["ocf_to_np"] == pytest.approx(0.8333)
    assert r_2024["ocf_to_np"] == 1.0
    assert r_2023["ocfps"] == 50.0
    assert r_2023["eps"] == 60.0


def test_financials_ocf_to_np_fallback_ocfps_div_eps(monkeypatch):
    """新浪个别页面缺比率列时，用 每股经营现金流/每股收益 兜底（两者口径等价）。"""
    ds = AkShareDataSource()
    monkeypatch.setattr(ds._ak, "stock_financial_analysis_indicator",
                        lambda symbol="": _fake_financials_df(with_ratio=False))

    recs = ds.financials("600519")["records"]
    r_2023 = next(r for r in recs if r["period"] == "20231231")
    r_2024 = next(r for r in recs if r["period"] == "20241231")
    assert r_2023["ocf_to_np"] == pytest.approx(round(50.0 / 60.0, 4))  # ocfps/eps 兜底（保留4位）
    assert r_2024["ocf_to_np"] == 1.0
