"""M10 决策引擎 + Agent 单元测试：五维加权 / 档位边界 / 一票否决 / M8 门禁 / 契约输出。"""
import pytest

from value_agent.agents.base import AgentContext
from value_agent.decision.agent import M10DecisionAgent
from value_agent.decision.engine import run_decision
from value_agent.sessions import ModuleName
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


def _all_modules(score: float) -> dict[str, float]:
    """全部 11 个模块同分（用真实 agent id）。"""
    return {ModuleName[f"M{i}"].value: score for i in range(1, 12)}


def _results(scores: dict[str, float], veto: list[str] | None = None) -> dict[str, ModuleResult]:
    res = {}
    for agent_id, score in scores.items():
        res[agent_id] = ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score)
    if veto is not None:
        res["M9_risk"] = ModuleResult(
            module="M9_risk", status=ModuleStatus.DONE, score=50, outputs={"veto": veto}
        )
    return res


def test_all_stub_neutral_around_50():
    # 全部模块 50 分 → 加权总分约 50，落入"中性/观察"
    r = run_decision(_results(_all_modules(50.0)))
    assert r.total == pytest.approx(50.0, abs=0.1)
    assert "中性" in r.conclusion
    assert r.decision_code == "watch"
    assert r.blocked_by_veto is False


def test_excellent_scores_hit_strong_band():
    r = run_decision(_results(_all_modules(90.0)))
    assert r.total >= 80
    assert "强烈关注" in r.conclusion
    assert r.decision_code == "buy"
    assert r.position == 0.10


def test_poor_scores_avoid():
    r = run_decision(_results(_all_modules(20.0)))
    assert r.total < 50
    assert r.conclusion == "回避"
    assert r.decision_code == "avoid"
    assert r.position == 0.0


def test_veto_forces_avoid():
    r = run_decision(_results({f"M{i}": 90.0 for i in range(1, 12)}, veto=["fraud_signal_hit"]))
    assert r.conclusion == "回避（触发一票否决）"
    assert r.decision_code == "avoid"
    assert r.blocked_by_veto is True
    assert r.position == 0.0
    assert r.vetoed == ["fraud_signal_hit"]



def test_veto_via_handoff_veto_flags():
    """契约：M9 输出 handoff.veto_flags（否决 id），M10 经 vetoes[] 解析成 reason 显示。"""
    scores = {ModuleName[f"M{i}"].value: 90.0 for i in range(1, 12)}
    scores["M9_risk"] = 50.0
    res = {
        aid: ModuleResult(module=aid, status=ModuleStatus.DONE, score=sc)
        for aid, sc in scores.items()
    }
    res["M9_risk"] = ModuleResult(
        module="M9_risk", status=ModuleStatus.DONE, score=50,
        outputs={
            "vetoes": [{"id": "V-003", "reason": "审计非标（意见非标）", "severity": "critical"}],
            "veto": [],  # 旧兼容字段为空，必须走 handoff.veto_flags
            "handoff": {
                "veto_flags": ["V-003"],
                "max_severity": "critical",
                "monitor_candidates": [],
            },
        },
    )
    r = run_decision(res)
    assert r.blocked_by_veto is True
    assert r.decision_code == "avoid"
    assert r.position == 0.0
    assert r.vetoed == ["审计非标（意见非标）"]


def test_dimension_weights_applied():
    # M2=100、M4/M8=100、其余 0 → 财务(20%) + 估值(25%) 贡献
    scores = {f"M{i}": 0.0 for i in range(1, 12)}
    scores["M2_financial_quality"] = 100.0
    scores["M4_valuation"] = 100.0
    scores["M8_safety_margin"] = 100.0
    r = run_decision(_results(scores))
    assert r.dimensions["financial_quality"] == 100.0
    assert r.dimensions["valuation_margin"] == pytest.approx(100.0)
    assert r.total == pytest.approx(45.0, abs=0.1)  # 20% + 25%


