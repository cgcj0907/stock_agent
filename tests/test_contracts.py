"""统一模块契约测试（批次 A，docs/09-module-contracts.md §8）。

覆盖：契约常量 / 枚举对齐 / RiskSignal / meta 校验 / ModuleResult.meta 往返 /
工作流依赖声明对齐（防 §1.1 的 handoff 断点回归）。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from value_agent.agents.builtin import register_builtin_agents
from value_agent.agents.registry import AgentRegistry
from value_agent.core.contracts import (
    OUTPUT_KEYS,
    SCHEMA_VERSION,
    BusinessType,
    ReasonCode,
    RiskSignal,
    build_meta,
    default_meta,
    is_valid_meta,
    is_valid_signal,
    validate_meta,
    validate_signal,
)
from value_agent.sessions import ModuleName
from value_agent.sessions.manager import MODULE_DEPENDENCIES
from value_agent.sessions.models import ModuleResult, ModuleStatus
from value_agent.workflow import load_workflow_from_yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
DEFAULT_WF = CONFIG_DIR / "workflows" / "default.yaml"


# ---- 常量与枚举 ----
def test_schema_version_and_output_keys():
    assert SCHEMA_VERSION == "1.0"
    assert OUTPUT_KEYS == (
        "schema_version",
        "module_type",
        "core_facts",
        "qualitative",
        "signals",
        "handoff",
        "meta",
    )


def test_business_type_enum_aligns_with_valuation_routing():
    """M1 生意类型枚举与 config/valuation_routing.yaml 的路由键一一对应。"""
    with open(CONFIG_DIR / "valuation_routing.yaml", encoding="utf-8") as f:
        routing_keys = set(yaml.safe_load(f)["routing"].keys())
    assert {b.value for b in BusinessType} == routing_keys


def test_reason_codes_cover_common_degradation_paths():
    assert ReasonCode.DATA_UNAVAILABLE.value == "DATA_UNAVAILABLE"
    assert ReasonCode.INPUT_MISSING.value == "INPUT_MISSING"
    assert ReasonCode.LLM_UNAVAILABLE.value == "LLM_UNAVAILABLE"
    # §4 M8：现价高于内在价值上沿的 reason code（此前文档有、枚举缺失）
    assert ReasonCode.PRICE_ABOVE_INTRINSIC.value == "PRICE_ABOVE_INTRINSIC"
    assert is_valid_meta(build_meta(0.8, "high", reason_codes=["PRICE_ABOVE_INTRINSIC"]))


# ---- RiskSignal ----
def test_risk_signal_validation():
    ok = RiskSignal(
        code="OCF_NP_DIVERGENCE",
        severity="medium",
        metric="ocf_to_np_min",
        message="经营现金流/净利润最低 0.62",
        evidence="M2_financial_quality: 2023-12-31 ~ 2024-12-31",
    )
    assert is_valid_signal(ok)
    assert validate_signal(ok.to_dict()) == []

    bad = RiskSignal(code="", severity="fatal", metric="", message="")
    assert not is_valid_signal(bad)
    joined = " ".join(validate_signal(bad))
    assert "fatal" in joined
    assert "code" in joined


# ---- meta ----
def test_default_meta_is_valid():
    m = default_meta()
    assert is_valid_meta(m)
    assert m["completeness"] == "low"
    assert m["reason_codes"] == []


def test_build_meta_clamps_confidence_and_enum():
    assert build_meta(1.7)["confidence"] == 1.0
    assert build_meta(-0.2)["confidence"] == 0.0
    assert build_meta(0.8, "not-an-enum")["completeness"] == "low"
    assert is_valid_meta(build_meta(0.8, "high"))


def test_validate_meta_detects_bad_values():
    bad = {
        "confidence": 1.5,
        "completeness": "bad",
        "degraded": True,
        "reason_codes": ["UNKNOWN"],
    }
    errors = validate_meta(bad)
    assert errors
    joined = " ".join(errors)
    assert "confidence" in joined and "completeness" in joined and "UNKNOWN" in joined


# ---- ModuleResult.meta 往返 ----
def test_module_result_meta_roundtrip():
    meta = build_meta(0.9, "high", degraded=False)
    r = ModuleResult(
        module="M2_financial_quality",
        status=ModuleStatus.DONE,
        meta=meta,
    )
    d = r.to_dict()
    assert d["meta"] == meta
    r2 = ModuleResult.from_dict(d)
    assert r2.meta == meta


def test_module_result_meta_default_for_old_payloads():
    """旧数据没有 meta 时，from_dict 回退为空 dict（不报错）。"""
    r = ModuleResult.from_dict({"module": "M1_business_model", "status": "done"})
    assert r.meta == {}


# ---- 工作流依赖声明对齐（防 §1.1 handoff 断点回归）----
def _yaml_deps_by_agent() -> dict[str, set[str]]:
    wf = load_workflow_from_yaml(str(DEFAULT_WF))
    agent_of = {s.id: s.agent_id for s in wf.steps}
    deps_by_agent: dict[str, set[str]] = {}
    for s in wf.steps:
        deps_by_agent[s.agent_id] = {agent_of[d] for d in s.deps}
    return deps_by_agent


def test_yaml_default_deps_match_module_dependencies():
    """config/workflows/default.yaml 的 deps 必须与 MODULE_DEPENDENCIES 一致。"""
    deps_by_agent = _yaml_deps_by_agent()
    for module, deps in MODULE_DEPENDENCIES.items():
        assert deps_by_agent[module.value] == {
            d.value for d in deps
        }, f"{module.value} 的 YAML deps 与 MODULE_DEPENDENCIES 不一致（handoff 断点）"


def test_decision_snapshot_recorded(stub_data):
    """O-3 输出快照审计：M10 完成后写结构化决策快照（含输入 handoff 摘要）。"""
    from value_agent.agents.builtin import register_builtin_agents
    from value_agent.agents.registry import AgentRegistry
    from value_agent.sessions import InMemoryStore, SessionManager
    from value_agent.workflow import WorkflowEngine, default_workflow

    reg = register_builtin_agents(AgentRegistry())
    engine = WorkflowEngine(reg, SessionManager(InMemoryStore()), data=stub_data)
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    engine.run(session, default_workflow())

    snaps = session.decision_snapshots
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap["decision_code"] in ("buy", "watch", "avoid")
    assert {"session_id", "company_code", "created_at", "total", "position",
            "blocked_by_veto", "dimensions", "inputs", "meta"} <= set(snap)
    # 8.6：快照纳入 decision_reasons + handoff（审计可回放「为什么是这个结论」）
    assert snap.get("decision_reasons") is not None
    assert snap.get("handoff", {}).get("decision_code") == snap["decision_code"]
    assert "M4_valuation" in snap["inputs"]
    assert "M8_safety_margin" in snap["inputs"]
    assert "M9_risk" in snap["inputs"]


def test_default_run_output_schema_stable(stub_data):
    """O-5 输出稳定性：固定输入 3 次运行，outputs key 集合与关键契约枚举一致（数值允许波动）。"""
    from value_agent.agents.builtin import register_builtin_agents
    from value_agent.agents.registry import AgentRegistry
    from value_agent.sessions import InMemoryStore, SessionManager
    from value_agent.sessions.models import ModuleStatus
    from value_agent.workflow import WorkflowEngine, default_workflow

    def _run():
        reg = register_builtin_agents(AgentRegistry())
        engine = WorkflowEngine(reg, SessionManager(InMemoryStore()), data=stub_data)
        session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
        engine.run(session, default_workflow())
        return session

    key_sets = []
    enums = []
    for _ in range(3):
        session = _run()
        key_sets.append({
            aid: frozenset(r.outputs.keys())
            for aid, r in session.module_results.items() if r.status == ModuleStatus.DONE
        })
        enums.append({
            "m7_state": session.module_results["M7_market"].outputs.get("handoff", {}).get("market_state"),
            "m8_mos": session.module_results["M8_safety_margin"].outputs.get("mos_state"),
            "m10_code": session.module_results["M10_decision"].outputs.get("decision_code"),
        })
    for aid in key_sets[0]:
        assert all(ks[aid] == key_sets[0][aid] for ks in key_sets[1:]), f"{aid} outputs key 集合不稳定"
    assert enums[0] == enums[1] == enums[2], f"契约枚举跨运行不稳定: {enums}"


def test_agent_inputs_match_expected_consumption():
    """关键模块 inputs 与引擎实际消费集合一致（批次 D 核对结果，防回归）。

    注：M3 消费 M1 生意类型（2026-08-09 周期口径一致化）；M10/M11 通过 ctx.inputs
    消费的模块必须完整声明（不直接读全量 session.module_results）。
    """
    registry = register_builtin_agents(AgentRegistry())
    expected = {
        "M3_growth": {"M1_business_model"},
        "M4_valuation": {
            "M1_business_model", "M2_financial_quality", "M3_growth",
            "M5_moat", "M6_governance",
        },
        "M5_moat": {"M1_business_model"},  # 5.8：显式声明依赖 M1
        "M8_safety_margin": {  # 6.1：确定性分级消费 M2/M3/M5
            "M2_financial_quality", "M3_growth", "M4_valuation",
            "M5_moat", "M7_market",
        },
        "M9_risk": {  # 8.5：压力情景接入 M4
            "M2_financial_quality", "M3_growth", "M4_valuation", "M5_moat",
            "M6_governance", "M7_market", "M8_safety_margin",
        },
        "M10_decision": {
            "M1_business_model", "M2_financial_quality", "M3_growth",
            "M4_valuation", "M5_moat", "M6_governance", "M7_market",
            "M8_safety_margin", "M9_risk",
        },
        "M11_monitor": {
            "M2_financial_quality", "M3_growth", "M7_market",
            "M8_safety_margin", "M9_risk", "M10_decision",
        },
    }
    for agent_id, exp in expected.items():
        assert set(registry.get(agent_id).spec.inputs) == exp, (
            f"{agent_id} inputs 与预期消费集合不一致"
        )


def test_default_run_emits_handoff_contracts(stub_data):
    """默认工作流跑通后，各模块 outputs.handoff 必须含契约字段（批次 C）。"""
    from value_agent.agents.builtin import register_builtin_agents
    from value_agent.agents.registry import AgentRegistry
    from value_agent.sessions import InMemoryStore, SessionManager
    from value_agent.workflow import WorkflowEngine, default_workflow

    reg = register_builtin_agents(AgentRegistry())
    engine = WorkflowEngine(reg, SessionManager(InMemoryStore()), data=stub_data)
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    engine.run(session, default_workflow())

    expected = {
        "M1_business_model": {"valuation_route", "understandability_level"},
        "M3_growth": {"recommended_growth_rate", "growth_confidence", "cyclicality_flag", "prosperity_code"},
        "M5_moat": {"moat_width", "moat_durability", "moat_trend", "erosion_risks"},
        "M6_governance": {"governance_score", "capital_allocation_flag", "governance_risk_codes"},
        "M7_market": {"valuation_percentile", "market_state", "margin_adjustment"},
        "M8_safety_margin": {"mos_state", "buy_zone", "sell_zone", "reason_codes"},
    }
    for agent_id, keys in expected.items():
        handoff = session.module_results[agent_id].outputs.get("handoff") or {}
        missing = keys - set(handoff)
        assert not missing, f"{agent_id} handoff 缺少字段: {sorted(missing)}"
    m9 = session.module_results["M9_risk"].outputs
    assert "vetoes" in m9 and "monitor_candidates" in m9
    m9_handoff = m9.get("handoff") or {}
    missing = {"veto_flags", "max_severity", "monitor_candidates"} - set(m9_handoff)
    assert not missing, f"M9 handoff 缺少字段: {sorted(missing)}"
    m11 = session.module_results["M11_monitor"].outputs
    if m11.get("monitor_rules"):
        rule = m11["monitor_rules"][0]
        assert "source_module" in rule and "action" in rule


def test_agent_inputs_within_workflow_deps():
    """AgentSpec.inputs ⊆ 默认工作流 deps：声明消费的必须被工作流提供。"""
    registry = register_builtin_agents(AgentRegistry())
    deps_by_agent = _yaml_deps_by_agent()
    for agent_id in registry.ids():
        spec = registry.get(agent_id).spec
        extra = set(spec.inputs) - deps_by_agent.get(agent_id, set())
        assert not extra, (
            f"{agent_id} 声明消费 {sorted(extra)}，但默认工作流未提供"
            "（AgentSpec.inputs 与 workflow deps 未对齐）"
        )


# ---------- backlog 5.8 / 8.10 / 8.11 ----------

def test_m5_depends_on_m1():
    """5.8：M5→M1 依赖显式化（MODULE_DEPENDENCIES + YAML deps 都含 M1）。"""
    assert ModuleName.M1 in MODULE_DEPENDENCIES[ModuleName.M5]
    deps_by_agent = _yaml_deps_by_agent()
    assert "M1_business_model" in deps_by_agent["M5_moat"]


def test_m2_depends_on_m1_for_industry_routing():
    """12.1：M2→M1 依赖显式化（分行业口径需要 M1 的 business_type/financial_subtype）。"""
    assert ModuleName.M1 in MODULE_DEPENDENCIES[ModuleName.M2]
    deps_by_agent = _yaml_deps_by_agent()
    assert "M1_business_model" in deps_by_agent["M2_financial_quality"]


def test_m10_agent_veto_flags_real_shape(stub_data):
    """8.10：agent 层 handoff.veto_flags 回归——LLM 不得覆盖一票否决（真实输出形状）。"""
    from value_agent.agents.base import AgentContext
    from value_agent.agents.builtin import register_builtin_agents
    from value_agent.agents.registry import AgentRegistry
    from value_agent.decision.agent import M10DecisionAgent
    from value_agent.sessions import InMemoryStore, SessionManager
    from value_agent.workflow import WorkflowEngine, default_workflow

    reg = register_builtin_agents(AgentRegistry())
    engine = WorkflowEngine(reg, SessionManager(InMemoryStore()), data=stub_data)
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    engine.run(session, default_workflow())
    m9 = session.module_results["M9_risk"]
    # 手工制造否决（真实形状：handoff.veto_flags + vetoes[]）
    m9.outputs["vetoes"] = [{"id": "V-001", "reason": "审计非标", "severity": "critical"}]
    m9.outputs["handoff"] = {**m9.outputs.get("handoff", {}), "veto_flags": ["V-001"]}
    ctx = AgentContext(session=session, assumptions={}, inputs={
        aid: session.module_results[aid]
        for aid in M10DecisionAgent.spec.inputs if aid in session.module_results
    }, llm=None)
    out = M10DecisionAgent().run(ctx).outputs
    assert out["decision_code"] == "avoid"
    assert out["blocked_by_veto"] is True
    assert out["position"] == 0.0
    assert "审计非标" in out["vetoed"]


def test_workflow_level_contract_consistency(stub_data):
    """8.11：O-5 工作流级断言——M10 handoff 与顶层一致；M11 decision_watch 来源=M10_decision。"""
    from value_agent.agents.builtin import register_builtin_agents
    from value_agent.agents.registry import AgentRegistry
    from value_agent.sessions import InMemoryStore, SessionManager
    from value_agent.workflow import WorkflowEngine, default_workflow

    reg = register_builtin_agents(AgentRegistry())
    engine = WorkflowEngine(reg, SessionManager(InMemoryStore()), data=stub_data)
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    engine.run(session, default_workflow())

    m10 = session.module_results["M10_decision"].outputs
    handoff10 = m10.get("handoff") or {}
    assert handoff10.get("decision_code") == m10.get("decision_code")
    assert handoff10.get("blocked_by_veto") == m10.get("blocked_by_veto")
    assert handoff10.get("position") == m10.get("position")
    # 8.7：core_facts 与顶层一致
    cf = m10.get("core_facts") or {}
    assert cf.get("decision") == m10.get("decision_code")
    assert cf.get("total") == m10.get("total")

    m11 = session.module_results["M11_monitor"].outputs
    for rule in m11.get("monitor_rules") or []:
        if rule.get("rule_type") == "decision_watch":
            assert rule.get("source_module") == "M10_decision"
            break
    else:
        # 决策非 avoid/buy 时也可能无 decision_watch；存在则必须来源正确
        assert m11.get("rule_count", 0) >= 0


# ---------- ModuleResult.calibration 往返（v2 P2 trace 落库） ----------
def test_module_result_calibration_roundtrip():
    calib = {
        "module_id": "M5_moat", "base": 70.0, "final": 75.0, "outcome": "applied",
        "notes": [], "delta": 5.0, "reasons": ["r"], "evidence_refs": [0], "new_facts": [],
    }
    r = ModuleResult(module="M5_moat", status=ModuleStatus.DONE, score=75.0, calibration=calib)
    d = r.to_dict()
    assert d["calibration"] == calib
    r2 = ModuleResult.from_dict(d)
    assert r2.calibration == calib


def test_module_result_calibration_default_none_for_old_payloads():
    """旧数据没有 calibration → from_dict 回退为 None（不报错，向后兼容）。"""
    r = ModuleResult.from_dict({"module": "M1_business_model", "status": "done"})
    assert r.calibration is None
