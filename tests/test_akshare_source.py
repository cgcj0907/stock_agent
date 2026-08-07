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


# ---- 日线多源回退链（东财 akshare → 新浪 → 腾讯） ----

def _em_df():
    """东财日线 DataFrame（日期/开收高低/成交量(手)/换手率(%)）。"""
    return pd.DataFrame(
        [
            {"日期": "2024-01-05", "开盘": 10.0, "收盘": 11.0, "最高": 12.0,
             "最低": 9.0, "成交量": 1000.0, "成交额": 2e6, "换手率": 0.44},
            {"日期": "2024-01-08", "开盘": 11.0, "收盘": 12.0, "最高": 13.0,
             "最低": 10.0, "成交量": 1200.0, "成交额": 2.4e6, "换手率": 0.52},
        ]
    )


def _sina_df():
    """新浪日线 DataFrame（date/open/.../volume(股)/turnover(小数)）。"""
    return pd.DataFrame(
        [
            {"date": "2024-01-05", "open": 10.0, "high": 12.0, "low": 9.0,
             "close": 11.0, "volume": 100000.0, "amount": 2e6, "turnover": 0.0044},
            {"date": "2024-01-08", "open": 11.0, "high": 13.0, "low": 10.0,
             "close": 12.0, "volume": 120000.0, "amount": 2.4e6, "turnover": 0.0052},
        ]
    )


def _tx_df():
    """腾讯日线 DataFrame（date/open/close/high/low/volume/turnover/amount）。"""
    return pd.DataFrame(
        [
            {"date": "2024-01-05", "open": 10.0, "close": 11.0, "high": 12.0,
             "low": 9.0, "volume": 100000.0, "turnover": 0.0044, "amount": 2e6},
            {"date": "2024-01-08", "open": 11.0, "close": 12.0, "high": 13.0,
             "low": 10.0, "volume": 120000.0, "turnover": 0.0052, "amount": 2.4e6},
        ]
    )


def test_daily_prices_prefers_eastmoney(monkeypatch):
    """东财（akshare）可用时优先，成交量=手、换手率=% 原样保留。"""
    ds = AkShareDataSource()
    monkeypatch.setattr(ds._ak, "stock_zh_a_hist", lambda **kw: _em_df())
    # 不应走到新浪/腾讯
    monkeypatch.setattr(ds._ak, "stock_zh_a_daily",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("不应回退新浪")))
    monkeypatch.setattr(ds._ak, "stock_zh_a_hist_tx",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("不应回退腾讯")))
    out = ds.daily_prices("600900", "20240101", "20240131")
    assert out["source"] == "akshare(eastmoney)"
    assert out["records"][0]["trade_date"] == "20240105"
    assert out["records"][0]["volume"] == 1000.0
    assert out["records"][0]["turnover"] == 0.44


def test_daily_prices_falls_back_to_sina(monkeypatch):
    """东财断连 → 回退新浪（独立主机），单位归一化：成交量股→手、换手率小数→%。"""
    ds = AkShareDataSource()
    monkeypatch.setattr(
        ds._ak, "stock_zh_a_hist",
        lambda **kw: (_ for _ in ()).throw(ConnectionError("RemoteDisconnected")),
    )
    monkeypatch.setattr(ds._ak, "stock_zh_a_daily", lambda **kw: _sina_df())
    out = ds.daily_prices("600900", "20240101", "20240131")
    assert out["source"] == "akshare(sina)"
    assert out["records"][0]["trade_date"] == "20240105"
    assert out["records"][0]["volume"] == 1000.0          # 100000 股 → 1000 手
    assert out["records"][0]["turnover"] == pytest.approx(0.44)  # 0.0044 → 0.44%


def test_daily_prices_falls_back_to_tencent(monkeypatch):
    """东财 + 新浪全挂 → 回退腾讯。"""
    ds = AkShareDataSource()
    monkeypatch.setattr(
        ds._ak, "stock_zh_a_hist",
        lambda **kw: (_ for _ in ()).throw(ConnectionError("RemoteDisconnected")),
    )
    monkeypatch.setattr(
        ds._ak, "stock_zh_a_daily",
        lambda **kw: (_ for _ in ()).throw(ConnectionError("RemoteDisconnected")),
    )
    monkeypatch.setattr(ds._ak, "stock_zh_a_hist_tx", lambda **kw: _tx_df())
    out = ds.daily_prices("600900", "20240101", "20240131")
    assert out["source"] == "akshare(tencent)"
    assert out["records"][1]["volume"] == 1200.0
    assert out["records"][1]["turnover"] == pytest.approx(0.52)


def test_daily_prices_all_sources_fail_raises_summary(monkeypatch):
    """三源全挂 → ConnectionError，且摘要含各源失败信息（供上层证据/日志诊断）。"""
    ds = AkShareDataSource()
    for attr in ("stock_zh_a_hist", "stock_zh_a_daily", "stock_zh_a_hist_tx"):
        monkeypatch.setattr(
            ds._ak, attr,
            lambda **kw: (_ for _ in ()).throw(ConnectionError("RemoteDisconnected")),
        )
    with pytest.raises(ConnectionError) as ei:
        ds.daily_prices("600900", "20240101", "20240131")
    msg = str(ei.value)
    assert "eastmoney" in msg
    assert "sina" in msg
    assert "tencent" in msg


