"""PostgreSQL 存储（Supabase）：生产使用，连接串来自 DATABASE_URL（Pooler 6543）。

依赖：pip install psycopg2-binary（已在 pyproject 声明）。
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from .base import DATE_COLUMN, INSERT_ONLY_TABLES, NUMERIC_COLUMNS, SCHEMA, MarketStorage

logger = logging.getLogger(__name__)

# 连接加固（生产稽核 2026-08-09：M7 卡「价格与估值分位」根因之一）：
# - connect_timeout：pooler 不可达时 ≤15s 快速失败，而不是 TCP 默认分钟级挂起；
# - keepalives：pooler 静默断开（SSL EOF）时能及时感知；
# - statement_timeout：单条查询 30s 兜底，杜绝坏连接上的查询无限阻塞。
_CONNECT_TIMEOUT = 15
_STATEMENT_TIMEOUT_MS = 30_000
_CONNECT_KWARGS = {
    "connect_timeout": _CONNECT_TIMEOUT,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
}


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
        self._psycopg2 = psycopg2
        self._dsn = dsn
        self._conn = self._connect()
        # 建表/迁移只在初始化做一次（重连不重复 DDL）
        with self._conn.cursor() as cur:
            for table in SCHEMA:
                cur.execute(_ddl(table))
            # 存量库迁移：老 daily_price 表没有 turnover 列（情绪指标），补上（幂等）
            cur.execute(
                "ALTER TABLE daily_price ADD COLUMN IF NOT EXISTS turnover DOUBLE PRECISION"
            )

    def _connect(self):
        conn = self._psycopg2.connect(self._dsn, **_CONNECT_KWARGS)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {_STATEMENT_TIMEOUT_MS}")
        return conn

    def _ensure_alive(self) -> None:
        """连接被 pooler 静默断开（SSL EOF）后重连；已关闭也重建。"""
        if self._conn.closed:
            self._conn = self._connect()

    @contextmanager
    def _cursor(self):
        """安全游标：仅保证连接存活（不在此重试——contextmanager 内 catch 后再次
        yield 会触发 "generator didn't stop after throw()"，重试逻辑放在方法层）。"""
        self._ensure_alive()
        with self._conn.cursor() as cur:
            yield cur

    def _read(self, fn):
        """读操作统一入口：连接异常（SSL EOF/超时）时重连重试一次；幂等读安全。"""
        for attempt in (1, 2):
            try:
                return fn()
            except self._psycopg2.OperationalError as exc:
                logger.warning("PG 读连接异常（第 %d 次重试）：%s，重连", attempt, exc)
                self._conn = self._connect()
                if attempt == 2:
                    raise

    def upsert(self, table: str, code: str, records: list[dict]) -> int:
        if table in INSERT_ONLY_TABLES:
            # 只追加：取该股在表内的最新日期，仅写入比它新的行（历史行一律保留首次入库值）
            date_col = DATE_COLUMN.get(table)
            latest = self.latest(table, code)
            records = [
                r for r in records
                if latest is None or str(r.get(date_col) or "") > latest
            ]
            if not records:
                return 0
        cols = [c for c in SCHEMA[table]["columns"] if c != "code"]
        pk = SCHEMA[table]["pk"]
        if table in INSERT_ONLY_TABLES:
            on_conflict = f"ON CONFLICT ({', '.join(pk)}) DO NOTHING"
        else:
            updates = ", ".join(
                f"{c} = EXCLUDED.{c}" for c in SCHEMA[table]["columns"] if c not in pk
            )
            on_conflict = f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {updates}"
        sql = (
            f"INSERT INTO {table} ({', '.join(['code'] + cols)}) "
            f"VALUES ({', '.join(['%s'] * (len(cols) + 1))}) "
            f"{on_conflict}"
        )
        if not records:
            return 0
        rows = [[code] + [r.get(c) for c in cols] for r in records]
        # 单事务批量：避免逐条自动提交（免费版池化连接逐条提交非常慢）；
        # 坏连接（SSL EOF）时重连重试一次，避免后台回写永久失败
        for attempt in (1, 2):
            try:
                self._ensure_alive()
                self._conn.autocommit = False
                with self._conn.cursor() as cur:
                    cur.executemany(sql, rows)
                self._conn.commit()
                return len(records)
            except self._psycopg2.OperationalError as exc:
                logger.warning("PG upsert 连接异常（第 %d 次）：%s，重连", attempt, exc)
                try:
                    self._conn.rollback()
                except Exception as exc2:  # noqa: BLE001
                    logger.debug("PG rollback 失败（可忽略）：%s", exc2)
                self._conn = self._connect()
                if attempt == 2:
                    raise
            finally:
                self._conn.autocommit = True

    def latest(self, table: str, code: str) -> str | None:
        date_col = DATE_COLUMN.get(table)
        if date_col is None:
            return None

        def _q():
            with self._cursor() as cur:
                cur.execute(
                    f"SELECT MAX({date_col}) FROM {table} WHERE code = %s", (code,)
                )
                row = cur.fetchone()
            return row[0] if row else None

        return self._read(_q)

    def records_before(self, table: str, code: str, as_of: str | None = None) -> list[dict]:
        cols = SCHEMA[table]["columns"]
        date_col = DATE_COLUMN.get(table)

        def _q():
            with self._cursor() as cur:
                if as_of and date_col:
                    cur.execute(
                        f"SELECT {', '.join(cols)} FROM {table} "
                        f"WHERE code = %s AND {date_col} <= %s",
                        (code, as_of),
                    )
                else:
                    cur.execute(
                        f"SELECT {', '.join(cols)} FROM {table} WHERE code = %s", (code,)
                    )
                rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]

        return self._read(_q)

    def all_records(self, table: str) -> list[dict]:
        cols = SCHEMA[table]["columns"]

        def _q():
            with self._cursor() as cur:
                cur.execute(f"SELECT {', '.join(cols)} FROM {table}")
                rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]

        return self._read(_q)

    def stats(self) -> dict:
        def _q():
            counts: dict[str, int] = {}
            with self._cursor() as cur:
                for table in SCHEMA:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(DISTINCT code) FROM company")
                counts["_companies"] = cur.fetchone()[0]
            return counts

        return self._read(_q)

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
