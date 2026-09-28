-- DESIGN MIGRATION, NOT APPLIED. Requires an isolated PostgreSQL database and
-- a separate migration/operator approval. There is NO live schema or endpoint.
-- A separate runtime role with minimal privileges must not own migration objects.
-- All currency uses exact NUMERIC. Transactional code must lock controls and
-- account singleton rows with FOR UPDATE before recording reserves/order intent.
BEGIN;
CREATE SCHEMA IF NOT EXISTS signal_vault_paper;

CREATE TABLE IF NOT EXISTS signal_vault_paper.runtime_controls (
    singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK(singleton=1),
    mode TEXT NOT NULL DEFAULT 'paper' CHECK(mode = 'paper'),
    operator_halted BOOLEAN NOT NULL DEFAULT TRUE,
    halt_reason TEXT NOT NULL DEFAULT 'First start requires operator authorization',
    policy_sha256 CHAR(64),
    revision BIGINT NOT NULL DEFAULT 0 CHECK(revision >= 0),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signal_vault_paper.logical_account (
    singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK(singleton=1),
    cash_usd NUMERIC(28,12) NOT NULL DEFAULT 100 CHECK(cash_usd >= 0),
    btc_qty NUMERIC(32,18) NOT NULL DEFAULT 0 CHECK(btc_qty >= 0),
    btc_cost_basis_usd NUMERIC(28,12) NOT NULL DEFAULT 0 CHECK(btc_cost_basis_usd >= 0),
    realized_pnl_usd NUMERIC(28,12) NOT NULL DEFAULT 0,
    fees_usd_equiv NUMERIC(28,12) NOT NULL DEFAULT 0 CHECK(fees_usd_equiv >= 0),
    peak_equity_usd NUMERIC(28,12) NOT NULL DEFAULT 100 CHECK(peak_equity_usd >= 0),
    session_start_equity_usd NUMERIC(28,12) NOT NULL DEFAULT 100 CHECK(session_start_equity_usd >= 0),
    session_date_utc DATE NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')::date,
    revision BIGINT NOT NULL DEFAULT 0 CHECK(revision >= 0),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signal_vault_paper.paper_drafts (
    client_order_id TEXT PRIMARY KEY CHECK(length(client_order_id) BETWEEN 1 AND 128),
    intent_sha256 CHAR(64) NOT NULL,
    signal_id TEXT NOT NULL CHECK(length(signal_id) BETWEEN 1 AND 128),
    guardian_policy_sha256 CHAR(64) NOT NULL,
    venue TEXT NOT NULL DEFAULT 'alpaca' CHECK(venue = 'alpaca'),
    mode TEXT NOT NULL DEFAULT 'paper' CHECK(mode = 'paper'),
    symbol TEXT NOT NULL DEFAULT 'BTC/USD' CHECK(symbol = 'BTC/USD'),
    side TEXT NOT NULL CHECK(side IN ('buy','sell')),
    status TEXT NOT NULL CHECK(status IN ('DRAFT_APPROVED','VOID')),
    reserved_usd NUMERIC(28,12) NOT NULL CHECK(reserved_usd >= 0),
    notional_usd NUMERIC(28,12) NOT NULL CHECK(notional_usd > 0),
    payload JSONB NOT NULL CHECK(jsonb_typeof(payload) = 'object'),
    created_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sv_paper_drafts_reserved
    ON signal_vault_paper.paper_drafts(status) WHERE status = 'DRAFT_APPROVED';

CREATE TABLE IF NOT EXISTS signal_vault_paper.paper_orders (
    client_order_id TEXT PRIMARY KEY REFERENCES signal_vault_paper.paper_drafts(client_order_id),
    broker_order_id TEXT UNIQUE,
    stage TEXT NOT NULL CHECK(stage IN (
        'draft_approved','submission_pending','unknown_result','broker_accepted',
        'partially_filled','broker_terminal_unreconciled','reconciled')),
    provider_status TEXT,
    cumulative_filled_qty NUMERIC(32,18) NOT NULL DEFAULT 0 CHECK(cumulative_filled_qty >= 0),
    filled_avg_price NUMERIC(28,12),
    reconciled BOOLEAN NOT NULL DEFAULT FALSE,
    revision BIGINT NOT NULL DEFAULT 0 CHECK(revision >= 0),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((cumulative_filled_qty = 0 AND filled_avg_price IS NULL)
        OR (cumulative_filled_qty > 0 AND filled_avg_price > 0)),
    CHECK ((stage = 'reconciled') = reconciled)
);
-- Cross-process protection: AT MOST ONE unresolved provider order in this
-- initial single-market experiment. A second concurrent POST intent fails at DB.
CREATE UNIQUE INDEX IF NOT EXISTS ux_sv_paper_one_unresolved_order
    ON signal_vault_paper.paper_orders ((1)) WHERE stage <> 'reconciled';

CREATE TABLE IF NOT EXISTS signal_vault_paper.provider_fills (
    provider_fill_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL REFERENCES signal_vault_paper.paper_orders(client_order_id),
    broker_order_id TEXT NOT NULL,
    base_qty NUMERIC(32,18) NOT NULL CHECK(base_qty > 0),
    price_usd NUMERIC(28,12) NOT NULL CHECK(price_usd > 0),
    fee_usd_equiv NUMERIC(28,12) NOT NULL DEFAULT 0 CHECK(fee_usd_equiv >= 0),
    executed_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sv_paper_fills_order
    ON signal_vault_paper.provider_fills(client_order_id, executed_utc);

CREATE TABLE IF NOT EXISTS signal_vault_paper.applied_provider_orders (
    client_order_id TEXT PRIMARY KEY REFERENCES signal_vault_paper.paper_orders(client_order_id),
    broker_order_id TEXT NOT NULL UNIQUE,
    side TEXT NOT NULL CHECK(side IN ('buy','sell')),
    filled_qty NUMERIC(32,18) NOT NULL CHECK(filled_qty >= 0),
    avg_price NUMERIC(28,12),
    fee_usd_equiv NUMERIC(28,12) NOT NULL CHECK(fee_usd_equiv >= 0),
    provider_btc_qty NUMERIC(32,18) NOT NULL CHECK(provider_btc_qty >= 0),
    applied_utc TIMESTAMPTZ NOT NULL,
    CHECK ((filled_qty = 0 AND avg_price IS NULL) OR
           (filled_qty > 0 AND avg_price > 0))
);

CREATE TABLE IF NOT EXISTS signal_vault_paper.pending_fee_audits (
    client_order_id TEXT PRIMARY KEY REFERENCES signal_vault_paper.applied_provider_orders(client_order_id),
    broker_order_id TEXT NOT NULL UNIQUE,
    provisional_fee_usd_equiv NUMERIC(28,12) NOT NULL CHECK(provisional_fee_usd_equiv >= 0),
    inferred_btc_fee_qty NUMERIC(32,18) NOT NULL CHECK(inferred_btc_fee_qty >= 0),
    created_utc TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_vault_paper.audit_events (
    seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_order_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(length(event_type) BETWEEN 1 AND 64),
    details JSONB NOT NULL CHECK(jsonb_typeof(details) = 'object'),
    occurred_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sv_paper_events_by_order
    ON signal_vault_paper.audit_events(client_order_id,seq);
CREATE OR REPLACE FUNCTION signal_vault_paper.prevent_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Signal Vault audit history is immutable';
END;
$$;
DROP TRIGGER IF EXISTS audit_events_append_only ON signal_vault_paper.audit_events;
CREATE TRIGGER audit_events_append_only
    BEFORE UPDATE OR DELETE ON signal_vault_paper.audit_events
    FOR EACH ROW EXECUTE FUNCTION signal_vault_paper.prevent_audit_mutation();

-- Idempotent initial funding; rerunning a migration never resets or enlarges
-- an existing logical account. Runtime remains HALTED on its first bootstrap.
INSERT INTO signal_vault_paper.runtime_controls(singleton) VALUES (1)
    ON CONFLICT (singleton) DO NOTHING;
INSERT INTO signal_vault_paper.logical_account(singleton) VALUES (1)
    ON CONFLICT (singleton) DO NOTHING;
COMMIT;
