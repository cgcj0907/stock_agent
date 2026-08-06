"""CompanyReferences 工具测试（mock akshare，不依赖外网）。"""
from __future__ import annotations

import pandas as pd

from value_agent.data.references import CompanyReferences, _refs_from_df


class _FakeAk:
    def stock_zh_a_disclosure_report_cninfo(self, **kwargs):
        return pd.DataFrame([
            {"公告标题": "2024年年度报告", "公告链接": "https://www.cninfo.com.cn/new/disclosure/detail?a=1"},
            {"公告标题": "2023年年度报告", "公告链接": "https://www.cninfo.com.cn/new/disclosure/detail?a=2"},
        ])

    def stock_individual_notice_report(self, **kwargs):
        return pd.DataFrame([
            {"公告标题": "2025年第一季度报告", "网址": "https://data.eastmoney.com/notices/detail/601919/1.html"},
        ])

    def stock_news_em(self, symbol="", **kwargs):
        return pd.DataFrame([
            {"新闻标题": "中远海控业绩大涨", "新闻链接": "https://finance.eastmoney.com/a/202408301.html"},
            {"新闻标题": "集运运价走高", "新闻链接": "https://finance.eastmoney.com/a/202408302.html"},
        ])

    def stock_research_report_em(self, symbol="", **kwargs):
        return pd.DataFrame([
            {"研究报告名称": "中远海控深度报告", "报告PDF链接": "https://pdf.dfcfw.com/pdf/H3_202408301.pdf"},
        ])


def _tool() -> CompanyReferences:
    tool = CompanyReferences()
    tool._ak = _FakeAk()
    return tool


def test_refs_from_df_dedupes_by_url():
    df = pd.DataFrame([
        {"t": "A", "u": "https://a.com/1"},
        {"t": "B", "u": "https://a.com/1"},  # 重复 url
        {"t": "C", "u": "https://a.com/2"},
    ])
    refs = _refs_from_df(df, ("t",), ("u",))
    assert refs == [
        {"title": "A", "url": "https://a.com/1"},
        {"title": "C", "url": "https://a.com/2"},
    ]


def test_reports_uses_cninfo():
    refs = _tool().reports("601919")
    assert len(refs) == 2
    assert all(r["url"].startswith("https://www.cninfo.com.cn/") for r in refs)


def test_news_limits():
    refs = _tool().news("601919", limit=1)
    assert len(refs) == 1
    assert "eastmoney" in refs[0]["url"]


def test_fetch_merges_all_sources_and_dedupes():
    refs = _tool().fetch("601919", limit=10)
    urls = [r["url"] for r in refs]
    assert len(urls) == len(set(urls))
    assert len(refs) == 6  # 2 年报 + 1 公告 + 2 新闻 + 1 研报
    assert any("cninfo" in u for u in urls)
    assert any("eastmoney" in u for u in urls)


def test_fetch_respects_limit():
    refs = _tool().fetch("601919", limit=3)
    assert len(refs) == 3


def test_all_sources_fail_returns_empty(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool._ak, "stock_zh_a_disclosure_report_cninfo", lambda **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(tool._ak, "stock_individual_notice_report", lambda **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(tool._ak, "stock_news_em", lambda **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(tool._ak, "stock_research_report_em", lambda **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert tool.fetch("000002", limit=5) == []
