# Phase 162 build checkpoint — multi-market reset

Updated: 2026-10-02

This checkpoint is the durable resume point for the Signal Vault reset. It
records only work/evidence that exists. Container health or dashboard state is
not counted as strategy evidence.

## Current product target

One PAPER-first system that can evaluate crypto, US equities/ETFs and Kalshi
event contracts simultaneously, using multiple independent strategy/model
families and one shared deterministic portfolio/risk allocator.

No single indicator or model owns the portfolio. A no-trade state is allowed
only when the broad opportunity set does not clear after-cost/risk thresholds.

## Completed Phase 162 architecture

- `docs/PHASE162_MULTIMARKET_RESET_CONTRACT.md`
- `research/upstream_engines.lock.json`
- `src/signal_vault/opportunity_engine.py`
  - normalized crypto / US-equity / event-contract opportunities
  - common after-cost edge ranking
  - confidence / maximum-loss comparison
  - shared $100 logical capital limits
  - total, market and correlation-group exposure caps
- `src/signal_vault/multimarket_cycle.py`
  - one simultaneous cross-market allocation cycle
  - deterministic idempotent intent IDs
  - explicit PAPER route verification
  - no live mode
- `src/signal_vault/event_value.py`
  - independently estimated event probability -> YES/NO expected-value opportunity
  - market price is not treated as its own forecast
- existing durable multi-market execution journal and PAPER/demo router remain
  available for later candidate execution
- `src/signal_vault/candidate_registry.py`
  - freezes evidence-bound model identity / features / horizon / threshold
  - cannot authorize PAPER orders

## Open-source-first research track

Pinned exact upstream commits are recorded for:
- NautilusTrader
- Freqtrade/FreqAI
- Jesse
- FinRL-Trading
- Hummingbot

Signal Vault reuses concepts/frameworks where they add value; it does not copy
third-party code blindly or ignore licenses.

## Crypto data evidence

Source:
- GitHub Actions run: 36927348918
- artifact ID: 11194955159
- artifact SHA256:
  `433a848b87cf269812ed08232ee1a7d5815fbffbd4fe19bd71c15bd3d83e7572`
- six assets:
  AVAX/USD, BTC/USD, ETH/USD, LINK/USD, LTC/USD, SOL/USD
- 2160 aligned hourly bars per asset (90 days)

## Crypto strategy-family tournament

Receipt:
`research/results/phase162_crypto_strategy_family_receipt.json`

Base-friction aggregate historical P&L on the shared $100 research book:

| Family | Aggregate P&L |
| --- | ---: |
| trend stack | +$10.97 |
| 24h momentum | +$9.26 |
| Donchian 20 | -$5.41 |
| Donchian 55 | -$0.14 |
| mean reversion | -$17.43 |
| passive equal-weight comparator | +$39.19 |

Trend and momentum were positive in 2/3 folds but each had a losing fold and
neither beat passive overall. No strategy was promoted.

## Crypto ML research

Broad multi-horizon receipt:
`research/results/phase162_multi_horizon_ml_receipt.json`

A 48-hour ExtraTrees candidate was positive on validation and descriptive
holdout under all three cost scenarios, but the original feature profile used a
168-hour feature while the current forward collector bootstraps only 72 hours.

That mismatch was not ignored. A separate deployable 72-hour-compatible screen
was created.

### Forward-compatible crypto candidates

Receipt:
`research/results/phase162_deployable_crypto_ml_receipt.json`

Primary candidate:
`crypto-rf-48h-return15bps-v1-phase162`

- Random Forest regression
- 48-hour horizon
- 1.5% predicted-return threshold
- maximum feature lookback: 72 hours
- validation base P&L: +$1.67
- validation trades: 26
- validation win rate: 57.69%
- validation max marked drawdown: $3.08
- descriptive holdout base P&L: +$8.48
- holdout trades: 27
- holdout base win rate: 59.26%
- holdout base max marked drawdown: $4.66
- descriptive holdout remained positive under low/base/high friction
- passive holdout base P&L: +$14.63

Secondary:
`crypto-extra-trees-48h-return125bps-v1-phase162`

- validation base P&L: +$1.28
- descriptive holdout base P&L: +$5.96
- descriptive holdout remained positive under all three cost scenarios

Important limitations:
- both deployable candidates were long-only in this historical period
- neither beat passive on absolute base-friction holdout P&L
- historical evidence is not prospective evidence
- neither candidate is authorized for PAPER orders

## US-equity lane

