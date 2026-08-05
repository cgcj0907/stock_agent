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
