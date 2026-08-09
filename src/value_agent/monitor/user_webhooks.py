"""用户通知渠道存储：user_webhooks(user_id, channel, webhook_url)。

- 每个登录用户可配自己的飞书/企微 webhook；监控命中按规则归属（user_id）推给对应用户。
- 与 rules_store 同构：InMemory / Sqlite / Supabase 三实现 + create_user_webhook_store() 工厂。
"""
from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS user_webhooks (
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('feishu', 'wechat')),
    webhook_url TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, channel)
);
"""

_PG_DDL = """
CREATE TABLE IF NOT EXISTS user_webhooks (
    user_id UUID NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('feishu', 'wechat')),
    webhook_url TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, channel)
);
"""

CHANNELS = ("feishu", "wechat")


class UserWebhookStore(ABC):
    """用户 webhook 存储接口。channel ∈ {feishu, wechat}。"""

    @abstractmethod
    def get_webhooks(self, user_id: str) -> dict[str, str]:
        """返回某用户已配置的 {channel: webhook_url}。"""

    @abstractmethod
    def set_webhook(self, user_id: str, channel: str, webhook_url: str) -> None:
        """upsert 某用户某个渠道的 webhook。"""

    @abstractmethod
    def delete_webhook(self, user_id: str, channel: str) -> None:
        """删除某用户某个渠道（清空配置时调用）。"""

    @abstractmethod
    def close(self) -> None:
        """释放连接（脚本结束时调用）。"""


class InMemoryUserWebhookStore(UserWebhookStore):
    """进程内实现：开发/测试用，重启即失。"""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], str] = {}

    def get_webhooks(self, user_id: str) -> dict[str, str]:
        return {ch: url for (uid, ch), url in self._rows.items() if uid == user_id}

    def set_webhook(self, user_id: str, channel: str, webhook_url: str) -> None:
        self._rows[(user_id, channel)] = webhook_url

    def delete_webhook(self, user_id: str, channel: str) -> None:
        self._rows.pop((user_id, channel), None)

    def close(self) -> None:
        return None


class SqliteUserWebhookStore(UserWebhookStore):
    """SQLite 实现：与会话库同文件（data/sessions.db）。"""

    def __init__(self, path: str = "data/sessions.db") -> None:
        import os as _os

        _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SQLITE_DDL)
        self._conn.commit()

    def get_webhooks(self, user_id: str) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT channel, webhook_url FROM user_webhooks WHERE user_id = ?", (user_id,)
        ).fetchall()
        return {r["channel"]: r["webhook_url"] for r in rows}

    def set_webhook(self, user_id: str, channel: str, webhook_url: str) -> None:
        self._conn.execute(
            """INSERT INTO user_webhooks (user_id, channel, webhook_url, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT (user_id, channel) DO UPDATE SET
                   webhook_url = excluded.webhook_url, updated_at = excluded.updated_at""",
            (user_id, channel, webhook_url),
        )
        self._conn.commit()

    def delete_webhook(self, user_id: str, channel: str) -> None:
        self._conn.execute(
            "DELETE FROM user_webhooks WHERE user_id = ? AND channel = ?", (user_id, channel)
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()


class SupabaseUserWebhookStore(UserWebhookStore):
    """Supabase（PostgreSQL）实现：生产用，连接串来自 DATABASE_URL。"""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg2
        except ImportError as exc:
            raise ImportError("未安装 psycopg2-binary：`pip install psycopg2-binary`") from exc
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
            cur.execute(_PG_DDL)

    def get_webhooks(self, user_id: str) -> dict[str, str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT channel, webhook_url FROM user_webhooks WHERE user_id = %s", (user_id,)
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def set_webhook(self, user_id: str, channel: str, webhook_url: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO user_webhooks (user_id, channel, webhook_url, updated_at)
                   VALUES (%s, %s, %s, now())
                   ON CONFLICT (user_id, channel) DO UPDATE SET
                       webhook_url = EXCLUDED.webhook_url, updated_at = EXCLUDED.updated_at""",
                (user_id, channel, webhook_url),
            )

    def delete_webhook(self, user_id: str, channel: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_webhooks WHERE user_id = %s AND channel = %s",
                (user_id, channel),
            )

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()


def create_user_webhook_store() -> UserWebhookStore:
    """按环境变量创建用户 webhook 存储（与 create_session_store 同源）。"""
    backend = os.getenv("SESSION_STORE", "sqlite").strip().lower()
    if backend == "memory":
        return InMemoryUserWebhookStore()
    if backend in ("supabase", "postgres"):
        dsn = os.getenv("DATABASE_URL", "")
        if not dsn:
            raise ValueError("SESSION_STORE=supabase 需要 DATABASE_URL")
        return SupabaseUserWebhookStore(dsn)
    return SqliteUserWebhookStore(os.getenv("SESSIONS_DB", "data/sessions.db"))
