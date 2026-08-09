"""M0 投资者画像智能体 + M1/M8/M9/M10 注入测试（docs/13-investor-profile-agent.md）。

验收红线：
- M0 不在默认工作流；默认流 M1/M8/M9/M10 行为与现状一致（中性兜底）；
- 空画像 → M0 中性降级（degraded），不放大不缩小；
- PII（姓名/邮箱/id）在落库/进 LLM 前剥离；
- M8 门禁 / M9 veto / M10 档位硬约束不被个人画像覆盖。
"""
from __future__ import annotations

import pytest

from tests.conftest import StubData
from value_agent.agents.base import AgentContext
from value_agent.business_model.agent import M1BusinessModelAgent
from value_agent.decision.agent import M10DecisionAgent
from value_agent.decision.engine import run_decision
from value_agent.profile.agent import M0InvestorProfileAgent
from value_agent.profile.engine import (
    derive_injection_params,
    overall_level,
    score_competence,
)
from value_agent.profile.models import (
    PII_FIELDS,
    InvestorProfile,
    parse_investor_profile,
    strip_pii,
)
from value_agent.risk.agent import M9RiskAgent
from value_agent.safety_margin.agent import M8SafetyMarginAgent
from value_agent.safety_margin.engine import run_safety_margin
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus

# 经管硕士·价值型·低风险承受·能力圈[消费,金融] 的典型画像（含 PII 与未知键）
RAW_PROFILE = {
    "display_name": "张三",
    "email": "zhang@example.com",
    "id": "uuid-123",
    "education_level": "master",
    "education_major": "economics",
    "education_note": "金融工程方向，读过 CFA",
    "investment_style": "value",
    "risk_tolerance": "low",
    "holding_period": "long_term",
    "capital_availability": "long_term_idle",
    "income_dependency_level": "low",
    "decision_preference": "margin_of_safety",
    "circle_of_competence": ["consumer", "finance", "bogus_dim"],
    "annual_income_range": "income_50_100",
    "investable_assets_range": "assets_100_300",
    "unknown_key": 123,
}


def _mod(agent_id: str, outputs: dict, score: float = 50.0) -> ModuleResult:
    return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score, outputs=outputs)


def _m0_result(handoff: dict, outputs_extra: dict | None = None) -> ModuleResult:
    outputs = {
        "persona_summary": "测试画像",
        "competence": {"dimensions": {}, "matched_circle": [], "overall_level": handoff.get("competence_level")},
        "handoff": handoff,
    }
    if outputs_extra:
        outputs.update(outputs_extra)
    return _mod("M0_investor_profile", outputs)


# ---- 模型解析 / PII ----
def test_strip_pii_removes_identity_fields():
    stripped = strip_pii(RAW_PROFILE)
    assert not (PII_FIELDS & set(stripped))
    assert "unknown_key" in stripped  # 未知键不删（parse 时忽略），但身份字段必删


def test_parse_whitelist_drops_invalid_enums():
    profile = parse_investor_profile(strip_pii(RAW_PROFILE))
    assert profile.education_level == "master"
    assert profile.education_major == "economics"
    assert profile.investment_style == "value"
    assert profile.circle_of_competence == ["consumer", "finance"]  # bogus_dim 被过滤
    assert profile.education_note == "金融工程方向，读过 CFA"
    bad = parse_investor_profile({"education_level": "phd", "risk_tolerance": "very_high"})
    assert bad.education_level is None and bad.risk_tolerance is None


def test_parse_empty_returns_empty_profile():
    assert parse_investor_profile(None).filled() == []
    assert parse_investor_profile({}).filled() == []


# ---- 能力圈评分 ----
def test_competence_scoring_levels():
    profile = parse_investor_profile(strip_pii(RAW_PROFILE))
    comp = score_competence(profile)
    finance = comp["dimensions"]["finance"]
    assert finance["level"] == "in_circle" and finance["score"] >= 70
    assert "自报能力圈" in "".join(finance["reasons"])
    # 无画像 → 全部默认 55 分 → edge（中性，不放大）
    neutral = score_competence(InvestorProfile())
    assert all(d["level"] == "edge" for d in neutral["dimensions"].values())