def test_financials_parses_sales_margin_columns(monkeypatch):
    """新浪列名「销售毛利率(%)/销售净利率(%)」也应解析（akshare 1.18 起带「销售」前缀）。"""
    ds = AkShareDataSource()
    df = pd.DataFrame([
        {"日期": "2025-12-31", "净资产收益率(%)": 15.59,
         "销售毛利率(%)": 62.1, "销售净利率(%)": 40.5,
         "资产负债率(%)": 58.3, "摊薄每股收益(元)": 1.4,
         "每股经营性现金流(元)": 2.0, "经营现金净流量与净利润的比率(%)": 1.5},
    ])
    monkeypatch.setattr(ds._ak, "stock_financial_analysis_indicator", lambda symbol: df)
    for fn in ("stock_balance_sheet_by_report_em", "stock_profit_sheet_by_report_em",
               "stock_cash_flow_sheet_by_report_em"):
        monkeypatch.setattr(ds._ak, fn, lambda symbol: pd.DataFrame())
    fin = ds.financials("600900")
    rec = fin["records"][0]
    assert rec["grossprofit_margin"] == 62.1
    assert rec["netprofit_margin"] == 40.5
    assert rec["debt_to_assets"] == 0.583


def test_merge_financial_statements_english_columns():
    """东财三大报表英文字段（akshare 1.18 起）也能补出有息负债率/合同负债/bvps/归母现金流。"""
    from value_agent.data.sources.akshare_source import _merge_financial_statements

    b = pd.DataFrame([{
        "REPORT_DATE": "2025-12-31", "TOTAL_ASSETS": 100.0,
        "CURRENT_ASSET_BALANCE": 30.0, "TOTAL_LIABILITIES": 60.0,
        "PARENT_EQUITY_BALANCE": 40.0, "SHORT_LOAN": 10.0,
        "LONG_LOAN": 20.0, "BOND_PAYABLE": 5.0,
        "NONCURRENT_LIAB_1YEAR": 2.0, "CONTRACT_LIAB": 8.0,
    }])
    i = pd.DataFrame([{
        "REPORT_DATE": "2025-12-31", "TOTAL_OPERATE_INCOME": 50.0,
        "PARENT_NETPROFIT": 10.0, "NETPROFIT": 10.0,
    }])
    c = pd.DataFrame([{"REPORT_DATE": "2025-12-31", "NETCASH_OPERATE": 12.0}])

    class FakeAk:
        def stock_balance_sheet_by_report_em(self, symbol=""):
            return b
        def stock_profit_sheet_by_report_em(self, symbol=""):
            return i
        def stock_cash_flow_sheet_by_report_em(self, symbol=""):
            return c

    recs = [{"period": "20251231", "eps": 1.0}]
    _merge_financial_statements("600900", recs, FakeAk())
    rec = recs[0]
    assert rec["interest_debt_ratio"] == round((10 + 20 + 5 + 2) / 100, 4)
    assert rec["contract_liability_ratio"] == round(8 / 100, 4)
    assert rec["bvps"] == round(40 / 10, 4)          # 股本 = 10 / 1.0
    assert rec["ncav_ps"] == round((30 - 60) / 10, 4)
    assert rec["ocf_to_np_parent"] == round(12 / 10, 4)


def test_financials_backfills_margins_from_ths(monkeypatch):
    """新浪「销售毛利率」为 NaN 时，用同花顺财务摘要直接补真实毛利率（不自行推算）。"""
    ds = AkShareDataSource()
    df = pd.DataFrame([
        {"日期": "2025-12-31", "净资产收益率(%)": 15.59,
         "销售毛利率(%)": None, "销售净利率(%)": 40.5,
         "资产负债率(%)": 58.3, "摊薄每股收益(元)": 1.4,
         "每股经营性现金流(元)": 2.0, "经营现金净流量与净利润的比率(%)": 1.5},
    ])
    ths = pd.DataFrame([
        {"报告期": "2025-12-31", "销售毛利率": "61.67%", "销售净利率": "40.52%"},
    ])
    monkeypatch.setattr(ds._ak, "stock_financial_analysis_indicator", lambda symbol: df)
    monkeypatch.setattr(ds._ak, "stock_financial_abstract_ths", lambda symbol, indicator: ths)
    for fn in ("stock_balance_sheet_by_report_em", "stock_profit_sheet_by_report_em",
               "stock_cash_flow_sheet_by_report_em"):
        monkeypatch.setattr(ds._ak, fn, lambda symbol: pd.DataFrame())
    fin = ds.financials("600900")
    rec = fin["records"][0]
    assert rec["grossprofit_margin"] == 61.67
    assert rec["netprofit_margin"] == 40.5  # 新浪已有值，不回填覆盖
