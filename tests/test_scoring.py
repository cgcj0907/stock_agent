"""LLM 评分层测试：解析 / 回退 / 模块接入（不依赖外网）。"""
from __future__ import annotations

from tests.conftest import StubData
from tests.test_decision import _results
from value_agent.agents.base import AgentContext  # 先加载 agents，避免循环导入
from value_agent.core.scoring import llm_score, parse_llm_score
from value_agent.decision.agent import M10DecisionAgent
from value_agent.sessions.models import Session, SessionStatus


class _FakeLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def chat(self, system: str, user: str) -> str:
        return self._text


class _QueuedLLM:
    """按调用顺序返回预设文本（模拟同一模块的定性 + 评分两次调用）。"""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)

    def chat(self, system: str, user: str) -> str:
        return self._texts.pop(0)


class _RecordingLLM:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._text


class _RecordingQueuedLLM:
    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._texts.pop(0)


def _ctx(llm=None) -> AgentContext:
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    return AgentContext(
        session=session, assumptions={}, inputs={}, data=StubData(), llm=llm
    )


# ---------- parse_llm_score ----------
def test_parse_score_valid():
    assert parse_llm_score({"score": 75, "reason": "x"}) == 75
    assert parse_llm_score({"score": "88%"}) == 88
    assert parse_llm_score(60) == 60


def test_parse_score_clamped():
    assert parse_llm_score({"score": 150}) == 100
    assert parse_llm_score({"score": -10}) == 0


def test_parse_score_invalid_returns_default():
    assert parse_llm_score({}) is None
    assert parse_llm_score({"score": "abc"}) is None
    assert parse_llm_score({"score": float("nan")}) is None
    assert parse_llm_score(None) is None
    assert parse_llm_score({"score": None}, default=42) == 42


# ---------- llm_score 辅助 ----------
def test_llm_score_uses_llm_when_valid():
    ctx = _ctx(llm=_FakeLLM('{"score": 82, "reason": "好"}'))
    assert llm_score(ctx, "M1_business_model", facts={"行业": "白酒"}, evidence=["e"], default=50) == 82


