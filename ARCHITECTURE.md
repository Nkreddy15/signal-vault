# SIGNAL VAULT — System architecture v0.1

Status: **approved for Phase 1 development, paper-only; all real-money actions explicitly prohibited**. Date: 2026-09-28.

## Purpose and rollout

One private, modular autonomous trading application capable of adding crypto, equities and eligible event contracts through adapters without rebuilding its common decision, risk, audit and operation layers. Initial end-to-end venue target: Alpaca paper BTC/USD, with an account **logically treated as $100**, even if the default broker sandbox balance is different. A proposed real-money $100 trial on November 1 is conditional, *never automatic*.

## Architecture choice

A modular monolith with explicit domain contracts is appropriate for one developer/team and a small pilot. Do not introduce distributed microservices or six paid LLMs merely to mimic a marketing screenshot. The six named agents are **logical components**; a deterministic policy gate is the only order authority. No AI may modify its own financial permissions. All monetary amounts use `Decimal` and persistent SQL `NUMERIC`, with time in UTC and timezone-aware timestamps.

```text
 PUBLIC MARKET DATA (read-only; source timestamp + freshness + quality checks)
                |
        market-specific adapter ---> normalized instrument/quote/cost envelope
                |
          SCOUT (candidates) -- evidence IDs --> ANALYST (features)
                |
         STRATEGIST (versioned trade proposal, or HOLD)
                |
     optional LLM advisory (bounded structured output, never executes tools)
                |
         GUARDIAN (deterministic, signed/versioned risk policy)
              /   \
          REJECT    approved trade intent (persisted with idempotency key)
                        |
             EXECUTOR (paper-only venue adapter)
                        |
              provider order receipt (not presumed fill)
                        |
          AUDITOR (poll/stream fills, balances, cash, pending orders)
                        |
          append-only activity journal + performance calculation
                        |
        OWNER UI + emergency stop + alerts + daily report
```

Every stateful component reads from or writes to PostgreSQL in deployment. A durable job scheduler/worker controls retries. A second process must not bypass portfolio locks or submit a second buy against reserved capital. In Phase 1 the offline skeleton has no network clients or daemon.

## Modules and planned interfaces

| Boundary | Input | Output | Principle |
|---|---|---|---|
| `market_data` | venue streams and REST | `Instrument`, timestamped `Quote` / bars | reject stale, crossed or missing quotes |
| `scout` | cleaned bars | candidate signals | no mandate to trade every day |
| `analyst` | candidate + features | immutable evidence record | reproducible inputs |
| `strategist` | versioned evidence | `TradeIntent` or HOLD | no direct broker permission |
| `ai_advisory` | bounded public data | validated suggestion | never receives keys or raw API tools |
| `risk` | intent + portfolio snapshot + venue rules | approve/reject + reasons | no model bypass; fail closed |
| `execution` | previously checked intent | idempotent order submission | paper endpoint hard-bound |
| `accounting` | order/fill/activity streams | reconciled NAV and P&L | orders are not fills |
| `operations` | heartbeat/errors | stop/pause/retry + alerts | no duplicate trades on restart |
| `api/web` | read-only views, owner control | dashboard, safe operator halt | authentication / audit |

Present modules include Phase 1 `domain/config/risk/broker/__main__` plus Phase 2 `market_data`, `strategy`, `backtest`, `alpaca_paper` (GET-only, non-executable order drafts) and `journal` (local SQLite offline drafts/events; NOT a provider order/fill ledger). Postgres target schema remains design-only at `db/migrations/0001_init.sql`.

## Multi-market interface requirements

Use an explicit `InstrumentId(venue, market, symbol, settlement_currency)` and instrument-specific metadata. Spot crypto has fractional base units and maker/taker fee assumptions; equities have sessions and different order validity; binary event contracts have payout/settlement and contract-specific worst-case loss. The risk module must convert proposed positions to validated worst-case USD risk via venue-specific adapters before portfolio aggregation. Do **not** pretend event contracts are fungible with crypto notional. Cross-venue cash cannot be double counted; maintain settled balance, pending balance and available balance per venue, then consolidate for reporting.

