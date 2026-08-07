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


def test_parse_date_handles_common_formats():
    from value_agent.data.references import _parse_date

    assert _parse_date("2026-08-05 14:20:00").isoformat() == "2026-08-05"
    assert _parse_date("2026/08/05").isoformat() == "2026-08-05"
    assert _parse_date("2026年08月05日").isoformat() == "2026-08-05"
    assert _parse_date("20260805").isoformat() == "2026-08-05"
    assert _parse_date(None) is None
    assert _parse_date("nan") is None
    assert _parse_date("not-a-date") is None
    assert _parse_date("2026-13-99") is None


def test_news_filters_out_old_articles_and_sorts_desc():
    """新闻按发布时间倒序保留最近 1 年：2024 旧资讯必须被过滤掉。"""
    class _Ak(_FakeAk):
        def stock_news_em(self, symbol="", **kwargs):
            return pd.DataFrame([
                {"新闻标题": "2024年旧闻", "新闻链接": "https://finance.eastmoney.com/a/202408301.html",
                 "新闻内容": "正文", "文章来源": "证券时报网", "发布时间": "2024-08-30 10:00:00"},
                {"新闻标题": "2026年最新", "新闻链接": "https://finance.eastmoney.com/a/202608051.html",
                 "新闻内容": "正文", "文章来源": "证券时报网", "发布时间": "2026-08-05 09:00:00"},
                {"新闻标题": "2026年稍早", "新闻链接": "https://finance.eastmoney.com/a/202607011.html",
                 "新闻内容": "正文", "文章来源": "上海证券报", "发布时间": "2026-07-01 08:00:00"},
            ])

    tool = CompanyReferences()
    tool._ak = _Ak()
    refs = tool.news("600519", limit=5)
    titles = [r["title"] for r in refs]
    assert "2024年旧闻" not in titles, "2024 旧资讯不应进入新闻池"
    assert titles == ["2026年最新", "2026年稍早"], "应按发布时间倒序"
    assert all(r["date"] for r in refs)


def test_news_falls_back_to_newest_when_all_old():
    """全部新闻都过期时回退为最新几条（仍带日期），避免资讯池为空。"""
    class _Ak(_FakeAk):
        def stock_news_em(self, symbol="", **kwargs):
            return pd.DataFrame([
                {"新闻标题": "2024旧闻A", "新闻链接": "https://finance.eastmoney.com/a/202401011.html",
                 "新闻内容": "x", "文章来源": "a", "发布时间": "2024-01-01 10:00:00"},
                {"新闻标题": "2024旧闻B", "新闻链接": "https://finance.eastmoney.com/a/202403011.html",
                 "新闻内容": "x", "文章来源": "b", "发布时间": "2024-03-01 10:00:00"},
            ])

    tool = CompanyReferences()
    tool._ak = _Ak()
    refs = tool.news("600519", limit=1)
    assert [r["title"] for r in refs] == ["2024旧闻B"]  # 回退时取最新一条


def test_research_filters_out_old_reports():
    """研报按日期倒序保留最近 2 年：2024 旧研报应被过滤。"""
    class _Ak(_FakeAk):
        def stock_research_report_em(self, symbol="", **kwargs):
            return pd.DataFrame([
                {"报告名称": "2024年深度报告", "报告PDF链接": "https://pdf.dfcfw.com/pdf/H3_20240101.pdf",
                 "机构": "中邮证券", "东财评级": "买入", "日期": "2024-01-01"},
                {"报告名称": "2026年最新研报", "报告PDF链接": "https://pdf.dfcfw.com/pdf/H3_20260701.pdf",
                 "机构": "中邮证券", "东财评级": "买入", "日期": "2026-07-01"},
            ])

    tool = CompanyReferences()
    tool._ak = _Ak()
    refs = tool.research("600519", limit=4)
    assert [r["title"] for r in refs] == ["2026年最新研报"]


