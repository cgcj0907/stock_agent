"""工作流执行引擎：拓扑执行 + 条件跳过 + 失败处理，进度写入 Session。

关键约定：工作流里 `deps` 引用的是**步骤 id**，引擎负责把步骤 id 映射到
agent id（session.module_results 以 agent id 为键）。
"""
from __future__ import annotations

import logging
from typing import Callable

from value_agent.agents.base import AgentContext
from value_agent.agents.registry import AgentRegistry
from value_agent.sessions.models import (
    ModuleResult,
    ModuleStatus,
    Session,
    SessionStatus,
    _now,
)
from value_agent.sessions.manager import SessionManager
from value_agent.sessions.state_machine import transition

from .models import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

# 条件表达式求值的受限作用域（禁止内建，仅支持结果访问与比较）
_RESTRICTED_GLOBALS = {"__builtins__": {}}


def _eval_condition(expr: str, scope: dict) -> bool:
    """受限求值条件表达式，异常一律视为不满足。"""
    try:
        return bool(eval(expr, _RESTRICTED_GLOBALS, scope))  # noqa: S307
    except Exception:  # noqa: BLE001
        logger.warning("condition 求值失败: %s", expr)
        return False


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
    ) -> Session:
        """按工作流执行会话中的分析；支持断点续跑（已完成步骤跳过）。

        on_step：每完成一个步骤回调 (session, step, result)，供 SSE 进度推送使用。
        on_step_start：每开始执行一个步骤回调 (session, step, result)（result 为 RUNNING），
            供 SSE 实时推送「正在执行」进度；断点续跑/条件跳过不会触发。
        """

        # 实时进度：每完成一步落库一次，保证断线重连/轮询也能看到已完成的步骤
        def _persist_step() -> None:
            try:
                self._manager.persist(session)
            except Exception:  # noqa: BLE001
                logger.exception("步骤进度落库失败（不影响执行）")

        def _emit_step(cb, step, result) -> None:
            if cb is not None and result is not None:
                try:
                    cb(session, step, result)
                except Exception:  # noqa: BLE001
                    logger.exception("步骤回调失败（不影响执行）")

        workflow.validate(available_agents=set(self._registry.ids()))
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
                self._execute(session, workflow, step, step_map, on_step_start=on_step_start)
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

        ctx = AgentContext(
            session=session,
            assumptions=session.assumptions,
            inputs=inputs,
            params=step.params,
            data=self._data,
            llm=self._resolve_llm(session),
        )
        agent = self._registry.get(agent_id)
        result = ModuleResult(module=agent_id, status=ModuleStatus.RUNNING, started_at=_now())
        session.module_results[agent_id] = result
        if on_step_start is not None:
            try:
                on_step_start(session, step, result)
            except Exception:  # noqa: BLE001
                logger.exception("步骤开始回调失败（不影响执行）")
        try:
            result = agent.run(ctx)
            if result.status == ModuleStatus.PENDING:
                result.status = ModuleStatus.DONE
        except Exception as exc:  # noqa: BLE001
            logger.exception("步骤 %s 执行失败", step.id)
            result.status = ModuleStatus.FAILED
            result.outputs = {"error": str(exc)}
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
        self._manager.persist(session)
