-- DESIGN SCHEMA ONLY (PostgreSQL). Not applied by the Phase 1 offline demo.
-- Values use NUMERIC, never binary floating point, for financial amounts.
CREATE TABLE IF NOT EXISTS strategy_versions (
    id UUID PRIMARY KEY,
    strategy_key TEXT NOT NULL,
    immutable_config JSONB NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','backtest','paper','retired')),
    approved_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id UUID PRIMARY KEY,
    venue TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode = 'paper'),
    equity_usd NUMERIC(24,10) NOT NULL,
    cash_usd NUMERIC(24,10) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY,
    strategy_version_id UUID REFERENCES strategy_versions(id),
    venue TEXT NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_data_time TIMESTAMPTZ NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS risk_decisions (
    id UUID PRIMARY KEY,
    signal_id UUID REFERENCES signals(id),
    policy_hash TEXT NOT NULL,
    allowed BOOLEAN NOT NULL,
    reasons JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    signal_id UUID REFERENCES signals(id),
    risk_decision_id UUID REFERENCES risk_decisions(id),
    venue TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode = 'paper'),
    client_order_id TEXT NOT NULL UNIQUE,
    broker_order_id TEXT UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy','sell')),
    notional_usd NUMERIC(24,10) NOT NULL CHECK(notional_usd > 0),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fills (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    provider_fill_id TEXT NOT NULL UNIQUE,
    qty NUMERIC(30,16) NOT NULL CHECK(qty > 0),
    price NUMERIC(24,10) NOT NULL CHECK(price >= 0),
    fee_usd NUMERIC(24,10) NOT NULL DEFAULT 0 CHECK(fee_usd >= 0),
    filled_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    happened_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_events_correlation ON audit_events(correlation_id, happened_at);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status, updated_at);
CREATE INDEX IF NOT EXISTS ix_signals_symbol_time ON signals(symbol, created_at);
