"""监控规则存储：把 M11 生成的 monitor_rules 物化为独立表（monitor_rules）。

- 表绑定 session_id + company_code，user_id 可空（空=系统/全局规则；后续前端编辑归属用户）。
- 设计：monitor_rules 表是每日监控的**规则源**（runner 从表读）；M11 每次分析完成后
  由 SessionManager.persist 物化写入。用户自定义行（user_id 非空）在重物化时保留。
- 与 SessionStore 同构：InMemory / Sqlite / Supabase 三实现 + create_rule_store() 工厂。
"""
from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod

# 写入/读取的字段顺序（与建表列对齐）
_COLUMNS = (
    "session_id", "company_code", "company_name", "rule_type", "source_module",
    "trigger", "message", "severity", "action", "params", "user_id", "active",
)

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS monitor_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    company_code TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    rule_type TEXT NOT NULL,
    source_module TEXT NOT NULL DEFAULT '',
    trigger TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    action TEXT NOT NULL DEFAULT 'watch',
    params TEXT NOT NULL DEFAULT '{}',
    user_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_monitor_rules_session ON monitor_rules (session_id);
CREATE INDEX IF NOT EXISTS idx_monitor_rules_company ON monitor_rules (company_code, active);
"""

_PG_DDL = """
CREATE TABLE IF NOT EXISTS monitor_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    company_code TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    rule_type TEXT NOT NULL,
    source_module TEXT NOT NULL DEFAULT '',
    trigger TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    action TEXT NOT NULL DEFAULT 'watch',
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    user_id UUID,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS monitor_rules_session_idx ON monitor_rules (session_id);
CREATE INDEX IF NOT EXISTS monitor_rules_company_idx ON monitor_rules (company_code, active);
"""


class MonitorRuleStore(ABC):
    """监控规则存储接口。规则行统一为 dict（见 _row_to_dict）。"""

    @abstractmethod
    def replace_for_session(self, session_id: str, rules: list[dict]) -> int:
        """用最新规则替换某会话的系统规则（user_id 非空的自定义行保留），返回写入条数。"""

    @abstractmethod
    def list_by_session(self, session_id: str) -> list[dict]:
        """返回某会话全部有效（active）规则，按写入顺序。"""

    @abstractmethod
    def list_by_company(self, company_code: str) -> list[dict]:
        """返回某公司全部有效规则（跨会话，供前端/管理查看）。"""

    @abstractmethod
    def close(self) -> None:
        """释放连接（脚本结束时调用）。"""


def _normalize_rule(rule: dict, session_id: str | None = None) -> dict:
    """规范化一条规则行：补齐必填键、限定列集。"""
    row = {k: rule.get(k) for k in _COLUMNS}
    row["rule_type"] = str(rule.get("rule_type") or "watch")
    row["company_code"] = str(rule.get("company_code") or "")
    row["company_name"] = str(rule.get("company_name") or "")
    row["severity"] = str(rule.get("severity") or "info")
    row["action"] = str(rule.get("action") or "watch")
    row["params"] = rule.get("params") or {}
    if not isinstance(row["params"], dict):
        row["params"] = {}
    row["user_id"] = rule.get("user_id")
    row["active"] = bool(rule.get("active", True))
    if session_id is not None:
        row["session_id"] = session_id
    return row


def _row_to_dict(row: dict) -> dict:
    """数据库行 → 规则 dict（params 反序列化、active 布尔化）。"""
    out = dict(row)
    params = out.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (TypeError, ValueError):
            params = {}
    out["params"] = params if isinstance(params, dict) else {}
    out["active"] = bool(out.get("active"))
    return out


class InMemoryRuleStore(MonitorRuleStore):
    """进程内实现：开发/测试用，重启即失。"""

    def __init__(self) -> None:
        self._rows: dict[str, list[dict]] = {}

    def replace_for_session(self, session_id: str, rules: list[dict]) -> int:
        kept = [r for r in self._rows.get(session_id, []) if r.get("user_id")]
        rows = [_normalize_rule(r, session_id) for r in rules]
        rows.extend(kept)
        self._rows[session_id] = rows
        return len(rows)

    def list_by_session(self, session_id: str) -> list[dict]:
        return [r for r in self._rows.get(session_id, []) if r.get("active")]

    def list_by_company(self, company_code: str) -> list[dict]:
        return [
            r for rows in self._rows.values() for r in rows
            if r.get("active") and r.get("company_code") == company_code
        ]

    def close(self) -> None:
        return None


class SqliteRuleStore(MonitorRuleStore):
    """SQLite 实现：与会话库同文件（data/sessions.db）。"""

    def __init__(self, path: str = "data/sessions.db") -> None:
        import os as _os

        _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SQLITE_DDL)
        self._conn.commit()

    def replace_for_session(self, session_id: str, rules: list[dict]) -> int:
        # 只替换系统规则（user_id IS NULL），保留用户自定义行
        self._conn.execute(
            "DELETE FROM monitor_rules WHERE session_id = ? AND user_id IS NULL", (session_id,)
        )
        for r in rules:
            row = _normalize_rule(r, session_id)
            self._conn.execute(
                """INSERT INTO monitor_rules
                   (session_id, company_code, company_name, rule_type, source_module,
                    trigger, message, severity, action, params, user_id, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["session_id"], row["company_code"], row["company_name"],
                    row["rule_type"], row["source_module"] or "",
                    row["trigger"] or "", row["message"] or "",
                    row["severity"], row["action"], json.dumps(row["params"], ensure_ascii=False),
                    row["user_id"], int(bool(row["active"])),
                ),
            )
        self._conn.commit()
        return len(rules)

    def _select(self, where: str, args: tuple) -> list[dict]:
        rows = self._conn.execute(
            f"""SELECT id, session_id, company_code, company_name, rule_type, source_module,
                       trigger, message, severity, action, params, user_id, active
                FROM monitor_rules WHERE {where} ORDER BY id""",
            args,
        ).fetchall()
        return [_row_to_dict(dict(r)) for r in rows]

    def list_by_session(self, session_id: str) -> list[dict]:
        return self._select("session_id = ? AND active = 1", (session_id,))

    def list_by_company(self, company_code: str) -> list[dict]:
        return self._select("company_code = ? AND active = 1", (company_code,))

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()


