-- 由 SCHEMA 自动生成（python -m value_agent data ddl），请勿手改
-- Supabase 免费版无 TimescaleDB：行情用普通表 + 复合索引

CREATE TABLE IF NOT EXISTS company (
    code TEXT,
    ts_code TEXT,
    name TEXT,
    industry TEXT,
    list_date TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code)
);

CREATE TABLE IF NOT EXISTS financials (
    code TEXT,
    period TEXT,
    roe DOUBLE PRECISION,
    grossprofit_margin DOUBLE PRECISION,
    netprofit_margin DOUBLE PRECISION,
    debt_to_assets DOUBLE PRECISION,
    ocfps DOUBLE PRECISION,
    eps DOUBLE PRECISION,
    ocf_to_np DOUBLE PRECISION,
    bvps DOUBLE PRECISION,
    ncav_ps DOUBLE PRECISION,
    rd_ratio DOUBLE PRECISION,
    interest_debt_ratio DOUBLE PRECISION,
    contract_liability_ratio DOUBLE PRECISION,
    ocf_to_np_parent DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code, period)
);

CREATE TABLE IF NOT EXISTS daily_price (
    code TEXT,
    trade_date TEXT,
    open DOUBLE PRECISION,
    close DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    turnover DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_price_code_date ON daily_price (code, trade_date);

CREATE TABLE IF NOT EXISTS valuation_history (
    code TEXT,
    trade_date TEXT,
    pe DOUBLE PRECISION,
    pe_ttm DOUBLE PRECISION,
    pb DOUBLE PRECISION,
    ps DOUBLE PRECISION,
    dv_ttm DOUBLE PRECISION,
    total_mv DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_valuation_history_code_date ON valuation_history (code, trade_date);

CREATE TABLE IF NOT EXISTS dividends (
    code TEXT,
    period TEXT,
    cash_div_tax DOUBLE PRECISION,
    div_proc TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code, period)
);

CREATE TABLE IF NOT EXISTS northbound (
    code TEXT,
    trade_date TEXT,
    hold_shares DOUBLE PRECISION,
    hold_ratio DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code, trade_date)
);

CREATE TABLE IF NOT EXISTS margin (
    code TEXT,
    trade_date TEXT,
    margin_balance DOUBLE PRECISION,
    fin_balance DOUBLE PRECISION,
    sec_balance DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code, trade_date)
);

CREATE TABLE IF NOT EXISTS governance_events (
    code TEXT,
    event_date TEXT,
    kind TEXT,
    holder TEXT,
    ratio DOUBLE PRECISION,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (code, event_date, kind)
);

-- 自选股池（与 config/watchlist.yaml 对应）
CREATE TABLE IF NOT EXISTS watchlist (
    code TEXT PRIMARY KEY,
    name TEXT,
    added_at TIMESTAMPTZ DEFAULT now()
);