First end-to-end adapter: Alpaca **paper**, BTC/USD only. Architecture stubs for equities/Kalshi are contracts on paper, not active integrations. Verify regulatory eligibility and relevant provider rules separately before ever enabling live modes.

## Paper/live separation (non-negotiable)

Current runnable demo hard-fails any mode other than `paper`, any broker other than `local_dry_run`, and any enabled network order submission. The separately imported paper-account reader supports allowlisted GETs and has not been authenticated. A new `paper_executor.py` production transport supports only one literal POST path on `https://paper-api.alpaca.markets`, exclusively when invoked with separately supplied paper credentials and a matching Guardian-approved draft already durably marked `SUBMISSION_PENDING`. Default CLI never invokes it. Its mocks were tested, but actual broker submission/reconciliation remains unverified. It must never support an environment-variable toggle from paper to live. Live execution, if ever authorized, will require a *separately reviewed and separately deployed component*, credentials and operator action after validation.

## Order lifecycle and reconciliation

`SIGNAL_GENERATED -> RISK_REJECTED` OR `INTENT_APPROVED -> SUBMISSION_PENDING -> BROKER_ACCEPTED -> PARTIALLY_FILLED -> FILLED/CANCELED/REJECTED/EXPIRED`. `UNKNOWN_RESULT` after timeout requires lookup by unique client order ID **before any retry**. Never infer a fill from HTTP 200 or a candidate price. Reserve cash at approval, protect order-placement critical sections with durable locking, reconcile provider positions and fills after restarts, then release reservations on confirmed terminal status. Errors in reconciliation trigger halt of new buys and owner alert.

## Portfolio controls (initial illustrative discussion defaults)

- Logical simulated starting equity: $100.
- Maximum new buy: $15 (offline/demo proposal; live value requires separate owner approval).
- Maximum combined marked-to-market open longs + pending new buys: $30 (offline/demo proposal).
- Daily equity loss pause: $3, including unrealized movement on recognized portfolio equity.
- Peak-to-current equity drawdown pause: $10.
- No margin, leverage, shorts, automatic funding, withdrawals or transfers.
- Fresh market quote required (default maximum age 90 seconds).
- Emergency halt blocks ALL new orders; loss pauses block new buys but permit independently validated risk-reducing sells.
- Venue minimum notional/quantity, spread, fee and slippage checks remain to be implemented; provider documentation indicates a dynamic BTC/USD minimum equivalent to approximately $10. To avoid immediate sell-side dust exposure, the research draft uses a $15 purchase rather than $5; even that does not guarantee a future position remains above the venue minimum. The executor must reject such orders rather than automatically upscale them.

These are configurable *planning* defaults, not loss guarantees. Gaps, stale pricing, exchange failures and liquidation constraints may cause realized loss to exceed a threshold. Total initial allocation could be lost. The loss pauses are intended to prompt review, not to override the user's separately approved operating mandate.

## Autonomous intelligence policy

Baseline deterministic features and candidate strategies first, walk-forward evaluation second, optional LLM adviser only as an explainable overlay. The agent controller may return HOLD indefinitely. Research agents may propose strategy variants in shadow mode. Strategy promotion is a separate approved/versioned release step and cannot be performed by the live strategy itself. Training/backtesting must avoid look-ahead, survivor selection and post hoc strategy selection; report transaction costs and relevant baseline comparisons.

## Build-time technology choices

Python 3.11+/FastAPI backend; PostgreSQL for durable orders and audit; separate async market-data worker; Next.js/TypeScript dashboard later; low-cost hosted Linux deployment with healthchecks. Local Phase 1 uses Python standard library and unittest, no connected APIs. Docker compose and hosted infra are deferred until Phase 2/3 and need separate account authorization. Prefer pinned dependencies and `make test` CI checks over complex orchestration.

## Risks / unknowns

