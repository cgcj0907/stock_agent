"""Supabase（PostgreSQL）会话存储：生产持久化，替代 SqliteStore。

连接串来自 DATABASE_URL（Supabase Pooler）；表结构与 SqliteStore 对齐
（id + jsonb payload），业务代码不感知。
"""
from __future__ import annotations

from .models import Message, Session
from .store import SessionStore


class SupabaseStore(SessionStore):
    name = "supabase"

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg2
            from psycopg2.extras import Json
        except ImportError as exc:
            raise ImportError(
                "未安装 psycopg2-binary：`pip install psycopg2-binary`"
            ) from exc
        self._Json = Json
        # keepalives + 连接超时：避免 pooler 静默断连导致操作无限挂起
        self._conn = psycopg2.connect(
            dsn,
            connect_timeout=15,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        self._conn.autocommit = True
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ
                )
                """
            )

    def save(self, session: Session) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (id, payload, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET payload = EXCLUDED.payload,
                        updated_at = EXCLUDED.updated_at
                """,
                (
                    session.id,
                    self._Json(session.to_dict()),
                    session.updated_at.isoformat(),
                ),
            )

    def load(self, session_id: str) -> Session:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"会话不存在: {session_id}")
        return Session.from_dict(row[0])

    def delete(self, session_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))

    def list(self, status: str | None = None) -> list[Session]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM sessions ORDER BY updated_at DESC")
            rows = cur.fetchall()
        sessions = [Session.from_dict(r[0]) for r in rows]
        if status is None:
            return sessions
        return [s for s in sessions if s.status.value == status]

    def add_message(self, session_id: str, message: Message) -> None:
        session = self.load(session_id)
        session.messages.append(message)
        session.updated_at = message.created_at
        self.save(session)

    def close(self) -> None:
        """释放数据库连接（脚本/批处理结束时调用）；已关闭时无操作。"""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
