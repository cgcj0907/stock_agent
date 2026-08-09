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


# ---------- LLM 流式增量回调 ----------
class _StreamingLLM:
    """模拟支持 stream_chat 的 LLM：逐字符产出文本。"""

    def __init__(self, text: str = "hello world") -> None:
        self._text = text
        self.calls = 0

    def stream_chat(self, system: str, user: str):
        self.calls += 1
        for ch in self._text:
            yield "content", ch


def test_engine_forwards_llm_chunks(engine, registry):
    """引擎应把 Agent 内 stream_llm 的每个增量转发给 on_llm_chunk 回调（带步骤定位）。"""

    class StreamAgent(Agent):
        spec = AgentSpec(id="T_llm_stream", name="流式步骤")

        def run(self, ctx: AgentContext) -> ModuleResult:
            text = ctx.stream_llm("sys", "usr")
            assert text == "hello world", "stream_llm 应返回拼接后的完整文本"
            return ModuleResult(module=self.spec.id, status=ModuleStatus.DONE)

    registry.register(StreamAgent(), overwrite=True)
    llm = _StreamingLLM("hello world")
    engine._llm = llm

    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    flow = Workflow(
        id="stream",
        name="流式流",
        steps=[WorkflowStep(id="S1", agent_id="T_llm_stream")],
    )
    chunks: list[tuple[str, str, str]] = []

    def on_chunk(sess, step, kind, chunk):
        chunks.append((step.id, kind, chunk))

    engine.run(session, flow, on_llm_chunk=on_chunk)
    assert "".join(c for _, _, c in chunks) == "hello world"
    assert all(sid == "S1" for sid, _, _ in chunks)
    assert all(kind == "content" for _, kind, _ in chunks)
    assert llm.calls == 1


def test_engine_forwards_thinking_chunks(engine, registry):
    """思考增量（thinking）应转发给 on_llm_chunk，且不混入 stream_llm 返回值。"""

    class ThinkLLM:
        def stream_chat(self, system: str, user: str):
            yield "thinking", "先看商业模式"
            yield "content", "回答正文"

    class ThinkAgent(Agent):
        spec = AgentSpec(id="T_llm_think", name="思考步骤")

        def run(self, ctx: AgentContext) -> ModuleResult:
            text = ctx.stream_llm("sys", "usr")
            assert text == "回答正文", "thinking 不应混入正文返回值"
            return ModuleResult(module=self.spec.id, status=ModuleStatus.DONE)

    registry.register(ThinkAgent(), overwrite=True)
    engine._llm = ThinkLLM()

    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    flow = Workflow(
        id="think",
        name="思考流",
        steps=[WorkflowStep(id="S1", agent_id="T_llm_think")],
    )
    chunks: list[tuple[str, str]] = []

    def on_chunk(sess, step, kind, chunk):
        chunks.append((kind, chunk))

    engine.run(session, flow, on_llm_chunk=on_chunk)
    assert chunks == [("thinking", "先看商业模式"), ("content", "回答正文")]


def test_engine_llm_chunk_callback_failure_does_not_break_run(engine, registry):
    """on_llm_chunk 抛异常时不应中断步骤执行。"""

    class StreamAgent(Agent):
        spec = AgentSpec(id="T_llm_stream_fail", name="流式步骤")

        def run(self, ctx: AgentContext) -> ModuleResult:
            text = ctx.stream_llm("sys", "usr")
            assert text == "abc"
            return ModuleResult(module=self.spec.id, status=ModuleStatus.DONE)

    registry.register(StreamAgent(), overwrite=True)
    engine._llm = _StreamingLLM("abc")

    session = SessionManager(InMemoryStore()).create_session("600519", "贵州茅台")
    flow = Workflow(
        id="stream_fail",
        name="流式失败流",
        steps=[WorkflowStep(id="S1", agent_id="T_llm_stream_fail")],
    )

    def on_chunk(sess, step, kind, chunk):
        raise RuntimeError("回调炸了")

    engine.run(session, flow, on_llm_chunk=on_chunk)
    assert session.module_results["T_llm_stream_fail"].status == ModuleStatus.DONE


