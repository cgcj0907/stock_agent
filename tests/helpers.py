"""测试辅助工具：StubAgent（不依赖数据源的占位智能体）。"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentSpec
from value_agent.sessions.models import ModuleResult, ModuleStatus


class StubAgent(Agent):
    """占位实现：输出固定结果，供会话语义等不依赖数据源的测试使用。"""

    spec = AgentSpec(id="__stub__", name="stub")

    def __init__(self, spec: AgentSpec, placeholder: str) -> None:
        self.spec = spec
        self._placeholder = placeholder

    def run(self, ctx: AgentContext) -> ModuleResult:
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=50.0,
            outputs={"placeholder": self._placeholder, "status": "stub"},
            evidence=["test stub"],
        )
