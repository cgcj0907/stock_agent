"""存储工厂：按 settings / 参数选择 SQLite 或 PostgreSQL。"""
from __future__ import annotations

from .base import MarketStorage
from .sqlite_storage import SqliteMarketStorage


def create_storage(settings: dict | None = None, *, backend: str | None = None) -> MarketStorage:
    """backend 优先取参数；否则取 settings.storage.backend；默认 sqlite。"""
    settings = settings or {}
    storage_cfg = settings.get("storage", {})
    chosen = backend or storage_cfg.get("backend", "sqlite")
    if chosen in ("postgres", "supabase"):
        dsn = storage_cfg.get("url")
        if not dsn:
            raise ValueError("PostgreSQL 存储需要 DATABASE_URL（storage.url）")
        from .postgres_storage import PostgresMarketStorage

        return PostgresMarketStorage(dsn)
    return SqliteMarketStorage(storage_cfg.get("path", "data/market.db"))