def test_m8_expensive_blocks_buy():
    """M8 mos_state=expensive（现价高于内在价值）→ 即便全模块 90 分也不给 buy，降为 watch。"""
    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = ModuleResult(
        module="M8_safety_margin", status=ModuleStatus.DONE, score=10,
        outputs={"mos_state": "expensive", "handoff": {"mos_state": "expensive"}},
    )
    r = run_decision(res)
    assert r.decision_code == "watch"
    assert "关注" in r.conclusion
    assert r.position == 0.05
    assert any("M8 安全边际" in e for e in r.evidence)


def test_m8_attractive_keeps_buy():
    """M8 mos_state=attractive → 高分组照常给 buy（门禁只在 expensive 生效）。"""
    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = ModuleResult(
        module="M8_safety_margin", status=ModuleStatus.DONE, score=95,
        outputs={"mos_state": "attractive", "handoff": {"mos_state": "attractive"}},
    )
    r = run_decision(res)
    assert r.decision_code == "buy"
    assert r.position == 0.10


# ---------- M10DecisionAgent 层（真实 Agent 输出，含 LLM 校准） ----------

def _m10_ctx(results: dict, llm=None) -> AgentContext:
    """按契约组装 M10 上下文：ctx.inputs 只含 spec.inputs 声明的模块。"""
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    session.module_results = results
    inputs = {aid: results[aid] for aid in results if aid in M10DecisionAgent.spec.inputs}
    return AgentContext(session=session, assumptions={}, inputs=inputs, llm=llm)


class _FakeLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def chat(self, system: str, user: str) -> str:
        return self._text


def _expensive_m8() -> ModuleResult:
    return ModuleResult(
        module="M8_safety_margin", status=ModuleStatus.DONE, score=10,
        outputs={"mos_state": "expensive", "handoff": {"mos_state": "expensive"}},
    )


def _attractive_m8() -> ModuleResult:
    return ModuleResult(
        module="M8_safety_margin", status=ModuleStatus.DONE, score=95,
        outputs={"mos_state": "attractive", "handoff": {"mos_state": "attractive"}},
    )


def test_agent_preserves_m8_expensive_gate_without_llm():
    """回归：引擎已把 buy 降为 watch，agent 层按同总分重算时不得冲回 buy。"""
    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = _expensive_m8()  # M8 分 10 → valuation 维度被拉低
    out = M10DecisionAgent().run(_m10_ctx(res)).outputs
    assert out["total"] == pytest.approx(83.3, abs=0.1)  # ≥80 本应 buy，门禁降 watch
    assert out["decision_code"] == "watch"
    assert out["position"] == 0.05
    assert "安全边际不足" in out["conclusion"]


def test_agent_llm_cannot_override_m8_expensive_gate():
    """高优先级回归：LLM 校准不得覆盖 M8 安全边际门禁。

    8.1 幅度保护：规则分 ~46.7（M8=10 拉低估值维度），LLM 抬到 90 超 ±15 → 回退规则分；
    即便分数足够，mos_state=expensive 仍强制 watch（门禁在最终输出形状下依然成立）。
    """
    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = _expensive_m8()
    result = M10DecisionAgent().run(
        _m10_ctx(res, llm=_FakeLLM('{"score": 90, "reason": "综合优秀"}'))
    )
    out = result.outputs
    assert out["total"] == 90.0  # LLM 校准 90 在 ±15 内生效（规则分 ~83.3）
    assert out["decision_code"] == "watch"  # 门禁仍在（buy → watch，LLM 不得覆盖）
    assert out["position"] == 0.05
    assert "安全边际不足" in out["conclusion"]
    assert any("M8 安全边际" in e for e in result.evidence)


def test_agent_keeps_buy_when_m8_attractive():
    """M8 attractive（安全边际充足）→ 高分组照常 buy，门禁只在 expensive 生效。"""
    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = _attractive_m8()
    out = M10DecisionAgent().run(_m10_ctx(res)).outputs
    assert out["decision_code"] == "buy"
    assert out["position"] == 0.10


