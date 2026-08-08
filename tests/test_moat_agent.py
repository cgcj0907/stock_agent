"""M5 护城河智能体 LLM 集成测试：两层合成 / handoff 回填 / 宽度冲突 / 无 LLM 退化。

重点回归（对应 docs/09-module-contracts.md §4 M5 两层制）：
- LLM 定性结果真正回填 handoff.moat_durability / erosion_risks（M9 消费）；
- LLM width 与规则层冲突时显式标记（width_source / width_conflict），不静默并存；
- 未配置 LLM 时完全退化为规则代理评级（字段集合一致）。
"""
from __future__ import annotations

from tests.conftest import StubData
from value_agent.agents.base import AgentContext
from value_agent.moat.agent import M5MoatAgent
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


class _FakeLLM:
    """流式 + 阻塞双实现：qualitative 为 LLM 定性 JSON，score 为 llm_score 的评分 JSON。"""

    def __init__(self, qualitative: str, score: str = '{"delta": 0, "reasons": ["ok"]}'):
        self._qualitative = qualitative
        self._score = score

    def chat(self, system, user):
        return self._score

    def stream_chat(self, system, user):
        yield "content", self._qualitative


class _NoRefs:
    """不联网的 CompanyReferences 替身（单测里 references.fetch 不应触发网络）。"""

    def fetch(self, code, slot=0):
        return []


class _NeutralData(StubData):
    """行业为空的数据桩：不命中任何行业细分，用于验证 M1 business_type 软读。"""

    def company_info(self, code: str) -> dict:
        return {"name": f"测试公司{code}", "industry": "", "code": code}


def _run(monkeypatch, llm, *, business_type=None, data=None):
    monkeypatch.setattr("value_agent.moat.agent.CompanyReferences", _NoRefs)
    session = Session(id="s1", company_code="600519", company_name="贵州茅台", status=SessionStatus.CREATED)
    inputs = {}
    if business_type:
        inputs["M1_business_model"] = ModuleResult(
            module="M1_business_model", status=ModuleStatus.DONE, score=60.0,
            outputs={"business_type": business_type},
        )
    ctx = AgentContext(
        session=session, assumptions={}, inputs=inputs,
        data=data or StubData(), llm=llm,
    )
    return M5MoatAgent().run(ctx)


def test_llm_qualitative_backfills_handoff(monkeypatch):
    """LLM 合法输出 → 回填 durability/erosion_risks，width 采用 LLM 并标记冲突。"""
    llm = _FakeLLM(
        '{"moat_sources": ["无形资产", "网络效应"], "width": "宽", "durability": "high", '
        '"trend": "stable", "erosion_risks": ["新进入者低价竞争"], '
        '"competition_evidence": ["品牌力强、提价能力强", "市占率长期领先"], '
        '"evidence": ["品牌力强，提价能力强"], "reference_indices": []}'
    )
    res = _run(monkeypatch, llm)
    assert res.status.value == "done"
    # 两层合成：StubData(ROE18/GM45/杠杆0.35, 白酒) 规则代理=窄（白酒细分基准 GM 中位 70）；
    # LLM=宽（附竞争优势证据）→ 采用 LLM + 冲突标记
    assert res.outputs["width"] == "宽"
    assert res.outputs["width_source"] == "llm"
    assert res.outputs["width_conflict"] is True
    assert res.outputs["rule_proxy"]["tier"] == "窄"
    # handoff 真正回填（M9 消费）
    assert res.outputs["handoff"]["moat_width"] == "wide"
    assert res.outputs["handoff"]["moat_durability"] == "high"
    assert res.outputs["handoff"]["moat_trend"] == "stable"  # LLM trend 回填
    assert res.outputs["handoff"]["erosion_risks"] == ["新进入者低价竞争"]
    # LLM 定性字段清洗保留
    assert res.outputs["llm_qualitative"]["moat_sources"] == ["无形资产", "网络效应"]
    assert any("宽度冲突" in e for e in res.evidence)


