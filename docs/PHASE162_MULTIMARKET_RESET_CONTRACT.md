# Phase 162 — Signal Vault multi-market reset contract

Date: 2026-10-02

This is the product/engineering contract for the reset. It replaces the prior
narrow-strategy mindset. It does NOT authorize real-money trading.

## Product objective

Build one autonomous PAPER-first trading system that can evaluate and trade
multiple markets simultaneously, without depending on one narrow signal.

Initial market lanes:
- Crypto
- US equities / ETFs
- Kalshi demo event contracts

The system may later add more venues through adapters.

## Core rule

The system does NOT force a trade. It must continually search across many
instruments, timeframes, and strategy/model families so that "no trade" means
"no candidate currently clears the risk/edge threshold", not "one EMA crossover
did not happen".

Where the venue/account permits it, candidates may include:
- long
- short
- breakout
- trend-following
- momentum
- mean reversion
- volatility/regime
- market-making / spread capture
- statistical / relative-value
- ML probability models
- return regression
- reinforcement-learning policies
- event-market probability/value models

Shorting/leverage is venue-specific and must never be silently assumed.

## Open-source-first architecture

Do not rebuild commodity trading infrastructure when mature open-source
components already solve it.

Verified candidate projects inspected on 2026-10-02:

### NautilusTrader — production multi-asset core candidate
Repository: nautechsystems/nautilus_trader
License: LGPL-3.0
Role under evaluation:
- common event-driven multi-asset engine
- simultaneous instruments/strategies
- backtest/live code parity
- venue adapters
- portfolio/order/execution state

### Freqtrade / FreqAI — crypto research and model laboratory
Repository: freqtrade/freqtrade
License: GPL-3.0
Role:
- crypto historical testing
- hyperparameter search
- FreqAI adaptive ML experiments
- strategy comparison
- dry-run execution where useful

### Jesse — crypto strategy research specialist
Repository: jesse-ai/jesse
License: MIT
Role:
- multi-symbol / multi-timeframe crypto research
- long/short strategy experiments
- significance tests / Monte Carlo
- built-in ML pipeline
- fast candidate screening

### FinRL / FinRL-X ecosystem — ML/DRL model source
Repositories:
- AI4Finance-Foundation/FinRL
- AI4Finance-Foundation/FinRL-Trading
License observed for FinRL: MIT
Role:
- supervised/DRL candidate models
- portfolio allocation research
- model comparison
- production-oriented AI trading experiments

### Hummingbot — optional market-making specialist
Repository: hummingbot/hummingbot
License: Apache-2.0
Role:
- crypto market-making / spread-capture experiments
- exchange connector reference
- NOT the initial core unless evidence supports that use

Do not vendor or copy third-party code blindly. Respect each license. Prefer
clean adapters, subprocess/service boundaries, pinned versions, and reproducible
configs.

## Intelligence architecture

1. MARKET SCOUT
   Continuously enumerates candidate opportunities across all enabled markets.

2. FEATURE / REGIME LAYER
   Produces trend, momentum, volatility, volume, liquidity, correlation,
   cross-sectional, mean-reversion, breakout, and market-specific features.

3. MODEL / STRATEGY ENSEMBLE
   Multiple independent models score the same opportunity. No single model owns
   the portfolio.

4. OPPORTUNITY RANKER
   Converts model outputs into comparable expected-edge/confidence estimates,
   net of estimated fees/slippage.

5. PORTFOLIO ALLOCATOR
   Chooses among opportunities across markets under one shared risk budget.

6. GUARDIAN
   Deterministic limits. Models cannot raise their own permissions, leverage,
   risk budget, or live-trading authority.

7. EXECUTION ADAPTERS
   Crypto PAPER, Alpaca PAPER equities, Kalshi DEMO initially.

8. EVALUATOR
   Every strategy/model has attribution: trades, after-cost P&L, benchmark,
   win rate, expectancy, drawdown, turnover, fees, regime behavior, and
   out-of-sample/walk-forward performance.

## Acceptance criteria before any live-money discussion

A candidate must have:
- reproducible historical data
- explicit train/development vs validation/test separation where applicable
- no look-ahead
- modeled fees and slippage
- enough trades/observations to be meaningful for its timescale
- benchmark comparison
- positive after-cost expectancy in relevant out-of-sample testing
- tolerable drawdown
- successful PAPER execution/reconciliation
- no unresolved duplicate-order/accounting faults

A dashboard is NOT an acceptance criterion.

## Current evidence that must not be forgotten

- 90-day / 2160-hour crypto strength-tilt candidates failed the existing
  support gate under all three illustrative friction settings.
- Short US-equity sample: EMA 12x26 lost money; momentum matched the passive
  comparator exactly, so no momentum alpha was demonstrated.
- These negative/inconclusive results stay in the record.

## Working rule for this reset

The next meaningful milestone is a RESULTS MATRIX, not UI work.

For each market/model:
- period
- assets
- strategy/model
- train/validation/test or walk-forward design
- trades
- gross P&L
- fees/slippage
- net P&L
- benchmark
- win rate
- expectancy
- max drawdown
- Sharpe/Sortino where meaningful
- pass/fail reason

Only candidates supported by this evidence enter the serious PAPER portfolio.

## Authorization boundary

Engineering, public/open-source research, historical analysis, backtesting, and
PAPER/DEMO infrastructure may proceed.

This document does NOT convert general project authority into authorization to
place real-money trades, transfer funds, enable leverage, or connect a live
broker/exchange account.