class SupabaseRuleStore(MonitorRuleStore):
    """Supabase（PostgreSQL）实现：生产用，连接串来自 DATABASE_URL。"""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg2
            from psycopg2.extras import Json
        except ImportError as exc:
            raise ImportError("未安装 psycopg2-binary：`pip install psycopg2-binary`") from exc
        self._Json = Json
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

    def replace_for_session(self, session_id: str, rules: list[dict]) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM monitor_rules WHERE session_id = %s AND user_id IS NULL",
                (session_id,),
            )
            for r in rules:
                row = _normalize_rule(r, session_id)
                cur.execute(
                    """INSERT INTO monitor_rules
                       (session_id, company_code, company_name, rule_type, source_module,
                        trigger, message, severity, action, params, user_id, active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        row["session_id"], row["company_code"], row["company_name"],
                        row["rule_type"], row["source_module"] or "",
                        row["trigger"] or "", row["message"] or "",
                        row["severity"], row["action"], self._Json(row["params"]),
                        row["user_id"], bool(row["active"]),
                    ),
                )
        return len(rules)

    def _select(self, where: str, args: tuple) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""SELECT id, session_id, company_code, company_name, rule_type, source_module,
                           trigger, message, severity, action, params, user_id, active
                    FROM monitor_rules WHERE {where} ORDER BY created_at, id""",
                args,
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return [_row_to_dict(r) for r in rows]

    def list_by_session(self, session_id: str) -> list[dict]:
        return self._select("session_id = %s AND active = TRUE", (session_id,))

    def list_by_company(self, company_code: str) -> list[dict]:
        return self._select("company_code = %s AND active = TRUE", (company_code,))

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()


def create_rule_store() -> MonitorRuleStore:
    """按环境变量创建规则存储（与 create_session_store 同源）。

    - memory：进程内（开发/测试）
    - supabase：Supabase/PostgreSQL（生产，需 DATABASE_URL）
    - sqlite（默认）：本地持久化 data/sessions.db
    """
    backend = os.getenv("SESSION_STORE", "sqlite").strip().lower()
    if backend == "memory":
        return InMemoryRuleStore()
    if backend in ("supabase", "postgres"):
        dsn = os.getenv("DATABASE_URL", "")
        if not dsn:
            raise ValueError("SESSION_STORE=supabase 需要 DATABASE_URL")
        return SupabaseRuleStore(dsn)
    return SqliteRuleStore(os.getenv("SESSIONS_DB", "data/sessions.db"))