Existing verified short sample:
- AAPL, AMD, MSFT, NVDA, QQQ, SPY
- 60 regular-core hourly bars per asset
- explicitly too short to validate alpha
- old EMA baseline lost money
- old momentum result matched passive exactly

New code:
- `src/signal_vault/stock_ml_tournament.py`
  - 6/12/24 verified-core-bar horizons
  - Ridge, Random Forest, ExtraTrees, HistGradientBoosting
  - causal cross-sectional / trend / volatility / volume features
  - purged chronological train/validation/test
  - validation-only threshold choice
  - three equity friction scenarios
- `src/signal_vault/local_long_equity_research.py`
  - DATA-GET only local collector
  - parses local PAPER env as data; never sources shell
  - requires `ALPACA_IS_PAPER=true`
  - no account/order/POST route
- `scripts/phase162_collect_and_score_stocks.sh`
  - one command: collect long history -> SHA/calendar validation -> stock ML tournament

Real long-horizon stock model results are still pending because the GitHub
Actions runner currently fails before any workflow step starts and no prior
long-horizon stock artifact exists.

## Kalshi / event-contract lane

The repository already contains:
- resolved-market historical capture / validation
- chronological and expanding walk-forward research
- frozen historical candidate gate
- untouched confirmation gate
- prospective shadow infrastructure
- DEMO signing / executor / reconciliation
- DEMO execution acceptance
- final readiness composition

Phase 162 added `event_value.py`, allowing an independent probability model to
compete with crypto/stocks through the common opportunity engine.

No Phase 162 Kalshi probability model is claimed yet, and no stored evidence was
found proving an existing Kalshi candidate passed the full historical /
untouched / prospective chain.

## Execution layer status

Existing repository components already provide:
- durable cross-market execution drafts
- commit-before-POST journal semantics
- UNKNOWN_RESULT on uncertain transport
- restart recovery
- no blind resubmission
- provider-specific PAPER/demo router
- Alpaca PAPER crypto/equity route contracts
- Kalshi DEMO route contract

Phase 162's new common planner feeds normalized candidates toward this layer but
does not bypass provider preflight, reconciliation or market-specific risk.

## Local PAPER execution / operator stack hardening

The local open-source execution stack is now synchronized into Phase 162 rather
than living on a separate competing branch:

- Freqtrade crypto PAPER harness runs the six-pair 5-minute execution lane.
- Crypto protections now include:
  - 3-candle pair cooldown,
  - global stoploss-streak guard,
  - 5% equity-mode MaxDrawdown lock after enough closed-trade evidence.
- Lumibot Alpaca PAPER stock harness runs the 12-symbol 15-minute lane.
- Stock safety keeps the $100 logical budget / $90 investable cap and now limits
  new buy submissions to 16/day while still allowing risk-reducing sells.
- A unified read-only dashboard is wired into Docker Compose at
  `http://127.0.0.1:8090`.
  - reads Freqtrade health/profit/trades,
  - reads Alpaca PAPER account/positions/orders,
  - filters stock detail to the managed universe,
  - exposes no order-writing endpoint.
- FreqUI remains separately available at `http://127.0.0.1:8080`.
- The macOS installer and status helper now start/check the unified dashboard.

This operator layer is evidence plumbing only. It does not upgrade any research
candidate or imply positive expectancy.

## GitHub Actions issue

Current PR-triggered Actions runs are failing before any step records/logs are
created. Example Phase 162 run: 37058689354. GitHub returned an empty step list
and no usable job log. This is not being treated as a strategy/test failure.

Until that external runner path becomes diagnostic, useful research is run from
verified historical artifacts or through the local DATA-only pipeline.

## Next build sequence

1. Run long-horizon stock DATA-only collection and the new stock ML tournament.
2. Freeze any stock candidates that survive validation/holdout evidence.
3. Add new crypto RF/ExtraTrees candidates to the existing prospective
   six-crypto shadow lane and score them without orders.
4. Build / evaluate a genuine independent Kalshi probability model on the
   resolved-market corpus.
5. Feed surviving crypto + stock + event candidates into one opportunity cycle.
6. Run the shared portfolio in PAPER/DEMO with full strategy attribution,
   reconciliation and recovery evidence.
7. Use the existing unified PAPER operator UI to inspect attributed execution evidence while research gates continue.

## Authorization state

Historical research, open-source evaluation, code changes and PAPER/DEMO
engineering may continue.

This checkpoint does not authorize:
- live-money orders
- transfers/funding
- leverage
- live credentials
- automatic transition from PAPER/DEMO to live