def test_overall_level_mapping():
    comp = score_competence(parse_investor_profile(strip_pii(RAW_PROFILE)))
    assert overall_level(comp, "financial") == "high"
    assert overall_level(comp, "cyclical") in ("high", "medium")  # 无周期维度加成也不会是 low（硕士+10）
    # 低学历无能力圈 → 消费 out_circle → 消费垄断公司 low
    low = score_competence(InvestorProfile(education_level="high_school"))
    assert low["dimensions"]["consumer"]["level"] == "out_circle"
    assert overall_level(low, "consumer_monopoly") == "low"
    # 未知生意类型 → None（M1 回退公司侧）
    assert overall_level(comp, None) is None


def test_derive_injection_params():
    profile = parse_investor_profile(strip_pii(RAW_PROFILE))
    comp = score_competence(profile)
    params = derive_injection_params(profile, comp, "financial")
    assert params["competence_level"] == "high"
    assert params["required_discount_adjustment"] == pytest.approx(0.08)  # 低风险0.05+偏好安全边际0.03
    assert params["risk_amplification"]["tone"] == "cautious"
    assert any("风险承受度低" in f for f in params["risk_amplification"]["flags"])
    assert params["position_cap"] is None  # 默认关闭
    assert "education_level" in params["profile_used"]


def test_derive_position_cap_when_enabled(monkeypatch):
    cfg = {"position_cap": {"enabled": 1, "risk_tolerance_low": 0.10, "holding_short": 0.05, "capital_short": 0.05}}
    import value_agent.profile.engine as eng

    monkeypatch.setattr(eng, "_load_config", lambda: {**eng._DEFAULTS, **cfg})
    profile = parse_investor_profile(strip_pii(RAW_PROFILE))
    params = derive_injection_params(profile, score_competence(profile), "financial")
    assert params["position_cap"] == pytest.approx(0.10)


# ---- M0 Agent ----
def _m0_ctx(session: Session, data=None):
    return AgentContext(session=session, assumptions={}, inputs={}, data=data or StubData(), llm=None)


def test_m0_agent_with_profile():
    session = Session(id="s1", company_code="600519", company_name="贵州茅台",
                      status=SessionStatus.CREATED, investor_profile=strip_pii(RAW_PROFILE))
    res = M0InvestorProfileAgent().run(_m0_ctx(session))
    assert res.status.value == "done"
    assert res.outputs["handoff"]["competence_level"] in ("high", "medium", "low")
    assert res.outputs["handoff"]["required_discount_adjustment"] > 0
    assert res.outputs["persona_summary"]
    assert not res.meta.get("degraded")


def test_m0_agent_empty_profile_neutral():
    session = Session(id="s2", company_code="600519", status=SessionStatus.CREATED)
    res = M0InvestorProfileAgent().run(_m0_ctx(session))
    assert res.meta.get("degraded") is True
    assert res.outputs["handoff"]["required_discount_adjustment"] == 0.0
    assert res.outputs["handoff"]["competence_level"] is None
    assert res.outputs["handoff"]["position_cap"] is None


def test_m0_agent_data_failure_still_runs():
    class BoomData(StubData):
        def company_info(self, code):
            raise RuntimeError("boom")

    session = Session(id="s3", company_code="600519", status=SessionStatus.CREATED,
                      investor_profile=strip_pii(RAW_PROFILE))
    res = M0InvestorProfileAgent().run(_m0_ctx(session, data=BoomData()))
    assert res.status.value == "done"  # 数据失败只丢公司维度，个人侧参数仍出


# ---- M1 注入 ----
def _m1_run(m0_result: ModuleResult | None, session_profile: dict | None = None):
    session = Session(id="s4", company_code="600519", company_name="贵州茅台",
                      status=SessionStatus.CREATED, investor_profile=session_profile)
    inputs = {} if m0_result is None else {"M0_investor_profile": m0_result}
    ctx = AgentContext(session=session, assumptions={}, inputs=inputs, data=StubData(), llm=None)
    return M1BusinessModelAgent().run(ctx)


