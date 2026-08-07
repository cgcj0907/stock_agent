"""会话管理器：创建/推进/重算/恢复/归档。

流水线执行器（runner）由调用方注入，保持本模块与具体模块解耦。
"""
from __future__ import annotations

from collections.abc import Iterable

from .models import (
    Message,
    ModuleName,
    ModuleResult,
    ModuleStatus,
    Session,
    SessionStatus,
    _now,
)
from .state_machine import transition
from .store import SessionStore


def _dedupe_monitor_hits(hits: list[dict], max_items: int = 20) -> list[dict]:
    """I-2 跨会话记忆继承：按 (rule_type, severity) 收敛保留最近一次命中，
    并限制条数，避免重复命中在下次分析时刷屏（历史命中只做回顾，不做计数）。"""
    latest: dict[tuple[str, str], dict] = {}
    for hit in hits:
        key = (hit.get("rule_type", ""), hit.get("severity", ""))
        latest[key] = hit  # 命中按时间升序，后出现的覆盖
    return list(latest.values())[-max_items:]


# 内置流水线执行顺序（默认工作流基于此生成）
PIPELINE_ORDER: list[ModuleName] = [
    ModuleName.M1,
    ModuleName.M2,
    ModuleName.M3,
    ModuleName.M4,
    ModuleName.M5,
    ModuleName.M6,
    ModuleName.M7,
    ModuleName.M8,
    ModuleName.M9,
    ModuleName.M10,
    ModuleName.M11,
]

# 重算依赖：模块 -> 直接依赖模块（改依赖需重跑下游）
MODULE_DEPENDENCIES: dict[ModuleName, set[ModuleName]] = {
    ModuleName.M2: {ModuleName.M1},  # 12.1：M2 按 M1 生意类型分行业口径（财务质量行业路由）
    ModuleName.M3: {ModuleName.M2},
    ModuleName.M7: {ModuleName.M1},  # 生意类型 → 主估值指标（周期/银行看 PB）
    ModuleName.M4: {
        ModuleName.M1,
        ModuleName.M2,
        ModuleName.M3,
        ModuleName.M5,
        ModuleName.M6,
    },
    ModuleName.M5: {ModuleName.M1},  # 5.8：M5 软读 M1 business_type → 显式声明依赖（先 M1 后 M5）
    ModuleName.M8: {  # 6.1：确定性分级消费 M5 moat_width + M2/M3 风险代理
        ModuleName.M2, ModuleName.M3, ModuleName.M4, ModuleName.M5, ModuleName.M7,
    },
    ModuleName.M9: {  # 8.5：压力情景接入 M4 内在价值区间（intrinsic_range + current_price）
        ModuleName.M2, ModuleName.M3, ModuleName.M4, ModuleName.M5,
        ModuleName.M6, ModuleName.M7, ModuleName.M8,
    },
    ModuleName.M10: {  # 维度评分消费全部上游 score + M9 veto
        ModuleName.M1, ModuleName.M2, ModuleName.M3, ModuleName.M4,
        ModuleName.M5, ModuleName.M6, ModuleName.M7, ModuleName.M8, ModuleName.M9,
    },
    ModuleName.M11: {  # 监控规则消费 M2/M3/M7/M8/M9 输出，并在 M10 之后生成
        ModuleName.M2, ModuleName.M3, ModuleName.M7, ModuleName.M8,
        ModuleName.M9, ModuleName.M10,
    },
}

def _affected_modules(modules: Iterable[ModuleName]) -> set[ModuleName]:
    """求出需要**重跑**的模块集合：请求模块 + 下游级联失效模块。

    上游依赖（如 M4 依赖的 M1/M5/M6）结果仍有效，只作为输入复用，不重跑；
    只有其结果已失效的模块（依赖链下游）才需要重算。
    """
    # 反向依赖表：谁依赖我
    reverse: dict[ModuleName, set[ModuleName]] = {}
    for m, deps in MODULE_DEPENDENCIES.items():
        for d in deps:
            reverse.setdefault(d, set()).add(m)

    affected: set[ModuleName] = set()
    queue = list(modules)
    while queue:
        m = queue.pop()
        if m in affected:
            continue
        affected.add(m)
        for dep in reverse.get(m, set()):  # 下游（结果失效需级联重算）
            queue.append(dep)  # noqa: PERF402 (BFS 队列追加，非列表拷贝)
    return affected


