"""画像 Planner 测试（docs/12-v2-upgrade.md §4）：schema 校验 / 冲突回退 / M1 接线 / plan 稳定性。"""
from __future__ import annotations

from tests.conftest import StubData
from value_agent.agents.base import AgentContext
from value_agent.planner import (
    PLAN_INVALID,
    parse_profile,
    resolve_profile,
)
from value_agent.planner.validator import stability_rate
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


# ---------- parse_profile（schema 校验） ----------
def test_parse_profile_valid():
    p = parse_profile({
        "business_type": "growth", "financial_subtype": "other", "cyclicality": "medium",
        "primary_metric": "pe", "confidence": "high", "special_flags": ["high_dividend"],
    })
    assert p is not None
    assert p.business_type == "growth"
    assert p.financial_subtype == "other"
    assert p.cyclicality == "medium"
    assert p.primary_metric == "pe"
    assert p.confidence == "high"
    assert p.special_flags == ["high_dividend"]


def test_parse_profile_invalid_returns_none():
    assert parse_profile(None) is None
    assert parse_profile({}) is None
    assert parse_profile({"business_type": "unknown_type"}) is None
    assert parse_profile({"business_type": None}) is None


def test_parse_profile_drops_invalid_enum_fields():
    p = parse_profile({
        "business_type": "financial", "financial_subtype": "FAKE", "cyclicality": "huge",
        "primary_metric": "roe", "confidence": "bogus",
    })
    assert p is not None
    assert p.financial_subtype is None
    assert p.cyclicality is None
    assert p.primary_metric is None
    assert p.confidence == "medium"  # 非法置信度回落默认


# ---------- resolve_profile（冲突回退） ----------
def test_resolve_fallback_rule_when_profile_invalid():
    effective, trace = resolve_profile(
        None, rule_business_type="cyclical", rule_financial_subtype="other"
    )
    assert effective.business_type == "cyclical"
    assert trace.outcome == "fallback_rule"
    assert any(PLAN_INVALID in r for r in trace.reasons)


def test_resolve_conflict_fallback_when_low_confidence():
    profile = parse_profile({"business_type": "growth", "confidence": "medium"})
    effective, trace = resolve_profile(
        profile, rule_business_type="consumer_monopoly", rule_financial_subtype="other"
    )
    assert effective.business_type == "consumer_monopoly"  # 规则胜出
    assert trace.outcome == "conflict_fallback"


def test_resolve_override_when_high_confidence():
    profile = parse_profile({"business_type": "growth", "confidence": "high"})
    effective, trace = resolve_profile(
        profile, rule_business_type="consumer_monopoly", rule_financial_subtype="other"
    )
    assert effective.business_type == "growth"
    assert trace.outcome == "override"


def test_resolve_adopted_when_consistent():
    profile = parse_profile({"business_type": "financial", "confidence": "medium"})
    effective, trace = resolve_profile(
        profile, rule_business_type="financial", rule_financial_subtype="bank"
    )
    assert effective.business_type == "financial"
    assert trace.outcome == "adopted"


def test_resolve_keeps_valid_profile_fields_on_conflict_fallback():
    profile = parse_profile({
        "business_type": "growth", "financial_subtype": "other",
        "cyclicality": "high", "primary_metric": "pb", "confidence": "medium",
    })
    effective, _ = resolve_profile(
        profile, rule_business_type="consumer_monopoly", rule_financial_subtype="other"
    )
    assert effective.business_type == "consumer_monopoly"
    assert effective.cyclicality == "high"   # 非冲突字段保留
    assert effective.primary_metric == "pb"


# ---------- plan 稳定性指标（§9 P4 验收） ----------
def test_stability_rate():
    assert stability_rate(["growth", "growth", "growth"]) == 1.0
    assert stability_rate(["growth", "growth", "cyclical"]) == 0.667
    assert stability_rate([]) == 0.0
    assert stability_rate(["a", "b", "c", "d"]) == 0.25


# ---------- M1 接线 ----------
class _QueuedLLM:
    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)

    def chat(self, system: str, user: str) -> str:
        return self._texts.pop(0)


def _m1_ctx(llm) -> AgentContext:
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    return AgentContext(session=session, assumptions={}, inputs={}, data=StubData(), llm=llm)


def _run_m1(llm) -> ModuleResult:
    from value_agent.business_model.agent import M1BusinessModelAgent

    return M1BusinessModelAgent().run(_m1_ctx(llm))


