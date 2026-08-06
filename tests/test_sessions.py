"""会话管理单元测试：状态机、依赖链重算、断点续跑。

执行走 WorkflowEngine（run_pipeline 已移除）；这里用全 stub 智能体，
不依赖数据源，专注会话语义。
"""
import pytest

from tests.helpers import StubAgent
from value_agent.agents import Agent, AgentContext, AgentRegistry, AgentSpec
from value_agent.sessions import (
    PIPELINE_ORDER,
    InMemoryStore,
    InvalidTransitionError,
    ModuleName,
    ModuleResult,
    ModuleStatus,
    Session,
    SessionManager,
    SessionStatus,
    transition,
)
from value_agent.sessions.manager import _affected_modules
from value_agent.workflow import Workflow, WorkflowEngine, WorkflowStep, default_workflow


def _stub_registry(overrides: list[Agent] | None = None) -> AgentRegistry:
    """全 11 模块 stub 智能体（M2 也用 stub，避免依赖数据源）。"""
    reg = AgentRegistry()
    for m in PIPELINE_ORDER:
        spec = AgentSpec(id=m.value, name=m.label)
        reg.register(StubAgent(spec, placeholder="test stub"))
    for agent in overrides or []:
        reg.register(agent, overwrite=True)
    return reg


def _engine(manager: SessionManager, overrides: list[Agent] | None = None) -> WorkflowEngine:
    return WorkflowEngine(_stub_registry(overrides), manager)


@pytest.fixture
def manager() -> SessionManager:
    return SessionManager(InMemoryStore())


@pytest.fixture
def session(manager: SessionManager) -> Session:
    return manager.create_session("600519", "贵州茅台")


def test_create_session_status(session):
    assert session.status == SessionStatus.CREATED
    assert len(session.module_results) == len(PIPELINE_ORDER)
    assert all(isinstance(k, str) for k in session.module_results)  # key=agent id


def test_illegal_transition_raises(session):
    with pytest.raises(InvalidTransitionError):
        transition(session, SessionStatus.COMPLETED)  # created 不能直接 completed


def test_rerun_affected_closure():
    affected = _affected_modules([ModuleName.M3])
    assert affected == {ModuleName.M3, ModuleName.M4,
                        ModuleName.M8, ModuleName.M9,
                        ModuleName.M10, ModuleName.M11}
    assert ModuleName.M2 not in affected       # 上游（M2）结果仍有效，只作输入
    assert ModuleName.M1 not in affected       # 与 M3 无关


def test_rerun_returns_pipeline_order(manager, session):
    _engine(manager).run(session, default_workflow())
    ordered = manager.rerun(session, [ModuleName.M3], assumptions={"growth": 0.18})
    assert ordered == [ModuleName.M3, ModuleName.M4,
                       ModuleName.M8, ModuleName.M9,
                       ModuleName.M10, ModuleName.M11]
    assert session.assumptions["growth"] == 0.18
    assert session.module_results[ModuleName.M3.value].status == ModuleStatus.PENDING
    assert session.module_results[ModuleName.M1.value].status == ModuleStatus.DONE  # 未受影响


def test_failed_module_sets_session_failed(manager, session):
    class BoomAgent(Agent):
        spec = AgentSpec(id="M1_business_model", name="boom")

        def run(self, ctx: AgentContext) -> ModuleResult:
            raise RuntimeError("数据缺失")

    flow = Workflow(
        id="f",
        name="失败流",
        steps=[WorkflowStep(id="M1", agent_id="M1_business_model")],
    )
    _engine(manager, overrides=[BoomAgent()]).run(session, flow)
    assert session.status == SessionStatus.FAILED
    assert session.module_results["M1_business_model"].status == ModuleStatus.FAILED


def test_resume_after_failure(manager, session):
    class BoomAgent(Agent):
        spec = AgentSpec(id="M1_business_model", name="boom")

        def run(self, ctx: AgentContext) -> ModuleResult:
            raise RuntimeError("boom")

    flow = Workflow(
        id="f",
        name="失败流",
        steps=[WorkflowStep(id="M1", agent_id="M1_business_model")],
    )
    engine = _engine(manager, overrides=[BoomAgent()])
    engine.run(session, flow)
    assert session.status == SessionStatus.FAILED
    manager.resume(session)
    assert session.status == SessionStatus.IN_PROGRESS


def test_save_memo_version_keeps_status(manager, session):
    manager.save_memo_version(session, "memo v1")
    manager.save_memo_version(session, "memo v2")
    assert session.memo_versions == ["memo v1", "memo v2"]
    assert session.status == SessionStatus.CREATED  # 不改变状态


def test_delete_session(manager, session):
    sid = session.id
    manager._store.delete(sid)
    with pytest.raises(KeyError):
        manager.load(sid)


def test_workflow_id_default_and_custom(manager):
    s1 = manager.create_session("600519")
    assert s1.workflow_id == "default"
    s2 = manager.create_session("600519", workflow_id="quick")
    assert s2.workflow_id == "quick"


def test_add_message_updates_session_object(manager, session):
    """add_message 应同时更新传入的 session（供 API 返回最新消息）。"""
    manager.add_message(session, "user", "追问")
    manager.add_message(session, "assistant", "回复")
    assert len(session.messages) == 2
    assert session.messages[-1].role == "assistant"
    # 重新加载也应一致（已持久化）
    reloaded = manager.load(session.id)
    assert len(reloaded.messages) == 2
