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

Present code: `src/signal_vault/{domain,config,risk,broker,__main__}.py` establishes domain contracts and an offline *non-filling* broker. Postgres target schema is design-only at `db/migrations/0001_init.sql`.

## Multi-market interface requirements

Use an explicit `InstrumentId(venue, market, symbol, settlement_currency)` and instrument-specific metadata. Spot crypto has fractional base units and maker/taker fee assumptions; equities have sessions and different order validity; binary event contracts have payout/settlement and contract-specific worst-case loss. The risk module must convert proposed positions to validated worst-case USD risk via venue-specific adapters before portfolio aggregation. Do **not** pretend event contracts are fungible with crypto notional. Cross-venue cash cannot be double counted; maintain settled balance, pending balance and available balance per venue, then consolidate for reporting.

First end-to-end adapter: Alpaca **paper**, BTC/USD only. Architecture stubs for equities/Kalshi are contracts on paper, not active integrations. Verify regulatory eligibility and relevant provider rules separately before ever enabling live modes.

## Paper/live separation (non-negotiable)

Phase 1 hard-fails any mode other than `paper`, any broker other than `local_dry_run`, and any enabled network order submission. A later Alpaca paper integration must instantiate `TradingClient(..., paper=True)`, verify its endpoint is `https://paper-api.alpaca.markets`, reject all unexpected domains, and use **paper-only credentials**. It must never support an environment-variable toggle from paper to live. Live execution, if ever authorized, will require a *separately reviewed and separately deployed component*, credentials and operator action after validation.

## Order lifecycle and reconciliation

`SIGNAL_GENERATED -> RISK_REJECTED` OR `INTENT_APPROVED -> SUBMISSION_PENDING -> BROKER_ACCEPTED -> PARTIALLY_FILLED -> FILLED/CANCELED/REJECTED/EXPIRED`. `UNKNOWN_RESULT` after timeout requires lookup by unique client order ID **before any retry**. Never infer a fill from HTTP 200 or a candidate price. Reserve cash at approval, protect order-placement critical sections with durable locking, reconcile provider positions and fills after restarts, then release reservations on confirmed terminal status. Errors in reconciliation trigger halt of new buys and owner alert.

## Portfolio controls (initial illustrative discussion defaults)

- Logical simulated starting equity: $100.
- Maximum new buy: $10.
- Maximum combined marked-to-market open longs + pending new buys: $20.
- Daily equity loss pause: $3, including unrealized movement on recognized portfolio equity.
- Peak-to-current equity drawdown pause: $10.
- No margin, leverage, shorts, automatic funding, withdrawals or transfers.
- Fresh market quote required (default maximum age 90 seconds).
- Emergency halt blocks ALL new orders; loss pauses block new buys but permit independently validated risk-reducing sells.
- Venue minimum notional/quantity, spread, fee and slippage checks remain to be implemented; proposed $5 trade sizes may be impossible when BTC lot/quantity rules imply a higher minimum. The executor must reject such orders rather than automatically upscale them.

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
