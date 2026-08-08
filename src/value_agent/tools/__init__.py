"""函数注册表（docs/12-v2-upgrade.md §5）：确定性引擎函数登记为带 schema 的只读工具。"""
from __future__ import annotations

from .registry import ToolError, ToolRegistry, ToolSpec, build_tool_registry

__all__ = ["ToolError", "ToolRegistry", "ToolSpec", "build_tool_registry"]