def test_agent_outputs_contract_handoff_and_reasons():
    """契约 §4 M10：handoff + qualitative.decision_reasons 存在且与顶层结论一致。"""
    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = _attractive_m8()
    out = M10DecisionAgent().run(_m10_ctx(res)).outputs
    assert out["handoff"] == {
        "decision_code": "buy",
        "blocked_by_veto": False,
        "position": 0.10,
    }
    reasons = out["qualitative"]["decision_reasons"]
    assert isinstance(reasons, list) and reasons
    assert any("加权总分" in r for r in reasons)
    # 契约枚举兜底断言（O-5 稳定性）
    assert out["decision_code"] in ("buy", "watch", "avoid")


def test_agent_consumes_only_ctx_inputs_declared_modules():
    """模块边界：只消费 ctx.inputs 里的声明模块，session 全量结果不混入。"""
    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    all90 = _results(_all_modules(90.0))
    session.module_results = all90
    subset = {
        aid: all90[aid]
        for aid in ("M2_financial_quality", "M4_valuation", "M8_safety_margin")
    }
    ctx = AgentContext(session=session, assumptions={}, inputs=subset)
    out = M10DecisionAgent().run(ctx).outputs
    # 仅 20% 财务 + 25% 估值（valuation 维度 = M4/M8 平均 90）→ 40.5 < 50 → avoid
    assert out["total"] == pytest.approx(40.5, abs=0.1)
    assert out["decision_code"] == "avoid"


# ---------- backlog 8.x：仓位联动 / 校准保护 / core_facts / LLM 理由 ----------

def test_position_sized_by_margin_and_risk():
    """8.2：仓位 = 档位基准 × M8 安全边际修正 × M9 风险修正（夹逼 [0, 25%]）。"""
    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = ModuleResult(
        module="M8_safety_margin", status=ModuleStatus.DONE, score=95,
        outputs={"discount": 0.5, "handoff": {"mos_state": "attractive"}},
    )
    res["M9_risk"] = ModuleResult(
        module="M9_risk", status=ModuleStatus.DONE, score=80,
        outputs={"handoff": {"max_severity": "high"}},
    )
    r = run_decision(res)
    # 0.10 × 1.0（discount≥0.4） × 0.7（high） = 0.07
    assert r.position == pytest.approx(0.07, abs=0.001)
    assert any("仓位依据" in reason for reason in r.decision_reasons)


def test_calibration_cap_falls_back_to_rule_score():
    """8.1：校准超 ±15 → 回退规则分（78 分不会被抬到 82 跨档）。"""
    res = _results(_all_modules(78.0))
    r = run_decision(res, total_override=82.0)  # 78 → 82，delta 4 在限内
    assert r.total == 82.0 and r.calibration_capped is False
    r2 = run_decision(res, total_override=95.0)  # 78 → 95，delta 17 超限
    assert r2.total == pytest.approx(78.0, abs=0.1)
    assert r2.calibration_capped is True
    assert any("回退" in e for e in r2.evidence)


def test_governance_dimension_uses_m6_only():
    """8.7：governance_risk 维度 = M6 为主（M9 分数不再与 M6 平均）。"""
    res = _results(_all_modules(50.0))
    res["M6_governance"] = ModuleResult(module="M6_governance", status=ModuleStatus.DONE, score=80)
    res["M9_risk"] = ModuleResult(module="M9_risk", status=ModuleStatus.DONE, score=10)
    r = run_decision(res)
    assert r.dimensions["governance_risk"] == 80.0  # 不被 M9=10 拉低


def test_agent_outputs_core_facts_and_llm_reasons():
    """8.7 core_facts 分组 + 8.3 LLM 定性理由并入 decision_reasons。"""
    class _ReasonLLM(_FakeLLM):
        def chat(self, system: str, user: str) -> str:
            if "reasons" in user:
                return '{"reasons": ["估值保护充分", "治理风险已被定价"]}'
            return '{"score": 88, "reason": "综合优秀"}'

    res = _results(_all_modules(90.0))
    res["M8_safety_margin"] = _attractive_m8()
    out = M10DecisionAgent().run(_m10_ctx(res, llm=_ReasonLLM(""))).outputs
    assert out["core_facts"] == {
        "decision": "buy",
        "position": out["position"],
        "dimension_scores": out["dimensions"],
        "total": out["total"],
    }
    reasons = out["qualitative"]["decision_reasons"]
    assert any("LLM 复核" in r for r in reasons)
