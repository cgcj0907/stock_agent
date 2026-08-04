"""会话存储接口。

- InMemoryStore：进程内（开发/测试用，重启即失）。
- SqliteStore：本地持久化（重启不丢；生产可换 Supabase/PostgreSQL 实现）。
- 实现 SessionStore 即可替换，业务代码不感知。
"""
from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod

from .models import Message, Session


class SessionStore(ABC):
    @abstractmethod
    def save(self, session: Session) -> None: ...

    @abstractmethod
    def load(self, session_id: str) -> Session: ...

    @abstractmethod
    def delete(self, session_id: str) -> None: ...

    @abstractmethod
    def list(self, status: str | None = None) -> list[Session]: ...

    @abstractmethod
    def add_message(self, session_id: str, message: Message) -> None: ...


class InMemoryStore(SessionStore):
    """内存实现：单进程开发/测试够用，重启即失。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def save(self, session: Session) -> None:
        self._sessions[session.id] = session

    def load(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"会话不存在: {session_id}") from None

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list(self, status: str | None = None) -> list[Session]:
        if status is None:
            return list(self._sessions.values())
        return [s for s in self._sessions.values() if s.status.value == status]

    def add_message(self, session_id: str, message: Message) -> None:
        session = self.load(session_id)
        session.messages.append(message)
        session.updated_at = message.created_at


class SqliteStore(SessionStore):
    """SQLite 持久化：会话整体序列化为 JSON 存单表。

    生产换 Supabase/PostgreSQL 时，把这里改成 psycopg2/asyncpg 实现即可，
    业务代码不变。
    """

    def __init__(self, path: str = "data/sessions.db") -> None:
        import os

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT
            )"""
        )
        self._conn.commit()

    def save(self, session: Session) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (id, payload, updated_at) VALUES (?, ?, ?)",
            (session.id, json.dumps(session.to_dict()), session.updated_at.isoformat()),
        )
        self._conn.commit()

    def load(self, session_id: str) -> Session:
        row = self._conn.execute(
            "SELECT payload FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"会话不存在: {session_id}")
        return Session.from_dict(json.loads(row["payload"]))

    def delete(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    def list(self, status: str | None = None) -> list[Session]:
        rows = self._conn.execute("SELECT payload FROM sessions").fetchall()
        sessions = [Session.from_dict(json.loads(r["payload"])) for r in rows]
        if status is None:
            return sessions
        return [s for s in sessions if s.status.value == status]

    def add_message(self, session_id: str, message: Message) -> None:
        session = self.load(session_id)
        session.messages.append(message)
        session.updated_at = message.created_at
        self.save(session)