def _ordered(modules: Iterable[ModuleName]) -> list[ModuleName]:
    """按内置流水线顺序排序。"""
    order = {m: i for i, m in enumerate(PIPELINE_ORDER)}
    return sorted(modules, key=lambda m: order[m])


class SessionManager:
    def __init__(self, store: SessionStore) -> None:
        self._store = store

    # ---- 创建 ----
    def create_session(
        self,
        company_code: str,
        company_name: str = "",
        *,
        assumptions: dict | None = None,
        data_snapshot_id: str | None = None,
        workflow_id: str = "default",
        workflow_steps: list[dict] | None = None,
        llm_config: dict | None = None,
        model_version: str = "0.1.0",
        monitor_hits: list[dict] | None = None,
    ) -> Session:
        session = Session(
            company_code=company_code,
            company_name=company_name,
            assumptions=assumptions or {},
            data_snapshot_id=data_snapshot_id,
            workflow_id=workflow_id,
            workflow_steps=workflow_steps,
            llm_config=llm_config,
            model_version=model_version,
            monitor_hits=list(monitor_hits or []),
        )
        for module in PIPELINE_ORDER:
            session.module_results[module.value] = ModuleResult(module=module.value)
        self._store.save(session)
        return session

    def latest_completed(self, company_code: str) -> Session | None:
        """同标的最近一次已完成会话（I-2 跨会话记忆继承来源）。

        供新分析继承 monitor_hits：保证监控命中能跨分析会话延续。
        """
        completed = [
            s for s in self._store.list()
            if s.company_code == company_code and s.status == SessionStatus.COMPLETED
        ]
        if not completed:
            return None
        return max(completed, key=lambda s: s.updated_at)

    def prior_monitor_hits(self, company_code: str, max_items: int = 20) -> list[dict]:
        """I-2 跨会话记忆继承：同标的最近一次已完成会话的命中（去重收敛后）。

        新分析会话用它作为 prior_hits 注入 M11，保证监控命中跨分析延续。
        """
        prev = self.latest_completed(company_code)
        if prev is None:
            return []
        return _dedupe_monitor_hits(prev.monitor_hits, max_items=max_items)

    # ---- 追问 / 重算 ----
    def add_message(
        self,
        session: Session,
        role: str,
        content: str,
        action: str | None = None,
    ) -> Message:
        message = Message(role=role, content=content, action=action)
        # 同时更新内存中的 session（调用方返回时能看到最新消息）并持久化
        session.messages.append(message)
        session.updated_at = message.created_at
        self._store.save(session)
        return message

    def rerun(
        self,
        session: Session,
        modules: Iterable[ModuleName],
        assumptions: dict | None = None,
    ) -> list[ModuleName]:
        """局部重算：只重置受影响模块，沿依赖链确定重跑集合。"""
        if assumptions:
            session.assumptions.update(assumptions)
        affected = _affected_modules(modules)
        for module in affected:
            key = module.value
            session.module_results[key].status = ModuleStatus.PENDING
            session.module_results[key].outputs = {}
            session.module_results[key].evidence = []
            session.module_results[key].llm_explanation = None
            session.module_results[key].score = None
        ordered = _ordered(affected)
        transition(session, SessionStatus.IN_PROGRESS)
        session.current_module = ordered[0].value if ordered else None
        self._store.save(session)
        return ordered

    # ---- 状态操作 ----
    def save_memo_version(self, session: Session, memo: str) -> None:
        """保存备忘录版本（不改变会话状态——状态由引擎管理）。"""
        session.memo_versions.append(memo)
        session.updated_at = _now()
        self._store.save(session)

    def resume(self, session: Session) -> Session:
        """从 failed/awaiting_input 恢复到 in_progress（断点续跑）。"""
        transition(session, SessionStatus.IN_PROGRESS)
        self._store.save(session)
        return session

    def archive(self, session: Session) -> Session:
        transition(session, SessionStatus.ARCHIVED)
        session.archived_at = _now()
        self._store.save(session)
        return session

    def persist(self, session: Session) -> None:
        self._store.save(session)

    def load(self, session_id: str) -> Session:
        return self._store.load(session_id)
