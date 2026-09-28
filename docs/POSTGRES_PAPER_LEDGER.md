# PostgreSQL critical PAPER ledger design (Phase 2H groundwork)

This document and `db/migrations/0002_critical_paper.sql` are **unapplied design**;
there is no authenticated PostgreSQL connection or transactional Python port yet.
The migration is for an isolated logical-$100 Alpaca BTC/USD **PAPER** runtime.
It adds paper-only CHECKs at the database level, initial operator HALT, exact
NUMERIC values, append-only audit, unique provider fill/order identifiers,
logical account/cash state and a unique partial index enforcing **at most one
unreconciled provider order** across concurrent worker processes.

The daemon MUST NEVER be pointed at this schema before a fully tested Python
transactional adapter replaces the SQLite `PersistentPaperOrderStore` path. A
partially migrated store or unverified conversion must remain disabled.

## Required PostgreSQL transaction pattern

For each candidate trade, use one `READ COMMITTED` transaction that locks
`runtime_controls` and `logical_account` singleton rows `FOR UPDATE`. Verify
operator halt, current risk policy hash, holdings, pending reservations,
provider/order drift and the actual validated Guardian result **inside** that
transaction before recording a draft. Do not recompute cash from the large
provider demo balance. SQL `NUMERIC` maps to Python `Decimal`, never float.

Begin paper POST intent via a separate committed transaction: under the same
row locks, confirm the previously persisted Guardian-approved draft payload and
its unique client-order ID match exactly, reject if another order is unresolved,
then atomically insert `paper_orders(stage='submission_pending')` and an audit
event; **commit before any network POST**. The unique partial index prevents two
workers from both inserting unresolved orders, even if application lock logic
regresses. Timeout or crash after commit becomes `unknown_result`; lookup the
provider by that same client ID, never send a blind second POST.

The audited reconciliation of terminal provider order, cash, position and fill
must be applied in **one** database transaction, with provider fill ID de-dupe.
Release reservations and set stage to `reconciled` only after verified external
accounting. Pending BTC-denominated fee settlement remains a separate checked
transaction. `audit_events` cannot be UPDATEd/DELETEd by the normal runtime role.

Use separate migration and least-privilege runtime DB roles. Application role
must not have table ownership, DDL, TRUNCATE, BYPASSRLS or superuser rights;
test audit immutability, migrations, crash recovery and concurrent duplicate
submission against **an actual PostgreSQL instance** before wiring deployment.
The static source/schema regression tests are not a substitute for those tests.

SQLite with a single-process lock and consistent backups remains the only
working persistence backend until this full transaction path and tests exist.
