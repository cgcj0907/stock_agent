"""工作流引擎单元测试：默认流、自定义流、条件跳过、run_always、注册自定义 agent。"""
import pytest

from value_agent.agents import Agent, AgentContext, AgentRegistry, AgentSpec
from value_agent.agents.builtin import register_builtin_agents
from value_agent.sessions import (
    PIPELINE_ORDER,
    InMemoryStore,
    ModuleResult,
    ModuleStatus,
    SessionManager,
    SessionStatus,
)
from value_agent.workflow import (
    Workflow,
    WorkflowEngine,
    WorkflowStep,
    WorkflowValidationError,
    default_workflow,
    load_workflow_from_dict,
)


@pytest.fixture
def registry() -> AgentRegistry:
    return register_builtin_agents(AgentRegistry())


@pytest.fixture
def engine(registry: AgentRegistry, stub_data) -> WorkflowEngine:
    return WorkflowEngine(registry, SessionManager(InMemoryStore()), data=stub_data)


def test_default_workflow_runs_all_modules(engine, registry):
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    flow = default_workflow()
    flow.validate(available_agents=set(registry.ids()))
    engine.run(session, flow)
    assert session.status == SessionStatus.COMPLETED
    done = [r for r in session.module_results.values() if r.status == ModuleStatus.DONE]
    assert len(done) == len(PIPELINE_ORDER)


def test_custom_workflow_topological_order(engine):
    manager = SessionManager(InMemoryStore())
    session = manager.create_session("600519", "贵州茅台")
    flow = Workflow(
        id="quick",
        name="快速估值流",
        steps=[
            WorkflowStep(id="M2", agent_id="M2_financial_quality"),
            WorkflowStep(id="M4", agent_id="M4_valuation", deps=["M2"]),
            WorkflowStep(id="M8", agent_id="M8_safety_margin", deps=["M4"]),
        ],
    )
    engine.run(session, flow)
    assert session.status == SessionStatus.COMPLETED
    ran = [aid for aid, r in session.module_results.items() if r.status == ModuleStatus.DONE]
    assert ran == ["M2_financial_quality", "M4_valuation", "M8_safety_margin"]


def test_condition_skip(engine):
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    flow = Workflow(
        id="cond",
        name="条件流",
        steps=[
            WorkflowStep(id="M2", agent_id="M2_financial_quality"),
            WorkflowStep(
                id="M4",
                agent_id="M4_valuation",
                deps=["M2"],
                condition="inputs['M2'].outputs.get('skip') == True",
            ),
        ],
    )
    engine.run(session, flow)
    assert session.module_results["M4_valuation"].status == ModuleStatus.SKIPPED


def test_run_always_after_dependency_failure(engine, registry):
    class FailingAnalysisAgent(Agent):
        spec = AgentSpec(id="M1_business_model", name="bad")

        def run(self, ctx):
            raise RuntimeError("boom")

    registry.register(FailingAnalysisAgent(), overwrite=True)
    flow = Workflow(
        id="f",
        name="失败流",
        steps=[
            WorkflowStep(id="M1", agent_id="M1_business_model"),
            WorkflowStep(id="M9", agent_id="M9_risk", deps=["M1"], run_always=True),
        ],
    )
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    engine.run(session, flow)
    assert session.module_results["M1_business_model"].status == ModuleStatus.FAILED
    assert session.module_results["M9_risk"].status == ModuleStatus.DONE  # run_always
    assert session.status == SessionStatus.FAILED


def test_validate_rejects_unknown_agent(registry):
    flow = Workflow(
        id="x",
        name="坏流",
        steps=[WorkflowStep(id="X", agent_id="nope_agent")],
    )
    with pytest.raises(WorkflowValidationError):
        flow.validate(available_agents=set(registry.ids()))


def test_validate_rejects_cycle(registry):
    flow = Workflow(
        id="c",
        name="环",
        steps=[
            WorkflowStep(id="A", agent_id="M1_business_model", deps=["B"]),
            WorkflowStep(id="B", agent_id="M2_financial_quality", deps=["A"]),
        ],
    )
    with pytest.raises(WorkflowValidationError):
        flow.validate(available_agents=set(registry.ids()))


