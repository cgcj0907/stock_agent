"""工作流执行引擎：拓扑执行 + 条件跳过 + 失败处理，进度写入 Session。

关键约定：工作流里 `deps` 引用的是**步骤 id**，引擎负责把步骤 id 映射到
agent id（session.module_results 以 agent id 为键）。
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from value_agent.agents.base import AgentContext
from value_agent.agents.registry import AgentRegistry
from value_agent.sessions.manager import SessionManager
from value_agent.sessions.models import (
    ModuleResult,
    ModuleStatus,
    Session,
    SessionStatus,
    _now,
)
from value_agent.sessions.state_machine import transition

from .models import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

# 条件表达式求值的受限作用域（禁止内建，仅支持结果访问与比较）
_RESTRICTED_GLOBALS = {"__builtins__": {}}


def _eval_condition(expr: str, scope: dict) -> bool:
    """受限求值条件表达式，异常一律视为不满足。"""
    try:
        return bool(eval(expr, _RESTRICTED_GLOBALS, scope))
    except Exception:  # noqa: BLE001
        logger.warning("condition 求值失败: %s", expr)
        return False


# P2：关键模块——降级/缺失会使备忘录结论失真（docs/13 §13）
CRITICAL_MODULES = ("M4_valuation", "M8_safety_margin", "M9_risk")


def coverage_warnings(workflow: Workflow, registry: AgentRegistry) -> list[dict]:
    """P1 连接覆盖警告：步骤 deps 未覆盖 agent.required_inputs → 提示（不拦截）。

    仅对声明了 required_inputs 的 agent（当前 M8/M10）检查，避免对「可优雅降级」
    的普通 spec.inputs 制造噪音；语义自由度保留。
    """
    agent_by_step = {s.id: s.agent_id for s in workflow.steps}
    warnings: list[dict] = []
    for step in workflow.steps:
        try:
            spec = registry.get(step.agent_id).spec
        except KeyError:
            continue  # validate 已拦，这里容错
        if not spec.required_inputs:
            continue
        dep_agents = {agent_by_step[d] for d in step.deps if d in agent_by_step}
        missing = [a for a in spec.required_inputs if a not in dep_agents]
        if missing:
            warnings.append({
                "type": "missing_required_input",
                "step": step.id,
                "agent": step.agent_id,
                "missing": missing,
                "message": (
                    f"{step.agent_id} 缺少必需上游 {'、'.join(missing)}，"
                    "该模块结果将降级（如安全边际 unavailable）或硬约束（门禁/否决）不生效"
                ),
            })
    return warnings


def _apply_quality_gate(session: Session, workflow: Workflow) -> None:
    """P2 质量门禁：关键模块（M4/M8/M9）失败/跳过/降级 → 会话标记不完整。

    只检查**在工作流内**的关键模块（自由编排：用户没选的模块不判）；
    状态仍保持 COMPLETED（不阻断结论），由 memo/前端 banner 提示。
    """
    step_agents = {step.agent_id for step in workflow.steps}
    reasons: list[str] = []
    for aid in CRITICAL_MODULES:
        if aid not in step_agents:
            continue
        r = session.module_results.get(aid)
        if r is None or r.status in (ModuleStatus.FAILED, ModuleStatus.SKIPPED):
            reasons.append(f"{aid} 未产出结果（{r.status.value if r else '缺失'}）")
        elif r.meta.get("degraded"):
            reasons.append(f"{aid} 数据降级运行，结论可能失真")
    session.incomplete = bool(reasons)
    session.incomplete_reasons = reasons


class WorkflowEngine:
    def __init__(
        self,
        registry: AgentRegistry,
        session_manager: SessionManager,
        data=None,
        llm=None,
    ) -> None:
        """data：DataManager；llm：LlmClient（可选，供 LLM 定性智能体）。"""
        self._registry = registry
        self._manager = session_manager
        self._data = data
        self._llm = llm

    # ---- 主入口 ----
    def run(
        self,
        session: Session,
        workflow: Workflow,
        on_step: Callable[[Session, WorkflowStep, ModuleResult], None] | None = None,
        on_step_start: Callable[[Session, WorkflowStep, ModuleResult], None] | None = None,
        on_llm_chunk: Callable[[Session, WorkflowStep, str, str], None] | None = None,
    ) -> Session:
        """按工作流执行会话中的分析；支持断点续跑（已完成步骤跳过）。

        on_step：每完成一个步骤回调 (session, step, result)，供 SSE 进度推送使用。
        on_step_start：每开始执行一个步骤回调 (session, step, result)（result 为 RUNNING），
            供 SSE 实时推送「正在执行」进度；断点续跑/条件跳过不会触发。
        on_llm_chunk：LLM 流式生成时每产出增量回调 (session, step, kind, chunk)，
            kind ∈ content|thinking，供 SSE 实时推送「正在思考/写作」的增量内容。
        """

        # 实时进度：每完成一步落库一次，保证断线重连/轮询也能看到已完成的步骤
        def _persist_step() -> None:
            try:
                self._manager.persist(session)
            except Exception:
                logger.exception("步骤进度落库失败（不影响执行）")

        def _emit_step(cb, step, result) -> None:
            if cb is not None and result is not None:
                try:
                    cb(session, step, result)
                except Exception:
                    logger.exception("步骤回调失败（不影响执行）")

        workflow.validate(available_agents=set(self._registry.ids()))
        # P1：连接覆盖警告（提示不拦截）；每次运行重算，避免旧警告残留
        session.warnings = coverage_warnings(workflow, self._registry)
        transition(session, SessionStatus.IN_PROGRESS)

        step_map = {s.id: s for s in workflow.steps}
        pending = {s.id for s in workflow.steps}
        while pending:
            ready = self._next_ready(workflow, pending, session, step_map)
            if not ready:
                # 没有可推进的步骤：剩余步骤因依赖失败/跳过而阻塞
                for sid in [s.id for s in workflow.steps if s.id in pending]:
                    self._mark_blocked(session, workflow, sid)
                break
            for step in ready:
                self._execute(
                    session,
                    workflow,
                    step,
                    step_map,
                    on_step_start=on_step_start,
                    on_llm_chunk=on_llm_chunk,
                )
                pending.discard(step.id)
                result = session.module_results.get(step.agent_id)
                _emit_step(on_step, step, result)
                _persist_step()

        self._finalize(session, workflow)
        return session

    # ---- 拓扑推进 ----
    def _next_ready(
        self,
        workflow: Workflow,
        pending: set[str],
        session: Session,
        step_map: dict[str, WorkflowStep],
    ) -> list[WorkflowStep]:
        """找出所有依赖已完成（或依赖失败但 run_always）的待执行步骤。"""
        ready: list[WorkflowStep] = []
        for step in workflow.steps:
            if step.id not in pending:
                continue
            if self._dep_done(session, step.deps, step_map, run_always=step.run_always):
                ready.append(step)
        return ready

    def _dep_done(
        self,
        session: Session,
        dep_step_ids: list[str],
        step_map: dict[str, WorkflowStep],
        *,
        run_always: bool,
    ) -> bool:
        for dep_step_id in dep_step_ids:
            agent_id = step_map[dep_step_id].agent_id
            result = session.module_results.get(agent_id)
            if result is None:
                return False
            if result.status == ModuleStatus.DONE:
                continue
            if run_always and result.status in (ModuleStatus.FAILED, ModuleStatus.SKIPPED):
                continue
            return False
        return True

    def _resolve_llm(self, session: Session):
        """按会话 llm_config 构造 LLM client（优先），否则回退全局 llm。"""
        cfg = getattr(session, "llm_config", None)
        if cfg and cfg.get("api_key"):
            try:
                from value_agent.core.llm import llm_from_config

                client = llm_from_config(cfg)
                if client is not None:
                    return client
            except Exception as exc:  # noqa: BLE001
                logger.warning("按会话 LLM 配置失败，回退全局：%s", exc)
        return self._llm

    # ---- 单步执行 ----
    def _execute(
        self,
        session: Session,
        workflow: Workflow,
        step: WorkflowStep,
        step_map: dict[str, WorkflowStep],
        on_step_start: Callable[[Session, WorkflowStep, ModuleResult], None] | None = None,
        on_llm_chunk: Callable[[Session, WorkflowStep, str, str], None] | None = None,
    ) -> None:
        agent_id = step.agent_id
        session.current_module = agent_id

        # 已完成（断点续跑）→ 跳过
        existing = session.module_results.get(agent_id)
        if existing is not None and existing.status == ModuleStatus.DONE:
            return

        # 条件判断（表达式可访问 inputs[步骤id] / params）
        if step.condition:
            scope = {
                "inputs": {
                    d: session.module_results.get(step_map[d].agent_id)
                    for d in step.deps
                    if d in step_map
                },
                "params": step.params,
            }
            if not _eval_condition(step.condition, scope):
                session.module_results[agent_id] = ModuleResult(
                    module=agent_id, status=ModuleStatus.SKIPPED
                )
                logger.info("步骤 %s 条件不满足，跳过", step.id)
                return

        # 组装上下文并执行（ctx.inputs 以 agent id 为键，匹配 AgentSpec.inputs）
        inputs: dict[str, ModuleResult] = {}
        for d in step.deps:
            if d in step_map and step_map[d].agent_id in session.module_results:
                inputs[step_map[d].agent_id] = session.module_results[step_map[d].agent_id]

        def _llm_chunk_cb(step_id: str, kind: str, chunk: str) -> None:
            """Agent 内流式增量 → 引擎级回调（忽略 agent 传入的 step_id，用引擎侧步骤）。"""
            if on_llm_chunk is None:
                return
            try:
                on_llm_chunk(session, step, kind, chunk)
            except Exception:
                logger.exception("llm chunk 回调失败（不影响执行）")

        ctx = AgentContext(
            session=session,
            assumptions=session.assumptions,
            inputs=inputs,
            params=step.params,
            data=self._data,
            llm=self._resolve_llm(session),
            step_id=step.id,
            on_llm_chunk=_llm_chunk_cb,
        )
        agent = self._registry.get(agent_id)
        started_at = _now()
        result = ModuleResult(module=agent_id, status=ModuleStatus.RUNNING, started_at=started_at)
        session.module_results[agent_id] = result
        try:
            self._manager.persist(session)
        except Exception:
            logger.exception("步骤开始进度落库失败（不影响执行）")
        if on_step_start is not None:
            try:
                on_step_start(session, step, result)
            except Exception:
                logger.exception("步骤开始回调失败（不影响执行）")
        try:
            result = agent.run(ctx)
            if result.status == ModuleStatus.PENDING:
                result.status = ModuleStatus.DONE
        except Exception as exc:
            logger.exception("步骤 %s 执行失败", step.id)
            result.status = ModuleStatus.FAILED
            result.outputs = {"error": str(exc)}
        # agent 返回的结果通常不带 started_at：沿用引擎记录的启动时间（补齐时长审计）
        if result.started_at is None:
            result.started_at = started_at
        result.finished_at = _now()
        session.module_results[agent_id] = result

        # O-3 输出快照审计：M10 决策完成后写结构化快照（含输入 handoff 摘要）
        if agent_id == "M10_decision" and result.status == ModuleStatus.DONE:
            try:
                from value_agent.report.memo import build_decision_snapshot  # 延迟导入避免环

                snap = build_decision_snapshot(session)
                if snap:
                    session.decision_snapshots.append(snap)
            except Exception:
                logger.exception("决策快照写入失败（不影响结果）")

    def _mark_blocked(self, session: Session, workflow: Workflow, step_id: str) -> None:
        """依赖失败导致无法执行的步骤标记为 failed（除非 run_always）。"""
        step = workflow.step(step_id)
        if step.run_always:
            return
        session.module_results[step.agent_id] = ModuleResult(
            module=step.agent_id,
            status=ModuleStatus.FAILED,
            outputs={"error": "依赖步骤失败，未执行"},
        )

    def _finalize(self, session: Session, workflow: Workflow) -> None:
        """只按工作流内步骤判定终态；工作流外的模块保持 pending 不影响结论。"""
        session.current_module = None
        step_agents = {step.agent_id for step in workflow.steps}
        results = [r for aid, r in session.module_results.items() if aid in step_agents]
        any_failed = any(r.status == ModuleStatus.FAILED for r in results)
        any_pending = any(r.status == ModuleStatus.PENDING for r in results)
        if any_failed:
            transition(session, SessionStatus.FAILED)
        elif any_pending:
            if session.status != SessionStatus.IN_PROGRESS:
                transition(session, SessionStatus.IN_PROGRESS)
        else:
            transition(session, SessionStatus.COMPLETED)
        # P2：关键模块降级/缺失 → 标记不完整（memo banner 提示）
        if session.status == SessionStatus.COMPLETED:
            _apply_quality_gate(session, workflow)
        self._manager.persist(session)