def test_m1_without_m0_unchanged():
    res = _m1_run(None)
    assert res.outputs["understandability"] == "能力圈内（模式直观）"
    assert "personal_understandability_level" not in res.outputs["handoff"]
    assert "understandability_company" not in res.outputs


def test_m1_with_m0_personal_understandability():
    # 高中学历、无能力圈 → 消费维度 out_circle → 个人等级 low
    m0 = _m0_result(
        {"competence_level": "low", "required_discount_adjustment": 0.08,
         "risk_amplification": {"tone": "cautious", "flags": []}, "position_cap": None,
         "profile_used": ["education_level"]},
        outputs_extra={"competence": {
            "dimensions": {"consumer": {"score": 40.0, "level": "out_circle", "reasons": []}},
            "matched_circle": [], "overall_level": "low",
        }},
    )
    res = _m1_run(m0, session_profile={"education_level": "high_school"})
    assert res.outputs["understandability"] == "圈外（超出个人能力圈）"
    assert res.outputs["understandability_company"] == "能力圈内（模式直观）"
    assert res.outputs["handoff"]["understandability_level"] == "low"
    assert res.outputs["handoff"]["personal_understandability_level"] == "low"
    assert any("个人画像注入" in e for e in res.evidence)


def test_m1_with_m0_high_personal_keeps_company():
    m0 = _m0_result(
        {"competence_level": "high", "required_discount_adjustment": 0.0,
         "risk_amplification": {"tone": "neutral", "flags": []}, "position_cap": None,
         "profile_used": ["education_level"]},
        outputs_extra={"competence": {
            "dimensions": {"consumer": {"score": 90.0, "level": "in_circle", "reasons": []}},
            "matched_circle": [], "overall_level": "high",
        }},
    )
    res = _m1_run(m0, session_profile={"education_level": "doctor"})
    # min(公司 high, 个人 high) = high → 不降级，但标签标注「个人画像匹配」；保留公司侧对照与审计
    assert res.outputs["understandability_company"] == "能力圈内（模式直观）"
    assert res.outputs["understandability"] == "能力圈内（个人画像匹配）"
    assert res.outputs["handoff"]["personal_understandability_level"] == "high"


# ---- M8 注入 ----
INTRINSIC = {"low": 56.67, "mid": 111.21, "high": 149.74}


def test_m8_persona_adjustment_applied():
    m8 = M8SafetyMarginAgent()
    session = Session(id="s5", company_code="600519", status=SessionStatus.CREATED)
    inputs = {
        "M4_valuation": _mod("M4_valuation", {
            "intrinsic_value": INTRINSIC, "current_price": 40.0, "business_type": "consumer_monopoly",
        }),
        "M7_market": _mod("M7_market", {}),
        "M0_investor_profile": _m0_result({
            "competence_level": "low", "required_discount_adjustment": 0.05,
            "risk_amplification": {"tone": "cautious", "flags": []}, "position_cap": None,
            "profile_used": [],
        }),
    }
    ctx = AgentContext(session=session, assumptions={}, inputs=inputs, data=None, llm=None)
    res = m8.run(ctx)
    assert res.outputs["required_discount"] == pytest.approx(0.30)  # 0.25 + 0.05
    assert res.outputs["buy_price"] == pytest.approx(56.67 * 0.70, abs=0.01)
    assert any("个人画像注入" in e for e in res.evidence)


def test_m8_without_m0_no_persona_adjustment():
    session = Session(id="s6", company_code="600519", status=SessionStatus.CREATED)
    inputs = {
        "M4_valuation": _mod("M4_valuation", {
            "intrinsic_value": INTRINSIC, "current_price": 40.0, "business_type": "consumer_monopoly",
        }),
        "M7_market": _mod("M7_market", {}),
    }
    ctx = AgentContext(session=session, assumptions={}, inputs=inputs, data=None, llm=None)
    res = M8SafetyMarginAgent().run(ctx)
    assert res.outputs["required_discount"] == 0.25
    assert not any("个人画像注入" in e for e in res.evidence)


