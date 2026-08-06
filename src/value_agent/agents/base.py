"""Agent 抽象：统一输入输出契约，是自由编排的基础。"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from value_agent.sessions.models import ModuleResult

if TYPE_CHECKING:
    from value_agent.sessions.models import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentSpec:
    """智能体的静态描述（注册表索引用）。"""

    id: str
    name: str
    description: str = ""
    inputs: list[str] = field(default_factory=list)  # 依赖的 agent id
    requires_llm: bool = False
    version: str = "0.1.0"


@dataclass
class AgentContext:
    """Agent 运行时上下文：只读输入 + 会话 + 数据/LLM 访问入口。"""

    session: "Session"
    assumptions: dict
    inputs: dict[str, ModuleResult]  # 依赖 agent 的结果（按 agent id 索引）
    data: Any = None  # 数据访问层（后续接入 data/）
    llm: Any = None  # LLM client（requires_llm=True 时提供）
    params: dict = field(default_factory=dict)  # 工作流步骤透传参数
    step_id: str | None = None  # 当前工作流步骤 id（SSE llm_chunk 事件定位用）
    # 实时流式回调：每产出增量触发一次 (step_id, kind, chunk)，kind ∈ content|thinking
    on_llm_chunk: Callable[[str, str, str], None] | None = None

    def stream_llm(self, system: str, user: str) -> str | None:
        """流式 LLM 定性调用：边生成边回调 on_llm_chunk，返回完整正文文本。

        - 正文增量（content）会累加进返回值；思考增量（thinking）只转发回调，
          不混入正文（由前端单独渲染成灰字思考区）。
        - 未配置 LLM 返回 None；回调失败只记日志，绝不阻断分析主流程。
        """
        if self.llm is None:
            return None
        # 兼容只实现了阻塞 chat() 的注入对象：退化为一次性整段返回
        stream = getattr(self.llm, "stream_chat", None)
        if stream is None:
            return self.llm.chat(system, user)
        parts: list[str] = []
        for item in stream(system, user):
            # 兼容旧式纯字符串增量：视为正文
            if isinstance(item, tuple):
                kind, delta = item
            else:
                kind, delta = "content", item
            if self.on_llm_chunk is not None:
                try:
                    self.on_llm_chunk(self.step_id or "", kind, delta)
                except Exception:  # noqa: BLE001
                    logger.warning("llm chunk 回调失败（不影响分析）", exc_info=True)
            if kind == "content":
                parts.append(delta)
        return "".join(parts)


class Agent(ABC):
    """分析能力单元。子类必须定义 spec 并实现 run。"""

    spec: AgentSpec

    @abstractmethod
    def run(self, ctx: AgentContext) -> ModuleResult:
        """执行分析，返回统一 ModuleResult。"""
        raise NotImplementedError
