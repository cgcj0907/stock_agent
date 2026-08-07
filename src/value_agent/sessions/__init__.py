"""Agent 会话管理：长流程分析的状态化容器。

设计见 docs/02-session-management.md。
"""
from .manager import MODULE_DEPENDENCIES, PIPELINE_ORDER, SessionManager
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

__all__ = [
    "MODULE_DEPENDENCIES",
    "PIPELINE_ORDER",
    "InMemoryStore",
    "InvalidTransitionError",
    "Message",
    "ModuleName",
    "ModuleResult",
    "ModuleStatus",
    "Session",
    "SessionManager",
    "SessionStatus",
    "SessionStore",
    "SqliteStore",
    "SupabaseStore",
    "create_session_store",
    "transition",
]
