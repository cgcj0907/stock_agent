"""工作流加载器：dict / YAML → Workflow。"""
from __future__ import annotations

from typing import Any

from .models import Workflow, WorkflowStep


def load_workflow_from_dict(data: dict[str, Any]) -> Workflow:
    steps: list[WorkflowStep] = []
    for raw in data.get("steps", []):
        steps.append(
            WorkflowStep(
                id=raw["id"],
                agent_id=raw["agent"],
                deps=list(raw.get("deps", [])),
                condition=raw.get("condition"),
                run_always=bool(raw.get("run_always", False)),
                params=dict(raw.get("params", {})),
            )
        )
    return Workflow(
        id=data["id"],
        name=data.get("name", data["id"]),
        description=data.get("description", ""),
        steps=steps,
    )


def load_workflow_from_yaml(path: str) -> Workflow:
    """从 YAML 文件加载工作流（见 docs/02-agent-architecture.md §4）。"""
    import yaml  # 延迟导入，避免强依赖

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return load_workflow_from_dict(data)