def test_llm_invalid_fields_fall_back_to_rule(monkeypatch):
    """LLM 字段越界/非法 → 全部丢弃，回退规则代理评级与规则映射的 handoff。"""
    llm = _FakeLLM(
        '{"moat_sources": ["胡诌来源"], "width": "超级宽", "durability": "very_high", '
        '"erosion_risks": "not a list", "evidence": 123}'
    )
    res = _run(monkeypatch, llm)
    assert res.outputs["width"] == "窄"          # 规则代理档位（白酒细分基准）
    assert res.outputs["width_source"] == "rule_proxy"
    assert res.outputs["width_conflict"] is False
    assert res.outputs["handoff"]["moat_durability"] == "low"  # 规则映射：窄→low
    assert res.outputs["handoff"]["erosion_risks"] == []       # Stub 数据稳定，规则无侵蚀信号
    assert "llm_qualitative" not in res.outputs                # 字段全非法 → 不写入
    assert any("字段全部非法" in e for e in res.evidence)


def test_llm_width_match_no_conflict(monkeypatch):
    """LLM 宽度与规则一致 → 采用 LLM 但无冲突标记。"""
    llm = _FakeLLM('{"width": "窄", "durability": "low", "erosion_risks": []}')
    res = _run(monkeypatch, llm)
    assert res.outputs["width"] == "窄"
    assert res.outputs["width_source"] == "llm"
    assert res.outputs["width_conflict"] is False


def test_no_llm_uses_rule_proxy_only(monkeypatch):
    """未配置 LLM → 完全退化为规则代理评级，字段集合与正常态一致。"""
    res = _run(monkeypatch, None)
    assert res.outputs["width"] == "窄"
    assert res.outputs["width_source"] == "rule_proxy"
    assert res.outputs["width_conflict"] is False
    assert res.outputs["handoff"]["moat_width"] == "narrow"
    assert res.outputs["handoff"]["moat_durability"] == "low"
    assert res.outputs["handoff"]["moat_trend"] == "stable"  # 规则层无侵蚀信号 → stable
    assert res.outputs["handoff"]["erosion_risks"] == []
    assert res.outputs["rule_proxy"]["peer"]["benchmark"] == "liquor"  # 白酒→白酒细分基准
    assert res.outputs["rule_proxy"]["peer"]["margin_median"] == 70.0
    assert any("未配置 LLM" in e for e in res.evidence)


def test_llm_conflict_without_competitive_evidence_falls_back(monkeypatch):
    """LLM 宽度与规则冲突但只给了市场情绪类理由 → 宽度不采纳，回退规则层（仍回填 sources/erosion）。"""
    llm = _FakeLLM(
        '{"moat_sources": ["成本优势"], "width": "宽", "durability": "medium", '
        '"erosion_risks": ["行业竞争加剧"], '
        '"competition_evidence": [], '
        '"evidence": ["主力资金净流入、股价上涨"], "reference_indices": []}'
    )
    res = _run(monkeypatch, llm)
    assert res.outputs["width"] == "窄"              # 规则代理（未采纳 LLM 的宽）
    assert res.outputs["width_source"] == "rule_proxy"
    assert res.outputs["width_conflict"] is False
    # 定性内容仍回填（sources/erosion），只是不参与宽度
    assert res.outputs["llm_qualitative"]["moat_sources"] == ["成本优势"]
    assert res.outputs["handoff"]["moat_durability"] == "medium"
    assert res.outputs["handoff"]["erosion_risks"] == ["行业竞争加剧"]
    assert any("未给出竞争优势类证据" in e for e in res.evidence)


def test_rule_erosion_signals_map_to_eroding_trend(monkeypatch):
    """规则层侵蚀信号非空 → handoff.moat_trend=eroding（LLM 缺省时喂给 M9）。"""
    class _DecliningData(StubData):
        def financials(self, code: str, years: int = 10) -> dict:
            # 最新期(2026) ROE 最低、持续下滑 → 触发规则层侵蚀信号
            recs = [{"period": f"{2026 - i}1231", "roe": 6.5 + i * 1.5,
                     "grossprofit_margin": 45.0, "netprofit_margin": 25.0,
                     "debt_to_assets": 0.35} for i in range(10)]
            return {"records": recs}

    res = _run(monkeypatch, None, data=_DecliningData())
    assert res.outputs["rule_proxy"]["erosion_signals"], "下滑数据应触发规则侵蚀信号"
    assert res.outputs["handoff"]["moat_trend"] == "eroding"