def test_custom_agent_in_workflow(engine, registry):
    registry.register(EsgAgent())
    flow = Workflow(
        id="esg",
        name="含自定义智能体",
        steps=[
            WorkflowStep(id="M2", agent_id="M2_financial_quality"),
            WorkflowStep(id="ESG", agent_id="M12_esg_rating", deps=["M2"]),
        ],
    )
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    engine.run(session, flow)
    r = session.module_results["M12_esg_rating"]
    assert r.status == ModuleStatus.DONE
    assert r.outputs["esg_level"] == "A"


def test_load_workflow_from_dict():
    flow = load_workflow_from_dict(
        {
            "id": "quick",
            "steps": [
                {"id": "M2", "agent": "M2_financial_quality"},
                {"id": "M4", "agent": "M4_valuation", "deps": ["M2"]},
            ],
        }
    )
    assert flow.step("M4").deps == ["M2"]
    assert flow.step("M4").agent_id == "M4_valuation"


# ---- 自定义智能体（示例） ----
class EsgAgent(Agent):
    spec = AgentSpec(
        id="M12_esg_rating",
        name="ESG 评级智能体",
        inputs=["M2_financial_quality"],
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        assert "M2_financial_quality" in ctx.inputs  # 依赖结果可访问
        return ModuleResult(
            module="M12_esg_rating",
            status=ModuleStatus.DONE,
            score=70.0,
            outputs={"esg_level": "A"},
            evidence=["自定义智能体示例"],
        )


def test_engine_resolves_per_session_llm(engine):
    """按会话 llm_config 注入优先于全局 llm；无配置回退。"""
    from value_agent.core.llm import LlmClient
    from value_agent.sessions import InMemoryStore, SessionManager

    manager = SessionManager(InMemoryStore())
    session = manager.create_session(
        "600519", "贵州茅台",
        # 真实用法：BFF 构造的 llm_config 含 provider（见 frontend/app/api/sessions/route.ts）
        llm_config={"provider": "openai", "model": "custom-model",
                    "api_key": "sk-test", "base_url": "https://x/v1"},
    )
    client = engine._resolve_llm(session)
    assert isinstance(client, LlmClient)
    assert client.api_key == "sk-test"
    assert client.model == "openai/custom-model"  # provider 前缀（litellm 路由）
    assert client.base_url == "https://x/v1"

    # 无 llm_config（engine 全局 llm=None）→ 回退 None
    assert engine._resolve_llm(manager.create_session("600519")) is None


def test_run_fires_step_start_then_completion_callbacks(engine):
    """实时进度：每个步骤先回调 running（开始），再回调终态（完成）。"""
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    flow = Workflow(
        id="cb",
        name="回调流",
        steps=[
            WorkflowStep(id="M2", agent_id="M2_financial_quality"),
            WorkflowStep(id="M4", agent_id="M4_valuation", deps=["M2"]),
        ],
    )
    started: list[tuple[str, str]] = []
    done: list[tuple[str, str]] = []

    def on_start(sess, step, result) -> None:
        started.append((step.id, result.status.value))

    def on_step(sess, step, result) -> None:
        done.append((step.id, result.status.value))

    engine.run(session, flow, on_step=on_step, on_step_start=on_start)

    assert [sid for sid, _ in started] == ["M2", "M4"]
    assert [st for _, st in started] == ["running", "running"]
    assert [st for _, st in done] == ["done", "done"]
    # 每个步骤：开始回调（running）必须先于完成回调
    for (start_sid, _), (done_sid, _) in zip(started, done):
        assert start_sid == done_sid


def test_run_fires_callbacks_only_for_executed_steps(engine):
    """条件跳过/断点续跑不触发 running 回调。"""
    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    flow = Workflow(
        id="cond",
        name="条件流",
        steps=[
            WorkflowStep(id="M2", agent_id="M2_financial_quality"),
            WorkflowStep(
                id="M4",
                agent_id="M4_valuation",
                deps=["M2"],
                condition="inputs['M2'].outputs.get('skip') == True",
            ),
        ],
    )
    started: list[str] = []
    done: list[str] = []

    def on_start(sess, step, result) -> None:
        started.append(step.id)

    def on_step(sess, step, result) -> None:
        done.append(step.id)

    engine.run(session, flow, on_step=on_step, on_step_start=on_start)

    assert started == ["M2"]  # M4 条件不满足，跳过，不触发 running
    assert set(done) == {"M2", "M4"}  # 完成回调包含 skipped
