"""Agent 会话管理：长流程分析的状态化容器。

设计见 docs/02-session-management.md。
"""
from .models import (
    Message,
    ModuleName,
    ModuleResult,
    ModuleStatus,
    Session,
    SessionStatus,
)
from .state_machine import InvalidTransitionError, transition
from .store import InMemoryStore, SessionStore, SqliteStore, create_session_store
from .supabase_store import SupabaseStore
from .manager import MODULE_DEPENDENCIES, PIPELINE_ORDER, SessionManager

__all__ = [
    "Message",
    "ModuleName",
    "ModuleResult",
    "ModuleStatus",
    "Session",
    "SessionStatus",
    "InvalidTransitionError",
    "transition",
    "InMemoryStore",
    "SqliteStore",
    "SupabaseStore",
    "SessionStore",
    "create_session_store",
    "MODULE_DEPENDENCIES",
    "PIPELINE_ORDER",
    "SessionManager",
]