def test_default_workflow_uses_short_step_ids():
    """默认工作流 step id 应为短编号（与 YAML/前端目录一致），agent_id 为模块全名。"""
    flow = default_workflow()
    ids = flow.step_ids()
    assert ids[0] == "M1"
    assert flow.step("M1").agent_id == "M1_business_model"
    assert "M1_business_model" not in ids
    assert set(ids) == {f"M{i}" for i in range(1, 12)}


def test_engine_preserves_started_at(engine):
    """生产数据稽核：所有模块 started_at 曾为 None（引擎占位被 agent 结果覆盖）。

    修复后：agent 返回的结果不带 started_at 时，沿用引擎记录的启动时间。
    """
    manager = SessionManager(InMemoryStore())
    session = manager.create_session("600519", "贵州茅台")
    flow = Workflow(
        id="t",
        name="计时流",
        steps=[
            WorkflowStep(id="M2", agent_id="M2_financial_quality"),
            WorkflowStep(id="M4", agent_id="M4_valuation", deps=["M2"]),
        ],
    )
    engine.run(session, flow)
    for aid in ("M2_financial_quality", "M4_valuation"):
        r = session.module_results[aid]
        assert r.status == ModuleStatus.DONE
        assert r.started_at is not None, f"{aid} started_at 不应为 None"
        assert r.finished_at is not None
        assert r.finished_at >= r.started_at


# ---------- P1/P2（docs/13 §13）：连接覆盖警告 + 质量门禁 ----------

def test_coverage_warnings_missing_required_input(registry):
    """M8 缺 M4（只连 M0）→ 覆盖警告（提示不拦截）。"""
    from value_agent.workflow.engine import coverage_warnings

    flow = Workflow(
        id="bad_m8",
        name="M8 缺 M4",
        steps=[
            WorkflowStep(id="M0", agent_id="M0_investor_profile"),
            WorkflowStep(id="M8", agent_id="M8_safety_margin", deps=["M0"]),
        ],
    )
    warns = coverage_warnings(flow, registry)
    assert any(
        w["agent"] == "M8_safety_margin" and "M4_valuation" in w["missing"]
        for w in warns
    )


def test_coverage_warnings_default_flow_empty(registry):
    """默认流所有 required_inputs 都被覆盖 → 无警告。"""
    from value_agent.workflow.engine import coverage_warnings

    assert coverage_warnings(default_workflow(), registry) == []


def test_engine_sets_session_warnings(engine):
    """引擎运行后把覆盖警告落 Session.warnings（P1）。"""
    manager = SessionManager(InMemoryStore())
    session = manager.create_session("600519", "贵州茅台")
    flow = Workflow(
        id="m8_only",
        name="只跑 M8",
        steps=[WorkflowStep(id="M8", agent_id="M8_safety_margin")],
    )
    engine.run(session, flow)
    assert any(w["agent"] == "M8_safety_margin" for w in session.warnings)


def test_quality_gate_marks_incomplete_when_m8_unavailable(engine):
    """M8 缺 M4 → 降级 unavailable → 会话标记不完整（状态仍 COMPLETED），memo 顶部 banner。"""
    from tests.helpers import StubAgent
    from value_agent.agents import AgentRegistry
    from value_agent.report.memo import build_memo

    manager = SessionManager(InMemoryStore())
    session = manager.create_session("600519", "贵州茅台")
    reg = AgentRegistry()
    reg.register(StubAgent(AgentSpec(id="M4_valuation", name="stub4"), "no intrinsic"))
    reg.register(engine._registry.get("M8_safety_margin"))
    eng = WorkflowEngine(reg, manager)
    flow = Workflow(
        id="m4_stub_m8",
        name="M8 降级",
        steps=[
            WorkflowStep(id="M4", agent_id="M4_valuation"),
            WorkflowStep(id="M8", agent_id="M8_safety_margin", deps=["M4"]),
        ],
    )
    eng.run(session, flow)
    assert session.status == SessionStatus.COMPLETED
    assert session.incomplete is True
    assert any("M8_safety_margin" in r for r in session.incomplete_reasons)
    assert "本报告不完整" in build_memo(session)


def test_quality_gate_default_flow_not_incomplete(engine):
    """默认流关键模块正常 → 不标记不完整。"""
    manager = SessionManager(InMemoryStore())
    session = manager.create_session("600519", "贵州茅台")
    engine.run(session, default_workflow())
    assert session.incomplete is False
    assert session.incomplete_reasons == []
