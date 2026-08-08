"""备忘录生成测试：决策快照输入（复用）+ self_check 质量自评（O-4）。"""
from __future__ import annotations

from value_agent.report.memo import build_decision_snapshot, build_memo


def test_memo_contains_self_check(stub_data):
    """O-4：memo 附质量自评（accuracy/logicality/storytelling），不改变内容。"""
    from value_agent.agents.builtin import register_builtin_agents
    from value_agent.agents.registry import AgentRegistry
    from value_agent.sessions import InMemoryStore, SessionManager
    from value_agent.workflow import WorkflowEngine, default_workflow

    reg = register_builtin_agents(AgentRegistry())
    engine = WorkflowEngine(reg, SessionManager(InMemoryStore()), data=stub_data)
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    engine.run(session, default_workflow())

    memo = build_memo(session)
    assert "备忘录质量自检（self_check）" in memo
    assert '"accuracy"' in memo and '"logicality"' in memo and '"storytelling"' in memo
    assert build_decision_snapshot(session)["decision_code"] in ("buy", "watch", "avoid")


def test_self_check_flags_degraded_as_low_accuracy():
    """降级模块（如 M4 数据失败）→ accuracy 降为 low/medium 并记录 notes。"""
    from value_agent.core.contracts import ReasonCode, build_meta
    from value_agent.sessions.models import ModuleResult, ModuleStatus, Session

    session = Session(company_code="600519")
    session.module_results["M4_valuation"] = ModuleResult(
        module="M4_valuation", status=ModuleStatus.DONE,
        outputs={"intrinsic_value": None, "current_price": None},
        meta=build_meta(0.0, "low", degraded=True, reason_codes=[ReasonCode.DATA_UNAVAILABLE.value]),
    )
    from value_agent.report.memo import _self_check

    check = _self_check(session)
    assert check["accuracy"] == "low"
    assert any("降级" in n for n in check["notes"])


def test_decision_snapshot_includes_calibration_trace():
    """v2 P2：决策快照含 calibration_trace（每模块校准轨迹落库，审计可追溯）。"""
    from value_agent.sessions.models import ModuleResult, ModuleStatus, Session

    session = Session(company_code="600519")
    session.module_results["M10_decision"] = ModuleResult(
        module="M10_decision", status=ModuleStatus.DONE, score=65.0,
        outputs={
            "decision_code": "watch", "total": 65.0, "position": 0.05,
            "conclusion": "关注", "blocked_by_veto": False, "vetoed": [],
            "dimensions": {}, "qualitative": {"decision_reasons": []},
            "handoff": {"decision_code": "watch", "blocked_by_veto": False, "position": 0.05},
        },
    )
    session.module_results["M5_moat"] = ModuleResult(
        module="M5_moat", status=ModuleStatus.DONE, score=75.0,
        calibration={
            "module_id": "M5_moat", "base": 70.0, "final": 75.0, "outcome": "applied",
            "notes": [], "delta": 5.0, "reasons": ["r"], "evidence_refs": [0], "new_facts": [],
        },
    )
    snap = build_decision_snapshot(session)
    assert "calibration_trace" in snap
    assert snap["calibration_trace"]["M5_moat"]["outcome"] == "applied"
    assert snap["calibration_trace"]["M5_moat"]["delta"] == 5.0