1. Account eligibility, free-tier market-data completeness and current BTC minimum quantity need broker validation.
2. Event-contract jurisdiction, provider terms and API access must be reassessed separately before that adapter is enabled.
3. A seven-day paper run checks operational behavior, not reliable strategy profitability.
4. A November 1 live pilot cannot be promised before integration, fault tests and a new explicit user approval.

## Phase 2-A checked engineering decisions

See `docs/API_PROVIDER_ASSUMPTIONS.md` for official provider links. Market-data pipeline requires validated UTC fully closed hourly BTC/USD bars and complete pagination; missing or incomplete bars cause HOLD/error, not guessed values. The 12/26 EMA candidate generates immutable evidence IDs; a research-only simulator fills on the next candle OPEN, includes conservative hypothetical trading costs and never reports brokerage fills. The local draft journal adds atomic idempotent proposal reservation and immutable audit, but a durable broker execution/fill state machine with PostgreSQL is required before POST orders. The proposed paper-only maximum buy is $15 and aggregate long/pending exposure is $30; any live risk mandate will require a new owner decision.

## Phase 2-B local continuation

`paper_order_state.py` implements a pure, tested state machine: draft approved -> pending submission -> accepted/partially filled -> terminal yet UNRECONCILED -> reconciled; ambiguous transport timeouts go to `UNKNOWN_RESULT` and never cause blind resubmission. All provider states must match the original client/broker IDs and nondecreasing cumulative fill quantity. This module neither POSTs nor persists actual provider orders yet, so a production broker ledger and reconciliation service remain mandatory. `offline_pipeline.py` connects strict, fresh, fully closed bars to immutable strategy evidence, Guardian screening, venue-sized draft generation and SQLite local journaling; results explicitly state `DRAFT_APPROVED_NOT_SUBMITTED`, HOLD, or REJECTED. Chronological research folds (`backtest.py`) use fixed, predeclared strategy parameters with previous bars as warmup and disjoint later evaluation windows; this is not optimization or genuine broker paper trading.

## Phase 2-C execution code, not activated

`paper_store.py` persists the pure lifecycle state machine to SQLite and atomically binds approved draft payloads to one unique client order ID before possible submission. It allows just one unresolved order at a time. A crash before/during POST leaves `SUBMISSION_PENDING`; errors/timeouts leave `UNKNOWN_RESULT`. Both block further submissions until provider lookup, and terminal states remain reserved until the separate auditor confirms provider cash, position and order reconciliation. `paper_executor.py` contains a *single-attempt* hardcoded paper-host POST transport; the default CLI never invokes it and tests inject fakes. Actual credentialed paper integration, provider fill/fee reconciliation, migration to production PostgreSQL and scheduler remain the next engineering gates. No live broker endpoint exists.

## Phase 2-D: provider evidence, virtual account and local operations (2026-09-28)

The single-attempt Alpaca PAPER executor now performs read-only preflight from an
identical-credential reader, checks current asset metadata (min_order_size,
min_trade_increment), cash-only buying power, single-symbol isolation and no
external open orders. A built durable draft must include an original
source-checked reference price and be no older than 90 seconds. The exact paper
POST is still opt-in code and NEVER called by the default CLI, dashboard,
operator tool, fake integration scenario or tests against a real provider.

Before the paper-only POST, `paper_store.py` atomically stores source cash/BTC
account baseline. A post-submission timeout becomes UNKNOWN_RESULT; repeated
POST is forbidden. Terminal status alone does not release reserved funds.
`paper_audit.py` validates a fresh, matching independent order lookup plus
source account and BTC position against the BEFORE snapshot. Audit tolerates
conservatively bounded maker/taker receive-currency fee effects; it halts on
unexpected accounts, identity mismatch, order mismatch, account transfers,
missing fill price, negative balances or unexplained external changes. Only
an audit with concrete source evidence may free the reservation. Caller-provided
`True` booleans no longer authorize reconciliation.