def test_filter_competitive_refs_drops_sentiment_news():
    """参考池过滤：资金面/情绪类新闻（净流入/特大单/主力资金）不能作为护城河证据。"""
    from value_agent.moat.agent import _filter_competitive_refs

    refs = [
        {"title": "5.63亿主力资金净流入，中船系概念涨2.85%", "url": "http://a"},
        {"title": "32股特大单净流入资金超2亿元", "url": "http://b"},
        {"title": "中国船舶：在手订单排至2028年，LNG船占比提升", "url": "http://c"},
        {"title": "船舶行业景气持续，造船产能供不应求", "url": "http://d"},
    ]
    kept = _filter_competitive_refs(refs)
    assert [r["title"] for r in kept] == [
        "中国船舶：在手订单排至2028年，LNG船占比提升",
        "船舶行业景气持续，造船产能供不应求",
    ]


def test_m1_business_type_soft_read(monkeypatch):
    """M1 已运行（business_type=financial）且行业无细分命中 → 规则层用金融基准（净利率口径）。"""
    res = _run(monkeypatch, None, business_type="financial", data=_NeutralData())
    assert res.outputs["rule_proxy"]["peer"]["benchmark"] == "financial"
    assert res.outputs["rule_proxy"]["peer"]["margin_key"] == "netprofit_margin"


# ---------- backlog 5.x：证据校验 / 情绪词表 / 跨周期窗口 ----------

def test_competition_evidence_rejects_sentiment_and_non_category():
    """5.10：竞争优势证据必须带类别关键词（订单/份额/成本/技术/客户…），情绪/股价表述剔除。"""
    from value_agent.moat.agent import _validate_competition_evidence

    good = _validate_competition_evidence([
        "在手订单饱满，市占率提升",
        "股价连续上涨，主力资金净流入",   # 情绪 → 剔除
        "机构评级买入",                    # 无类别关键词 → 剔除
        "专利壁垒与客户转换成本高",
    ])
    assert "在手订单饱满，市占率提升" in good
    assert "专利壁垒与客户转换成本高" in good
    assert all("资金" not in x and "机构" not in x for x in good)


def test_sentiment_title_regex_covers_new_phrases():
    """5.11：参考池过滤词表补充（蹭概念/涨停潮/吸筹等）。"""
    from value_agent.moat.agent import _SENTIMENT_TITLE_RE

    for title in ("公司蹭概念炒作", "板块涨停潮来袭", "主力吸筹迹象明显", "游资拉升异动"):
        assert _SENTIMENT_TITLE_RE.search(title), title
    assert not _SENTIMENT_TITLE_RE.search("公司发布年度订单数据")


def test_moat_cross_cycle_margin_debt_window():
    """5.7：周期行业利润率/杠杆也取近 8 年跨周期均值参与相对评分。"""
    from value_agent.moat.engine import assess_moat

    # 最新期毛利率/杠杆处于极端值，但 8 年均值温和
    gms = [45, 40, 38, 36, 34, 32, 30, 28, 26, 24]
    debts = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.9, 0.9]
    recs = [
        {"period": f"{2026 - i}1231", "roe": 10.0, "grossprofit_margin": gm,
         "debt_to_assets": d}
        for i, (gm, d) in enumerate(zip(gms, debts))
    ]
    r = assess_moat({"records": recs}, industry="钢铁", business_type="cyclical")
    assert r.peer is not None
    assert any("跨周期均值" in s for s in r.signals)
    # 最新毛利率 24 vs 8 年均值 ~34.6 → 用均值（≥34.6 分位段）
    assert r.peer.margin_company is not None and r.peer.margin_company > 30
    # 最新杠杆 0.9 vs 8 年均值 ~0.55 → 用均值
    assert r.peer.debt_company is not None and r.peer.debt_company < 0.7
