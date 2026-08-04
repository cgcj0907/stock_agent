"""SQLite 存储：本地开发/测试（无外部依赖）。生产用 PostgresMarketStorage。"""
from __future__ import annotations

import os
import sqlite3

from .base import DATE_COLUMN, NUMERIC_COLUMNS, SCHEMA, MarketStorage


def _ddl(table: str) -> str:
    """按 SCHEMA 生成 SQLite 建表语句（数值列用 REAL，读回保持类型）。"""
    cols, pk = SCHEMA[table]["columns"], SCHEMA[table]["pk"]
    numeric = NUMERIC_COLUMNS.get(table, set())
    defs = ", ".join(f"{c} {'REAL' if c in numeric else 'TEXT'}" for c in cols)
    return f"CREATE TABLE IF NOT EXISTS {table} ({defs}, PRIMARY KEY ({', '.join(pk)}))"


class SqliteMarketStorage(MarketStorage):
    name = "sqlite"

    def __init__(self, path: str = "data/market.db") -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path)
        for table in SCHEMA:
            self._conn.execute(_ddl(table))
        self._conn.commit()

    def upsert(self, table: str, code: str, records: list[dict]) -> int:
        if not records:
            return 0
        cols = [c for c in SCHEMA[table]["columns"] if c != "code"]
        placeholders = ", ".join("?" * (len(cols) + 1))
        conflict = ", ".join(SCHEMA[table]["pk"])
        updates = ", ".join(f"{c}=excluded.{c}" for c in SCHEMA[table]["columns"] if c not in SCHEMA[table]["pk"])
        sql = (
            f"INSERT INTO {table} ({', '.join(['code'] + cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        )
        rows = [[code] + [r.get(c) for c in cols] for r in records]
        self._conn.executemany(sql, rows)
        self._conn.commit()
        return len(records)

    def latest(self, table: str, code: str) -> str | None:
        date_col = DATE_COLUMN.get(table)
        if date_col is None:
            return None
        row = self._conn.execute(
            f"SELECT MAX({date_col}) FROM {table} WHERE code = ?", (code,)
        ).fetchone()
        return row[0]

    def records_before(self, table: str, code: str, as_of: str | None = None) -> list[dict]:
        cols = SCHEMA[table]["columns"]
        date_col = DATE_COLUMN.get(table)
        if as_of and date_col:
            rows = self._conn.execute(
                f"SELECT {', '.join(cols)} FROM {table} WHERE code = ? AND {date_col} <= ?",
                (code, as_of),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT {', '.join(cols)} FROM {table} WHERE code = ?", (code,)
            ).fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def all_records(self, table: str) -> list[dict]:
        cols = SCHEMA[table]["columns"]
        rows = self._conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for table in SCHEMA:
            counts[table] = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        counts["_companies"] = self._conn.execute("SELECT COUNT(DISTINCT code) FROM company").fetchone()[0]
        return counts

    def close(self) -> None:
        self._conn.close()
