"""会话状态机：所有合法迁移集中定义，非法迁移抛异常。"""
from __future__ import annotations

from .models import Session, SessionStatus, _now


class InvalidTransitionError(RuntimeError):
    """非法的会话状态迁移。"""


VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {
        SessionStatus.IN_PROGRESS,
        SessionStatus.FAILED,
        SessionStatus.ARCHIVED,
    },
    SessionStatus.IN_PROGRESS: {
        SessionStatus.AWAITING_INPUT,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
    },
    SessionStatus.AWAITING_INPUT: {SessionStatus.IN_PROGRESS, SessionStatus.ARCHIVED},
    SessionStatus.COMPLETED: {SessionStatus.IN_PROGRESS, SessionStatus.ARCHIVED},
    SessionStatus.FAILED: {SessionStatus.IN_PROGRESS, SessionStatus.ARCHIVED},
    SessionStatus.ARCHIVED: set(),
}


def transition(session: Session, new_status: SessionStatus) -> None:
    """把会话迁移到新状态；非法迁移抛 InvalidTransitionError。"""
    allowed = VALID_TRANSITIONS[session.status]
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"非法状态迁移: {session.status.value} -> {new_status.value}"
        )
    session.status = new_status
    session.updated_at = _now()