The paper broker might show a default $100,000. A separate virtual subledger,
initialized with exactly **$100**, tracks only reconciled changes in paper USD
cash and net received BTC. It checks account identity and frozen paper balances
before a subsequent order, independently of the caller's PortfolioSnapshot;
a buy with marked exposure plus order > $30 or marked equity <= $97 is
rejected. These are conservative prototype gates; daily reset and exact
peak-equity high-water tracking remain required before unrestricted worker use.
Submitted drafts cannot be voided to release pending reserves.

`operator_controls` is a persisted, auditable HALT flag. New submissions are
blocked while HALT is active; unknown orders prevent clearing HALT. Existing
provider orders are **not** canceled merely by setting local HALT and must
still be audited. `signal_vault.operator` is a local CLI; the local-only
`signal_vault.dashboard` only reads state, refuses public bind addresses and
provides no mutation endpoints. Cloud hosting still requires authenticated
owner sessions, HTTPS, authorization, health alerts and a separate deployment
review.

`signal_vault.fake_paper_scenario` exercises a deterministic fake paper
order -> accepted -> fake filled -> verified fake source snapshots ->
reconciled lifecycle without ANY network or real keys. It is not a broker
paper fill or proof of trading performance. Run `make smoke`.


## Phase 2-E follow-on: venue, research supervisor and AI boundary

`venue_rules.py` reads Alpaca source asset fields for current minimum BASE
quantity, BTC step and USD price step. It refuses an order below provider
minimum and calculates an **unsubmitted** proposed sell quantity and remaining
non-executable dust; source-deduced fee-reduced holdings may not equal a whole
step. The operating policy for dust remains unapproved, so the paper writer
still rejects an unstepped full-quantity sell instead of silently rounding.

`operations.py` records one research decision per immutable closed hourly BTC
bar; stale bar input outside a 90-second post-close window gives STALE_WINDOW,
and the durable operator halt/unresolved paper order prevent drafting. Old
strictly UNSENT drafts may expire with an immutable event; a draft with an
actual paper_order_states row is never voided by a TTL. `research_runner.py`
adds an independent unarmed single-worker scheduler with a local CSV mode or
owner-opted-in public read-only market-data GET. Even its continuous mode does
not import or instantiate any executor, so it cannot send orders.

`paper_onboarding.py` is a separate owner-invoked read-only paper eligibility
check, using separately supplied environment credentials and no order APIs.
It has not been run on real credentials. `agent_policy.py` defines a strict
non-tool-bearing AI output schema. The adviser may select an existing
reproducible BUY/SELL candidate or HOLD, but cannot invent an unrelated
trade, modify risk parameters or send network requests. AI-model integration
is not connected; the unarmed research supervisor currently uses the
deterministic baseline. No AI strategy performance has been established.

**Remaining before unattended real provider PAPER execution:** derive all
source-backed proposals from the isolated virtual subledger (not an arbitrary
external PortfolioSnapshot); mark-to-market peak/daily risk baselines and
venue minimum/fees, introduce sellable-quantity/dust owner policy, integrate
read-only paper onboarding and verify real source semantics, a durable order
scheduler/owner notifications and an authenticated cloud operator UI. All of
this remains separate from any live-money authorization.


### Durable source equity marks (Phase 2-E)

`paper_risk_marks` stores the virtual account's independently marked equity,
observed peak, UTC session opening equity, evidence ID and last source price.
The unarmed research supervisor records one mark for each fresh closed source
candle when provider virtual holdings exist. A new buy is denied after a $3
loss from the observed UTC-day open, a $10 drop from observed high-water, or
when risk marks become too stale. On UTC rollover, prior observed equity is
the next session's basis so overnight losses are not erased. Confirmed terminal
cash/BTC changes and the initial virtual mark are persisted atomically with
the order ledger. An above-$100 recorded portfolio snapshot is only allowed
by the local draft journal when it exactly matches independently reconciled,
durably marked budget values; a fabricated $100,000 paper account balance
cannot be treated as profit. `dashboard.py` labels this **virtual paper** data,
never actual or guaranteed P&L.