def test_llm_score_falls_back_on_invalid():
    ctx = _ctx(llm=_FakeLLM('{"reason": "没有分"}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_falls_back_without_llm():
    ctx = _ctx(llm=None)
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_falls_back_when_disabled(monkeypatch):
    monkeypatch.setattr("value_agent.core.scoring.scoring_enabled", lambda: False)
    ctx = _ctx(llm=_FakeLLM('{"score": 82, "reason": "好"}'))
    assert llm_score(ctx, "M1_business_model", facts={}, evidence=[], default=50) == 50


def test_llm_score_uses_value_investing_prompt():
    llm = _RecordingLLM('{"score": 82, "reason": "好"}')
    ctx = _ctx(llm=llm)

    assert llm_score(ctx, "M1_business_model", facts={"行业": "白酒"}, evidence=["品牌强"], default=50) == 82

    system, user = llm.calls[0]
    assert "格雷厄姆" in system
    assert "费雪" in system
    assert "巴菲特" in system
    assert "芒格" in system
    assert "安全边际" in system
    assert "护城河" in system
    assert "不能因为措辞华丽或叙事动人而给高分" in system
    assert "不得脱离素材臆测" in user


# ---------- M1 接入 ----------
def test_m1_uses_llm_score_and_strips_score_from_qualitative(monkeypatch):
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        '{"business_type": "growth", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"], "references": []}',
        '{"score": 88, "reason": "模式清晰"}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert res.score == 88
    assert res.outputs["business_type"] == "growth"
    assert res.outputs["handoff"]["valuation_route"] == "growth"
    assert "score" not in res.outputs


def test_m1_drops_references_when_tool_empty(monkeypatch):
    """工具拿不到真实链接时，直接移除 references，不展示 LLM 编造的内容。"""
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        ('{"business_type": "growth", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"], '
         '"references": [{"title": "编造的假链接", "url": "https://example.com/fake"}]}'),
        '{"score": 88, "reason": "模式清晰"}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert "references" not in res.outputs


def test_m1_references_use_tool_real_links(monkeypatch):
    """工具抓到的真实链接优先，覆盖 LLM 编造的链接。"""
    from value_agent.business_model.agent import M1BusinessModelAgent

    real_refs = [
        {"title": "2024年年度报告", "url": "https://www.cninfo.com.cn/new/disclosure/detail?a=1"},
    ]
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: real_refs,
    )
    llm = _QueuedLLM([
        ('{"business_type": "growth", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"], '
         '"references": [{"title": "编造的假链接", "url": "https://example.com/fake"}]}'),
        '{"score": 88, "reason": "模式清晰"}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert res.outputs["references"] == real_refs


def test_m1_falls_back_to_rule_business_type_when_llm_missing_type(monkeypatch):
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        '{"business_model": "卖酒", "understandability": "可理解", "reasons": ["r"]}',
        '{"score": 88, "reason": "模式清晰"}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    assert res.outputs["business_type"] == "consumer_monopoly"
    assert res.outputs["handoff"]["valuation_route"] == "consumer_monopoly"


def test_m1_prompt_requires_exclusive_type_judgment(monkeypatch):
    from value_agent.business_model.agent import M1BusinessModelAgent

    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _RecordingQueuedLLM([
        '{"business_type": "growth", "business_model": "卖酒", "understandability": "可理解", "reasons": ["r"]}',
        '{"score": 88, "reason": "模式清晰"}',
    ])
    M1BusinessModelAgent().run(_ctx(llm=llm))
    system, user = llm.calls[0]
    assert "排他判断" in system
    assert "不要把“高增长”直接等同于“成长型”" in system
    assert "为什么是该类型" in user
    assert "为什么不是另一个最相近的类型" in user


# ---------- M10 接入 ----------
def test_m10_llm_score_overrides_total_and_band():
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    session.module_results = _results({f"M{i}": 50.0 for i in range(1, 12)})
    ctx = AgentContext(
        session=session, assumptions={}, inputs={},
        llm=_FakeLLM('{"score": 90, "reason": "综合优秀"}'),
    )
    res = M10DecisionAgent().run(ctx)
    assert res.score == 90
    assert res.outputs["total"] == 90
    assert res.outputs["decision_code"] == "buy"
    assert "强烈关注" in res.outputs["conclusion"]


def test_m10_veto_not_overridden_by_llm():
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    session.module_results = _results(
        {f"M{i}": 90.0 for i in range(1, 12)}, veto=["fraud_signal_hit"]
    )
    ctx = AgentContext(
        session=session, assumptions={}, inputs={},
        llm=_FakeLLM('{"score": 90, "reason": "x"}'),
    )
    res = M10DecisionAgent().run(ctx)
    assert res.outputs["blocked_by_veto"] is True
    assert res.outputs["decision_code"] == "avoid"
    assert res.outputs["conclusion"] == "回避（触发一票否决）"


def test_m1_filters_references_by_llm_indices(monkeypatch):
    """LLM 通过 reference_indices 筛选对 M1 有用的文章，系统按真实链接还原且不落 reference_indices。"""
    from value_agent.business_model.agent import M1BusinessModelAgent

    refs = [
        {"title": "2024年年度报告", "url": "https://www.cninfo.com.cn/a=1"},
        {"title": "茅台提价新闻", "url": "https://finance.eastmoney.com/a=2"},
        {"title": "白酒行业研报", "url": "https://pdf.dfcfw.com/pdf/H3.pdf"},
    ]
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: refs,
    )
    llm = _RecordingQueuedLLM([
        ('{"business_type": "growth", "business_model": "卖酒", "understandability": "可理解", '
         '"reasons": ["r"], "reference_indices": [2, 3]}'),
        '{"score": 88, "reason": "模式清晰"}',
    ])
    res = M1BusinessModelAgent().run(_ctx(llm=llm))
    # 提示词里应包含参考资料清单
    user_prompt = llm.calls[0][1]
    assert "参考资料清单" in user_prompt
    assert "1. 2024年年度报告" in user_prompt
    # 过滤结果：只保留 2、3 号真实链接
    assert [r["title"] for r in res.outputs["references"]] == ["茅台提价新闻", "白酒行业研报"]
    assert "reference_indices" not in res.outputs
