"""智能体抽象与注册表。

- 每个分析能力 = 一个 Agent（M1–M11 为内置，可自由新增）
- 注册后即可被任意工作流引用
设计见 docs/02-agent-architecture.md。
"""
from .base import Agent, AgentContext, AgentSpec
from .registry import AgentRegistry
from .builtin import register_builtin_agents

__all__ = ["Agent", "AgentContext", "AgentSpec", "AgentRegistry", "register_builtin_agents"]
