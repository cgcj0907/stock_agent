"""工作流定义模型。"""
from __future__ import annotations

from dataclasses import dataclass, field


class WorkflowValidationError(ValueError):
    """工作流定义非法（agent 不存在 / 依赖缺失 / 有环）。"""


@dataclass
class WorkflowStep:
    id: str
    agent_id: str
    deps: list[str] = field(default_factory=list)  # 依赖的 step id
    condition: str | None = None  # 条件表达式，为假则跳过
    run_always: bool = False  # 依赖失败也强制运行（如红队批判）
    params: dict = field(default_factory=dict)  # 透传给 agent 的参数


@dataclass
class Workflow:
    id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)

    def step(self, step_id: str) -> WorkflowStep:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(f"工作流 {self.id} 中没有步骤 {step_id}")

    def step_ids(self) -> list[str]:
        return [s.id for s in self.steps]

    def validate(self, available_agents: set[str]) -> None:
        """校验：agent 存在、依赖存在、无环。"""
        step_ids = set(self.step_ids())
        if len(step_ids) != len(self.steps):
            raise WorkflowValidationError(f"工作流 {self.id} 存在重复步骤 id")
        for s in self.steps:
            if s.agent_id not in available_agents:
                raise WorkflowValidationError(
                    f"步骤 {s.id} 引用了未注册的 agent: {s.agent_id}"
                )
            missing = [d for d in s.deps if d not in step_ids]
            if missing:
                raise WorkflowValidationError(
                    f"步骤 {s.id} 依赖不存在的步骤: {missing}"
                )
        # 环检测（DFS）
        visited: dict[str, int] = {}  # 0=未访问 1=访问中 2=完成

        def dfs(node: str) -> None:
            state = visited.get(node, 0)
            if state == 1:
                raise WorkflowValidationError(f"工作流 {self.id} 存在环: {node}")
            if state == 2:
                return
            visited[node] = 1
            for dep in self.step(node).deps:
                dfs(dep)
            visited[node] = 2

        for s in self.steps:
            dfs(s.id)
