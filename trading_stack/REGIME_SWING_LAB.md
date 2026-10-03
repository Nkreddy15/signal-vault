# Daily leaders and channel swings

The 48-hour forecast approach produced no entries across the uploaded 48
scenarios. The diagnostic output confirms unsuccessful calibration: some
thresholds had no predictions or too few spaced outcomes; others failed
after-cost return/profit-factor requirements. This new release tests different
fixed hypotheses. It does not lower those forecast gates or claim an edge.

Pull `phase-162-multimarket-reset`, then run with Docker Desktop available:

```bash
bash trading_stack/research_regime_mac.sh
```

The command reuses the already prepared `edge-universe-v1` candles. It does
not download data, select assets by subsequent performance, fit models, restart
paper containers or remove paused-entry markers. It saves separate reports
and puts `regime-summary.txt` directly in Downloads, revealed in Finder for
upload using the chat attachment button. Detailed account, fill and daily
ranking receipts stay in the Docker volume under `regime-swing-v1`.

## Entry and exit rules

The same 24-asset formation selection is retained. Complete UTC days are
aggregated from all 96 observed 15m bars. Incomplete days are excluded, and
daily indicators restart after a missing day. All three families require at
least 29 complete consecutive days before entry. Testing starts March 1 for
comparison with the forecasting research.

| Family | Entry | Retention and exit |
|---|---|---|
| `leader_7d` | Top two positive 7d momentum/14d volatility scores, at least 3% 7d momentum, close above daily EMA21 | Hold while still in top four qualifying assets; exit at next observed opening quote after dropping out |
| `leader_28d` | Top two equally weighted 7d/28d momentum/volatility scores; 28d momentum at least 3%, 7d momentum positive, close above EMA21 | Same top-four retention buffer |
| `channel_7d` | Close above the previous seven daily highs and EMA21 | Hold until the daily close falls to/below EMA21, or a risk/time exit fires |
| `blend` | All three families share one account; scores compete for positions | Exit follows the family that opened that position; no independent $100 balances added together |

Long-only scenarios ignore bearish entry directions and can hold cash.
Synthetic long/short scenarios also rank negative momentum and use below-EMA
downside channel breaks, with symmetric retention rules. They are reported
separately. They do not establish executable spot shorting, borrowing,
margin/funding availability or broker authorization. Carry remains a sensitivity
assumption of 0.03% of short entry notional per day.

Daily decisions become entry/exit instructions for the following 15m opening
quote. Scheduled exits run before new entry capacity checks, including when
all position slots are occupied. A missing held-asset quote keeps the exit
pending until an observed quote arrives; no exit price is fabricated.
Instructions retain their closed-candle timestamp. Rank buffers avoid selling
a held leader solely because another asset temporarily moves one rank ahead.

Position stops are three daily ATRs, clipped to 6–20%. After price gains one
initial stop distance, trailing uses that same fixed daily-derived distance.
Updates apply to the following bar. There is **no fixed take-profit level**.
Maximum position holding time is 28 days. Stops, scheduled exits, daily losses,
drawdown halts and window-end accounting can still realize losses.

## Accounts and comparison matrix

There are 64 scenarios: four arrangements, two risk profiles, two side modes,
two fee profiles and two execution models. Spread is 15bps, slippage 0.10%
per side. Kraken scenarios use rolling-volume taker tiers; the lower Alpaca
rates are only a fee-rate sensitivity on Kraken data with simplified cash-fee
accounting. They do not establish Alpaca quotes or asset support.

Each scenario carries one $100 account through March–June. Calendar-month
accounts independently reset to $100 for comparison. Equity-based risk budgets
remain 1%/3%, allocation at most 80% at entry, per-family blend allocation at
most 50%, and capacity scales to at most six assets. Daily loss triggers remain
10%/20% and peak drawdown triggers 25%/50%. Gaps can exceed these triggers.

There is **no account-profit ceiling**. Reports measure milestones through
$10,000 without shutting the account down. More capital increases stake and
capacity; it does not generate qualifying signals where none exist.

The development screen requires three complete months, 20 trades, positive
continuous and median-month returns, at least 60% positive months, profit
factor at least 1.1, acceptable drawdown and no pending positions. A robust
Kraken long-only candidate must pass both trigger and extrema execution at
15bps. Synthetic-short or lower-fee results cannot qualify a Kraken spot bot.
No result auto-activates a paper engine.

Optional operating costs can be deducted, including time spent holding cash:

```bash
bash trading_stack/research_regime_mac.sh --daily-operating-cost-usd YOUR_ESTIMATE
```

## Evidence limits

Q1/Q2 are reused development data. Chronological rankings prevent future-price
selection at each decision; they do not undo repeated experimentation on the
same archive. Archive omissions can introduce survivorship bias. A passing
result still needs a frozen specification, untouched venue-native data and
prospective execution before any profitability conclusion.

The longer momentum hypotheses are motivated by
[time-series crypto momentum research](https://www.nber.org/papers/w24877)
and [cross-sectional crypto risk-factor research](https://www.nber.org/papers/w25882).
These rules are not a reproduction of either study, and neither study's
returns are claimed as this bot's results.

Mechanical verification uses generated fixtures for chronology, complete-day
aggregation, rank buffers, gap resets, both trade sides, exit-before-entry
capacity handling, pending exits, unlimited targets, daily trailing distances,
account reconciliation and the complete 64-scenario reporting pipeline.
Generated fixture returns are not market evidence. The build workspace has
no actual archives or Docker; the Mac command must verify the real replay.
