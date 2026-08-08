"""Agent 注册表：注册、发现、校验。"""
from __future__ import annotations

from .base import Agent, AgentSpec


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent, *, overwrite: bool = False) -> None:
        """注册一个智能体实例；id 冲突默认报错。"""
        aid = agent.spec.id
        if aid in self._agents and not overwrite:
            raise ValueError(f"agent 已存在: {aid}（可用 overwrite=True 覆盖）")
        self._agents[aid] = agent

    def get(self, agent_id: str) -> Agent:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise KeyError(
                f"agent 不存在: {agent_id}；可用: {', '.join(sorted(self._agents))}"
            ) from None

    def has(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def specs(self) -> list[AgentSpec]:
        return [a.spec for a in self._agents.values()]

    def ids(self) -> list[str]:
        return sorted(self._agents)

    def extend(self, other: AgentRegistry, *, overwrite: bool = False) -> None:
        """合并另一个注册表（用于叠加自定义智能体）。"""
        for agent in other._agents.values():
            self.register(agent, overwrite=overwrite)