def test_m8_engine_persona_clamped():
    res = run_safety_margin(
        price=40.0, intrinsic=INTRINSIC, business_type="consumer_monopoly",
        margin_adjustment=0.0, persona_adjustment=0.5,  # 超上限 → 夹逼 0.6
    )
    assert res.required_discount == pytest.approx(0.60)


# ---- M9 注入 ----
def test_m9_personal_flags_with_m0():
    session = Session(id="s7", company_code="600519", status=SessionStatus.CREATED)
    inputs = {
        "M0_investor_profile": _m0_result({
            "competence_level": "low", "required_discount_adjustment": 0.08,
            "risk_amplification": {"tone": "cautious", "flags": ["超出投资者能力圈，难以独立评估"]},
            "position_cap": None, "profile_used": [],
        }),
    }
    ctx = AgentContext(session=session, assumptions={}, inputs=inputs, data=None, llm=None)
    res = M9RiskAgent().run(ctx)
    assert res.outputs["personal_flags"] == ["超出投资者能力圈，难以独立评估"]
    assert res.outputs["handoff"]["personal_risk_tone"] == "cautious"
    assert any("个人风险提示" in e for e in res.evidence)
    # veto 硬约束未被个人画像触碰
    assert res.outputs["veto"] == []


def test_m9_without_m0_no_personal_flags():
    session = Session(id="s8", company_code="600519", status=SessionStatus.CREATED)
    ctx = AgentContext(session=session, assumptions={}, inputs={}, data=None, llm=None)
    res = M9RiskAgent().run(ctx)
    assert "personal_flags" not in res.outputs


# ---- M10 注入 ----
def _decision_inputs() -> dict[str, ModuleResult]:
    base = {
        "M1_business_model": _mod("M1_business_model", {}, score=80.0),
        "M2_financial_quality": _mod("M2_financial_quality", {}, score=80.0),
        "M3_growth": _mod("M3_growth", {}, score=80.0),
        "M4_valuation": _mod("M4_valuation", {}, score=80.0),
        "M5_moat": _mod("M5_moat", {}, score=80.0),
        "M6_governance": _mod("M6_governance", {}, score=80.0),
        "M7_market": _mod("M7_market", {}, score=80.0),
        "M8_safety_margin": _mod("M8_safety_margin", {"discount": 0.3, "handoff": {"mos_state": "attractive"}}, score=80.0),
        "M9_risk": _mod("M9_risk", {"handoff": {"max_severity": "medium", "veto_flags": []}}, score=80.0),
    }
    return base


def test_run_decision_position_cap_engine():
    res = run_decision(_decision_inputs(), position_cap=0.05)
    assert res.position == pytest.approx(0.05)
    assert any("个人仓位上限" in r for r in res.decision_reasons)


def test_m10_agent_with_m0_cap_when_enabled(monkeypatch):
    import value_agent.profile.engine as eng

    monkeypatch.setattr(
        eng, "_load_config",
        lambda: {**eng._DEFAULTS, "position_cap": {"enabled": 1, "risk_tolerance_low": 0.10,
                                                      "holding_short": 0.05, "capital_short": 0.05}},
    )
    session = Session(id="s9", company_code="600519", status=SessionStatus.CREATED,
                      investor_profile=strip_pii({"risk_tolerance": "low"}))
    m0 = M0InvestorProfileAgent().run(
        AgentContext(session=session, assumptions={}, inputs={}, data=StubData(), llm=None)
    )
    assert m0.outputs["handoff"]["position_cap"] == pytest.approx(0.10)
    inputs = {**_decision_inputs(), "M0_investor_profile": m0}
    ctx = AgentContext(session=session, assumptions={}, inputs=inputs, data=None, llm=None)
    res = M10DecisionAgent().run(ctx)
    assert res.outputs["position"] <= 0.10 + 1e-9


