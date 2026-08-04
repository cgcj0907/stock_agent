"""PostgreSQL 存储（Supabase）：生产使用，连接串来自 DATABASE_URL（Pooler 6543）。

依赖：pip install psycopg2-binary（已在 pyproject 声明）。
"""
from __future__ import annotations

from .base import DATE_COLUMN, NUMERIC_COLUMNS, SCHEMA, MarketStorage


def _ddl(table: str) -> str:
    cols, pk = SCHEMA[table]["columns"], SCHEMA[table]["pk"]
    numeric = NUMERIC_COLUMNS.get(table, set())
    defs = ", ".join(
        f"{c} {'DOUBLE PRECISION' if c in numeric else 'TEXT'}" for c in cols
    )
    return (
        f"CREATE TABLE IF NOT EXISTS {table} ({defs}, "
        f"updated_at TIMESTAMPTZ DEFAULT now(), "
        f"PRIMARY KEY ({', '.join(pk)}))"
    )


class PostgresMarketStorage(MarketStorage):
    name = "postgres"

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg2
        except ImportError as exc:
            raise ImportError(
                "未安装 psycopg2-binary：`pip install psycopg2-binary`（生产部署镜像已包含）"
            ) from exc
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = True
        with self._conn.cursor() as cur:
            for table in SCHEMA:
                cur.execute(_ddl(table))

    def upsert(self, table: str, code: str, records: list[dict]) -> int:
        cols = [c for c in SCHEMA[table]["columns"] if c != "code"]
        pk = SCHEMA[table]["pk"]
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in SCHEMA[table]["columns"] if c not in pk
        )
        sql = (
            f"INSERT INTO {table} ({', '.join(['code'] + cols)}) "
            f"VALUES ({', '.join(['%s'] * (len(cols) + 1))}) "
            f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {updates}"
        )
        if not records:
            return 0
        rows = [[code] + [r.get(c) for c in cols] for r in records]
        # 单事务批量：避免逐条自动提交（免费版池化连接逐条提交非常慢）
        self._conn.autocommit = False
        try:
            with self._conn.cursor() as cur:
                cur.executemany(sql, rows)
            self._conn.commit()
        finally:
            self._conn.autocommit = True
        return len(records)

    def latest(self, table: str, code: str) -> str | None:
        date_col = DATE_COLUMN.get(table)
        if date_col is None:
            return None
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT MAX({date_col}) FROM {table} WHERE code = %s", (code,))
            row = cur.fetchone()
        return row[0] if row else None

    def records_before(self, table: str, code: str, as_of: str | None = None) -> list[dict]:
        cols = SCHEMA[table]["columns"]
        date_col = DATE_COLUMN.get(table)
        with self._conn.cursor() as cur:
            if as_of and date_col:
                cur.execute(
                    f"SELECT {', '.join(cols)} FROM {table} WHERE code = %s AND {date_col} <= %s",
                    (code, as_of),
                )
            else:
                cur.execute(f"SELECT {', '.join(cols)} FROM {table} WHERE code = %s", (code,))
            rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def all_records(self, table: str) -> list[dict]:
        cols = SCHEMA[table]["columns"]
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(cols)} FROM {table}")
            rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        with self._conn.cursor() as cur:
            for table in SCHEMA:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT code) FROM company")
            counts["_companies"] = cur.fetchone()[0]
        return counts

    def close(self) -> None:
        self._conn.close()