def test_reports_keeps_main_annual_reports_with_date():
    """年报只保留「XX年年度报告」主报告（剔除摘要/英文版），并带公告时间。"""
    class _Ak(_FakeAk):
        def stock_zh_a_disclosure_report_cninfo(self, **kwargs):
            return pd.DataFrame([
                {"公告标题": "贵州茅台2025年年度报告", "公告时间": "2026-04-17",
                 "公告链接": "https://www.cninfo.com.cn/new/disclosure/detail?a=1"},
                {"公告标题": "贵州茅台2025年年度报告（英文版）", "公告时间": "2026-04-17",
                 "公告链接": "https://www.cninfo.com.cn/new/disclosure/detail?a=2"},
                {"公告标题": "贵州茅台2025年年度报告摘要", "公告时间": "2026-04-17",
                 "公告链接": "https://www.cninfo.com.cn/new/disclosure/detail?a=3"},
                {"公告标题": "贵州茅台2024年年度报告", "公告时间": "2025-04-03",
                 "公告链接": "https://www.cninfo.com.cn/new/disclosure/detail?a=4"},
            ])

    tool = CompanyReferences()
    tool._ak = _Ak()
    refs = tool.reports("600519")
    assert [r["title"] for r in refs] == ["贵州茅台2025年年度报告", "贵州茅台2024年年度报告"]
    assert refs[0]["date"] == "2026-04-17"
    assert "2026-04-17" in refs[0]["meta"]


def test_notices_include_date():
    class _Ak(_FakeAk):
        def stock_individual_notice_report(self, **kwargs):
            return pd.DataFrame([
                {"公告标题": "2025年年度权益分派实施公告", "公告日期": "2026-06-22",
                 "网址": "https://data.eastmoney.com/notices/detail/600519/1.html"},
            ])

    tool = CompanyReferences()
    tool._ak = _Ak()
    refs = tool.notices("600519", limit=8)
    assert refs[0]["date"] == "2026-06-22"
    assert "2026-06-22" in refs[0]["meta"]


def test_format_reference_list_shows_date_when_meta_missing():
    from value_agent.data.references import format_reference_list

    refs = [{"title": "A", "url": "https://a.com/1", "date": "2026-08-03"}]
    s = format_reference_list(refs)
    assert "1. A [2026-08-03]" in s
    assert "优先引用较新的资料" in s


def test_fetch_cache_expires_after_ttl(monkeypatch):
    """进程内缓存超过 TTL 后应重新拉取，避免长驻服务一直用旧资讯池。"""
    from value_agent.data import references as refs_mod

    tool = _tool()
    refs_mod._CACHE.clear()  # 隔离其他测试留下的缓存，保证 TTL 判定确定
    fake_time = {"now": 1000.0}
    monkeypatch.setattr(refs_mod.time, "monotonic", lambda: fake_time["now"])
    a = tool.fetch("601919", limit=5)
    assert a
    # 未过期：命中缓存，不重新拉取（池内容一致）
    b = tool.fetch("601919", limit=5)
    assert b == a
    # 超过 TTL：重新拉取（模拟数据源变化后拿到新池）
    monkeypatch.setattr(tool._ak, "stock_news_em", lambda symbol="", **k: pd.DataFrame([
        {"新闻标题": "新新闻", "新闻链接": "https://finance.eastmoney.com/a/20260807new.html"},
    ]))
    fake_time["now"] += refs_mod._CACHE_TTL + 1
    c = tool.fetch("601919", limit=5)
    assert any("new" in r["url"] for r in c), "缓存过期后应重新拉取"


def test_recent_fallback_keeps_dated_first():
    """回退时：有日期的按倒序在前，无日期的放最后，不污染顺序。"""
    from value_agent.data.references import _recent

    refs = [
        {"title": "无日期", "url": "https://a.com/0"},
        {"title": "旧但最新", "url": "https://a.com/1", "date": "2024-03-01"},
        {"title": "更旧", "url": "https://a.com/2", "date": "2024-01-01"},
    ]
    out = _recent(refs, max_age_days=365, limit=3)
    assert [r["title"] for r in out] == ["旧但最新", "更旧", "无日期"]