def test_m10_agent_without_m0_position_unchanged():
    session = Session(id="s10", company_code="600519", status=SessionStatus.CREATED)
    ctx = AgentContext(session=session, assumptions={}, inputs=_decision_inputs(), data=None, llm=None)
    res = M10DecisionAgent().run(ctx)
    # 无 M0 → position_cap=None，仓位 = 档位 0.10 × M8(0.9) × M9(0.9) = 0.081，不被个人画像改动
    assert res.outputs["position"] == pytest.approx(0.081)


# ---- 注册与默认工作流 ----
def test_m0_registered_not_in_default_workflow():
    from value_agent.agents.builtin import register_builtin_agents
    from value_agent.agents.registry import AgentRegistry
    from value_agent.workflow.defaults import default_workflow

    reg = register_builtin_agents(AgentRegistry())
    assert reg.has("M0_investor_profile")
    flow = default_workflow()
    assert "M0_investor_profile" not in [s.agent_id for s in flow.steps]


# ---- Session 序列化 ----
def test_session_investor_profile_roundtrip():
    session = Session(id="s11", company_code="600519", status=SessionStatus.CREATED,
                      investor_profile={"education_level": "bachelor"})
    restored = Session.from_dict(session.to_dict())
    assert restored.investor_profile == {"education_level": "bachelor"}
    assert Session(id="s12", company_code="600519").investor_profile is None


def test_overall_level_missing_dims_is_neutral():
    """M0 降级（dimensions 为空/缺维度）→ None，M1 回退公司侧，不误降级。"""
    from value_agent.profile.engine import overall_level

    assert overall_level({"dimensions": {}}, "consumer_monopoly") is None
    assert overall_level({"dimensions": {"consumer": {"level": "in_circle", "score": 90.0, "reasons": []}}},
                         "growth") is None  # growth 需要 technology/healthcare/internet，缺 → 中性


# ---- 输出自描述 manifest 试点（docs/13 §12）----
_MISSING = object()


def _resolve_path(outputs: dict, path: str):
    """按路径取字段；键缺失返回 _MISSING 哨兵（值为 None 不算缺失）。"""
    cur: object = outputs
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def test_m0_manifest_fields_resolve_in_outputs():
    """M0 manifest 声明的字段路径必须真实存在于 M0 输出（防描述与实现漂移）。"""
    from value_agent.agents.base import AgentManifest

    manifest: AgentManifest | None = M0InvestorProfileAgent.spec.manifest
    assert manifest is not None and manifest.how_to_consume
    session = Session(id="s13", company_code="600519", status=SessionStatus.CREATED,
                      investor_profile=strip_pii(RAW_PROFILE))
    res = M0InvestorProfileAgent().run(_m0_ctx(session))
    for path in manifest.output_fields:
        assert _resolve_path(res.outputs, path) is not _MISSING, f"manifest 字段缺失: {path}"
    # 空画像（中性）时字段仍存在（值为 None/空）
    session2 = Session(id="s14", company_code="600519", status=SessionStatus.CREATED)
    res2 = M0InvestorProfileAgent().run(_m0_ctx(session2))
    for path in manifest.output_fields:
        assert _resolve_path(res2.outputs, path) is not _MISSING, f"空画像 manifest 字段缺失: {path}"


def test_format_inputs_for_llm_includes_summary():
    """下游 LLM 提示词可拿到「来源 + 一句话自描述」。"""
    from value_agent.agents.base import format_inputs_for_llm

    m0 = _m0_result({"competence_level": "high"}, outputs_extra={"summary": "投资者画像：个人可理解性评级"})
    m1 = _mod("M1_business_model", {"business_type": "consumer_monopoly"})
    text = format_inputs_for_llm({"M0_investor_profile": m0, "M1_business_model": m1})
    assert "M0_investor_profile" in text and "个人可理解性评级" in text
    assert "M1_business_model" in text  # 无 summary 的模块退化为 id
    assert format_inputs_for_llm({}) == "（无上游输入）"
