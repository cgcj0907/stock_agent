"""Agent 抽象：统一输入输出契约，是自由编排的基础。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from value_agent.sessions.models import ModuleResult

if TYPE_CHECKING:
    from value_agent.sessions.models import Session


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


class Agent(ABC):
    """分析能力单元。子类必须定义 spec 并实现 run。"""

    spec: AgentSpec

    @abstractmethod
    def run(self, ctx: AgentContext) -> ModuleResult:
        """执行分析，返回统一 ModuleResult。"""
        raise NotImplementedError
