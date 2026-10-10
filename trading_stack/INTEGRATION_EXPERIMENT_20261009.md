# Frozen experiment — 9 October 2026

This specification was written before running this comparison. No positive
return is presumed. Research does not activate trading or start a cloud account.

Continue the existing dashboard and one $500 logical portfolio. Crypto tests
six established USD pairs: BTC, ETH, SOL, XRP, DOGE and ADA. The smaller fixed
universe limits request load; it was chosen before observing new results.

Test three separate four-hour hypotheses together: 55-bar trend breakout,
EMA20 pullback reclaim in a rising EMA20/50/100 trend, and a lower-band recovery
in an OmniQuant ranging regime. Use 3 ATR or 3% initial stop distance, 4R trend
targets, prior-mean range targets, 2R trailing activation and 1.5R trailing
distance. Hold at most 14 days. All signals use complete closed native bars;
entries use the next bar, never the close that generated the signal.

Use 0.5% budgeted risk per trade, maximum four positions, 20% position allocation,
60% aggregate allocation, 2% daily and 10% account drawdown triggers. Gaps can
exceed these triggers. Keep one paper account for a runtime; historical scenarios
start separate $500 accounts and must never be combined into reported profit.

Report the complete fixed scenario set: Kraken 0.8% per-side taker plus 0.15%
half-spread and 0.1% slippage; the same with 0.2% slippage; and hypothetical 0.25%
taker costs on the same Kraken data. The last is cost sensitivity only, not an
Alpaca backtest. Reused Q1/Q2 history and a new bounded public 4h capture are both
retrospective. Previous exposure to the new interval elsewhere is unknown, so
neither is advertised as an untouched holdout. Keep all failures and results.

Correction before final evaluation: use precisely the trailing 120 closed 4h
bars for all indicators and gap validation. The first implementation incorrectly
validated the entire 720-bar input, so one February archive gap suppressed
signals for months after sufficient history had rewarmed. The initial report is
retained as `research/integrated-comparison-initial-window-bug-20261009.json` and
is not the final comparison. DOGE's Kraken XDG symbol alias was also corrected;
the configured universe was not changed. Thresholds and cost scenarios were not
tuned from the first report.

The current Kraken schedule was verified at
https://support.kraken.com/articles/cross-platform-fee-tier-changes ; Alpaca at
https://docs.alpaca.markets/us/docs/crypto-fees . Account-specific eligibility and
fees still require verification before any broker execution.

OmniQuant's small SimpleRegimeDetector is vendored under its MIT license from
Mfoniso-Jackson/OmniQuantAI commit 3ec6ea4177745386be61d6b63983b2bbf2d0bfd7.
Only its import path is adapted. It supplies a rule-based regime label, not
a probability or a proven source of profit. Its legacy strategy.py merely
returns the sign of the last price change; that is not used as a trading brain.

PredictArb's public scanner is adapted from the supplied PredictArb.zip and
integrated as research-only. It covers both buy-complete-set and split-then-sell
directions, bounded rotating market pages, timestamp alignment, depth and
per-level price-dependent fees. Unsupported protocols, fee curves and negative
risk markets are not assumed equivalent. Merges, eligibility, partial fills
and live auth are unverified, so this lane has no order or wallet transport,
no simulated settlement credits and no second $500 account. The latest API
references are https://docs.polymarket.com/trading/fees and
https://docs.polymarket.com/trading/positions/how-positions-work .

Jupiter/new-token checks remain connected to the existing discovery module;
quote entries require verified credentials and are off in this experiment.
Jev remains optional annotation with its paid-call switch off. No Claude,
social-data or other metered API is silently enabled. Stocks and Kalshi keep
their existing adapters, credentials and independent model-evidence checks.

Do not alter old campaign configurations or overwrite their databases.
No auto-promotion or live-money route is added. Hosting is subject to the
user's no-paid-testing requirement; prepare the concrete release before
asking for any unresolved hosting allowance or access.
