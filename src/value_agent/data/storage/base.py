"""行情/财报存储抽象：业务代码只依赖此接口，不感知 SQLite 还是 PostgreSQL。"""
from __future__ import annotations

from abc import ABC, abstractmethod

# 表结构定义（规范化字段，数据源在适配器里归一化）
SCHEMA: dict[str, dict] = {
    "company": {
        "columns": ["code", "ts_code", "name", "industry", "list_date"],
        "pk": ["code"],
    },
    "financials": {
        "columns": [
            "code", "period", "roe", "grossprofit_margin", "netprofit_margin",
            "debt_to_assets", "ocfps", "eps", "ocf_to_np",
            # 1.1/5.2/5.4/1.4（backlog 第二批）：资产负债表明细派生字段
            "bvps",            # 每股净资产（NAV 基数）
            "ncav_ps",         # 每股净流动资产 = (流动资产−总负债)/股本（NCAV 基数）
            "rd_ratio",        # 研发费用率（研发费用/营业收入）
            "interest_debt_ratio",    # 有息负债率（短期借款+长期借款+应付债券 / 总资产）
            "contract_liability_ratio",  # 合同负债/总资产（订单型行业杠杆口径修正）
            "ocf_to_np_parent",  # 1.4：归母口径 经营现金流净额/归母净利润
        ],
        "pk": ["code", "period"],
    },
    "daily_price": {
        "columns": ["code", "trade_date", "open", "close", "high", "low", "volume", "turnover"],
        "pk": ["code", "trade_date"],
    },
    "valuation_history": {
        "columns": ["code", "trade_date", "pe", "pe_ttm", "pb", "ps", "dv_ttm", "total_mv"],
        "pk": ["code", "trade_date"],
    },
    "dividends": {
        "columns": ["code", "period", "cash_div_tax", "div_proc"],
        "pk": ["code", "period"],
    },
    # 7.1（backlog）：北向资金个股持股（免费源 best-effort，未接入时表为空）
    "northbound": {
        "columns": ["code", "trade_date", "hold_shares", "hold_ratio"],
        "pk": ["code", "trade_date"],
    },
    # 7.2（backlog）：个股两融余额（沪/深交易所披露，best-effort）
    "margin": {
        "columns": ["code", "trade_date", "margin_balance", "fin_balance", "sec_balance"],
        "pk": ["code", "trade_date"],
    },
    # 6.1（backlog）：治理事件（质押/减持/监管/审计/并购/回购）落库，
    # M6 governance_events 数据源接入后可直接持久化；未接入时表为空不影响评分。
    "governance_events": {
        "columns": ["code", "event_date", "kind", "holder", "ratio", "description"],
        "pk": ["code", "event_date", "kind"],
    },
}

# 只追加、不覆盖的表：写库前先取该股在表内的最新日期，仅写入比它新的行；
# 历史行保留首次入库值，绝不覆盖。行情属于时间序列快照，重跑全量/重复拉取不应改写历史。
# 财报等结构化表仍走覆盖更新（ingest_company 可修正已入库财报）。
INSERT_ONLY_TABLES: frozenset[str] = frozenset({"daily_price", "valuation_history"})

# 各表用于"最新日期"的列（YYYYMMDD 字符串，字典序即时间序）
DATE_COLUMN: dict[str, str] = {
    "financials": "period",
    "daily_price": "trade_date",
    "valuation_history": "trade_date",
    "dividends": "period",
    "governance_events": "event_date",
    "northbound": "trade_date",
    "margin": "trade_date",
}

# 数值列（DDL 生成时用 DOUBLE PRECISION，其余 TEXT）—— SCHEMA 是唯一事实来源
NUMERIC_COLUMNS: dict[str, set[str]] = {
    "company": set(),
    "financials": {"roe", "grossprofit_margin", "netprofit_margin", "debt_to_assets", "ocfps", "eps",
                   "ocf_to_np", "bvps", "ncav_ps", "rd_ratio", "interest_debt_ratio",
                   "contract_liability_ratio", "ocf_to_np_parent"},
    "daily_price": {"open", "close", "high", "low", "volume", "turnover"},
    "valuation_history": {"pe", "pe_ttm", "pb", "ps", "dv_ttm", "total_mv"},
    "dividends": {"cash_div_tax"},
    "governance_events": {"ratio"},
    "northbound": {"hold_shares", "hold_ratio"},
    "margin": {"margin_balance", "fin_balance", "sec_balance"},
}


def generate_pg_ddl() -> str:
    """从 SCHEMA 生成 PostgreSQL DDL（Supabase 用）。

    唯一事实来源 = SCHEMA；`python -m value_agent data ddl` 输出，
    docs/07 与 data/schema.sql 均由它生成，避免手改漂移。
    """
    lines = [
        "-- 由 SCHEMA 自动生成（python -m value_agent data ddl），请勿手改",
        "-- Supabase 免费版无 TimescaleDB：行情用普通表 + 复合索引",
        "",
    ]
    for table, meta in SCHEMA.items():
        defs = [
            f"    {c} {'DOUBLE PRECISION' if c in NUMERIC_COLUMNS.get(table, set()) else 'TEXT'}"
            for c in meta["columns"]
        ]
        defs.append("    updated_at TIMESTAMPTZ DEFAULT now()")
        defs.append(f"    PRIMARY KEY ({', '.join(meta['pk'])})")
        lines.append(f"CREATE TABLE IF NOT EXISTS {table} (")
        lines.append(",\n".join(defs))
        lines.append(");")
        if table in ("daily_price", "valuation_history"):
            lines.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_code_date "
                f"ON {table} (code, {DATE_COLUMN[table]});"
            )
        lines.append("")
    lines += [
        "-- 自选股池（与 config/watchlist.yaml 对应）",
        "CREATE TABLE IF NOT EXISTS watchlist (",
        "    code TEXT PRIMARY KEY,",
        "    name TEXT,",
        "    added_at TIMESTAMPTZ DEFAULT now()",
        ");",
        "",
    ]
    return "\n".join(lines)


class MarketStorage(ABC):
    """行情/财报存储。实现：SqliteMarketStorage（本地）、PostgresMarketStorage（Supabase）。"""

    name: str = "base"

    @abstractmethod
    def upsert(self, table: str, code: str, records: list[dict]) -> int:
        """按 code 写入/更新记录（自动过滤 schema 外的字段、注入 code 列），返回写入条数。"""

    @abstractmethod
    def latest(self, table: str, code: str) -> str | None:
        """返回该表该 code 的最新日期（YYYYMMDD），无数据返回 None。"""

    @abstractmethod
    def records_before(self, table: str, code: str, as_of: str | None = None) -> list[dict]:
        """返回该 code 在 as_of（YYYYMMDD，含）之前的所有记录（point-in-time 快照用）。"""

    @abstractmethod
    def all_records(self, table: str) -> list[dict]:
        """返回整表所有记录（校验/导出用）。"""

    @abstractmethod
    def stats(self) -> dict:
        """返回各表行数与公司数，用于 status 展示。"""

    @abstractmethod
    def list_codes(self) -> list[str]:
        """返回 company 表全部股票代码（daily 任务默认遍历这些代码）。"""

    @abstractmethod
    def close(self) -> None: ...