def test_m1_profile_handoff_with_high_confidence_override(monkeypatch):
    """P4：LLM 高置信画像 → business_type 覆盖规则，画像字段进 handoff + plan_trace。"""
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        ('{"business_type": "growth", "confidence": "high", "financial_subtype": "other", '
         '"cyclicality": "medium", "primary_metric": "pe", "special_flags": ["export_led"], '
         '"business_model": "卖酒", "understandability": "可理解", "reasons": ["r"]}'),
        '{"delta": 0, "reasons": ["合理"]}',
    ])
    res = _run_m1(llm)
    assert res.outputs["business_type"] == "growth"
    handoff = res.outputs["handoff"]
    assert handoff["primary_metric"] == "pe"
    assert handoff["cyclicality"] == "medium"
    assert handoff["plan_trace"]["outcome"] == "override"
    assert handoff["plan_trace"]["adopted_business_type"] == "growth"


def test_m1_profile_conflict_fallback_to_rule(monkeypatch):
    """P4：LLM 与规则冲突且置信度不足 → business_type 回退规则（白酒→consumer_monopoly）。"""
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        ('{"business_type": "growth", "confidence": "medium", "business_model": "卖酒", '
         '"understandability": "可理解", "reasons": ["r"]}'),
        '{"delta": 0, "reasons": ["合理"]}',
    ])
    res = _run_m1(llm)
    assert res.outputs["business_type"] == "consumer_monopoly"  # 规则胜出
    assert res.outputs["handoff"]["valuation_route"] == "consumer_monopoly"
    assert res.outputs["handoff"]["plan_trace"]["outcome"] == "conflict_fallback"
    assert any("回退规则" in e for e in res.evidence)


def test_m1_no_llm_no_profile_keys(monkeypatch):
    """无 LLM → 画像字段不进 handoff（保持旧行为）。"""
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    res = _run_m1(None)
    assert "plan_trace" not in res.outputs["handoff"]
    assert "primary_metric" not in res.outputs["handoff"]


# ---------- M4 接线（画像路由落审计） ----------
def test_m4_records_plan_note_in_evidence():
    from value_agent.valuation.agent import M4ValuationAgent

    m1 = ModuleResult(
        module="M1_business_model", status=ModuleStatus.DONE, score=80.0,
        outputs={
            "business_type": "consumer_monopoly",
            "industry": "白酒",
            "handoff": {
                "valuation_route": "consumer_monopoly",
                "financial_subtype": "other",
                "plan_trace": {"outcome": "adopted", "reasons": ["r"], "adopted_business_type": "consumer_monopoly"},
            },
        },
    )
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    ctx = AgentContext(session=session, assumptions={}, inputs={"M1_business_model": m1}, data=StubData())
    res = M4ValuationAgent().run(ctx)
    assert res.status.value == "done"
    assert any("M1 画像路由" in e and "plan=adopted" in e for e in res.evidence)


# ---------- v2 P5 接线：画像 → meta.completeness → 校准上限 ----------
def test_m1_meta_completeness_reflects_plan_outcome(monkeypatch):
    """P5：plan 采纳 → completeness high；冲突回退 → medium。"""
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    # 高置信覆盖 → adopted/override → high
    llm = _QueuedLLM([
        ('{"business_type": "growth", "confidence": "high", "business_model": "卖酒", '
         '"understandability": "可理解", "reasons": ["r"]}'),
        '{"delta": 0, "reasons": ["合理"]}',
    ])
    res = _run_m1(llm)
    assert res.meta["completeness"] == "high"

    # 冲突回退 → medium
    llm = _QueuedLLM([
        ('{"business_type": "growth", "confidence": "medium", "business_model": "卖酒", '
         '"understandability": "可理解", "reasons": ["r"]}'),
        '{"delta": 0, "reasons": ["合理"]}',
    ])
    res = _run_m1(llm)
    assert res.meta["completeness"] == "medium"


def test_m1_calibration_cap_tightened_by_high_completeness(monkeypatch):
    """P5 接线闭环：plan 采纳（completeness=high）→ 校准上限 ±5 → 超限 delta 被截断。"""
    monkeypatch.setattr(
        "value_agent.business_model.agent.CompanyReferences.fetch",
        lambda self, code, limit=5, slot=0: [],
    )
    llm = _QueuedLLM([
        ('{"business_type": "growth", "confidence": "high", "business_model": "卖酒", '
         '"understandability": "可理解", "reasons": ["r"]}'),
        '{"delta": -12, "reasons": ["模式清晰"]}',
    ])
    res = _run_m1(llm)
    assert res.meta["completeness"] == "high"
    assert res.score == 95  # 规则 100 + delta -12 → 截断至 -5
    assert res.calibration["outcome"] == "capped"
    assert any("截断" in n for n in res.calibration["notes"])
