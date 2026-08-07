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


def test_fetch_interleaves_finance_and_news():
    """fetch 应交错合并财报类与资讯类：同一段里既有巨潮年报又有东财新闻。"""
    refs = _tool().fetch("601919", limit=5, slot=0)
    urls = [r["url"] for r in refs]
    assert any("cninfo" in u for u in urls), "应包含财报/公告链接"
    assert any("eastmoney.com" in u or "dfcfw" in u for u in urls), "应包含新闻/研报链接"


def test_fetch_slot_returns_different_slice():
    """不同模块传不同 slot，拿到的参考链接不雷同。"""
    a = [r["url"] for r in _tool().fetch("601919", limit=5, slot=0)]
    b = [r["url"] for r in _tool().fetch("601919", limit=5, slot=1)]
    assert a and b
    assert a != b


def test_fetch_respects_slot_offset_when_pool_short():
    """池较短时 slot 超出也会环绕，不会越界崩溃。"""
    refs = _tool().fetch("601919", limit=5, slot=99)
    assert isinstance(refs, list)
    assert all("url" in r for r in refs)


def test_research_accepts_report_name_column():
    """新版 AkShare 研报用「报告名称」列（旧版为「研究报告名称」），都应解析。"""
    class _Ak(_FakeAk):
        def stock_research_report_em(self, symbol="", **kwargs):
            return pd.DataFrame([
                {"报告名称": "贵州茅台深度报告", "报告PDF链接": "https://pdf.dfcfw.com/pdf/H3_x.pdf"},
            ])

    tool = CompanyReferences()
    tool._ak = _Ak()
    refs = tool.research("600519", limit=1)
    assert refs and refs[0]["title"] == "贵州茅台深度报告"
    assert "dfcfw" in refs[0]["url"]


def test_format_reference_list_numbers_and_includes_snippet():
    from value_agent.data.references import format_reference_list

    refs = [
        {"title": "A", "url": "https://a.com/1", "snippet": "正文摘要", "meta": "证券时报网 · 2026-08-03"},
        {"title": "B", "url": "https://b.com/2"},
    ]
    s = format_reference_list(refs)
    assert "1. A 正文摘要 [证券时报网 · 2026-08-03]" in s
    assert "2. B" in s
    assert "不得编造" in s


def test_select_references_by_indices():
    from value_agent.data.references import select_references

    refs = [{"title": f"t{i}", "url": f"u{i}"} for i in range(5)]
    assert [r["title"] for r in select_references(refs, [3, 1])] == ["t2", "t0"]
    assert select_references(refs, None) == refs          # 无下标 → 全部
    assert select_references(refs, []) == refs            # 空数组 → 全部
    assert select_references(refs, [99, -1]) == refs      # 非法下标 → 全部
    assert select_references([], [1]) == []
    assert select_references(refs, 2) == [refs[1]]        # 单个整数
