# V10 paper campaign

V9 completed no trades in the reported overnight run. It remains a separate,
unchanged short-only experiment. V10 is an **unvalidated** bidirectional paper
candidate, not a profitable strategy certification.

## Activate on the Mac

In GitHub Desktop, fetch and pull `phase-162-multimarket-reset`. Start Docker
Desktop, then from `~/Desktop/Projects/signal-vault`:

```bash
bash trading_stack/start_v10_mac.sh
bash trading_stack/status_v10_mac.sh
```

The launcher builds, checks all six fresh public feeds, prints recent historical
**raw signal counts**, verifies V1 paper mode, pauses new V1 entries, backs up
SQLite ledgers, and verifies the V10 runtime plus dashboard. Historical signal
counts overlap and say nothing about profitability. They do not become trades.
If public-data checks fail, activation stops before changing V1.

Dashboard: http://127.0.0.1:8090. Refresh with Cmd+Shift+R. Default selects V10;
`/?engine=v9` shows V9 and `/?engine=v1` shows the original V1 trades. Each has
separate P&L. Click a trade for genuine candles, entry/exit markers, target,
stop, signal explanation and exit rules. Archived candles preserve older trades.

## Frozen rules

- Six assets: BTC, ETH, SOL, XRP, DOGE and ADA against USD.
- Closed 15m candles only. EMA20/60 and the slow EMA slope classify each asset.
  BTC does not veto another asset's signal.
- Trending assets need directional 1h momentum of at least 0.15%, price on the
  trend side of EMA20, bounded RSI and volume at least 60% of the prior median.
  Prior 16-bar breakout receives a separate tag; continuation can also qualify.
- Range reversals need a prior 1.5-sigma stretch, a confirmed turning candle,
  and at least 2.7% price room to the rolling mean. Flat markets can remain idle.
- ATR must be 0.07–2% of price. Trend target: max(2.7%, four ATR), at most 6%.
  Stop: max(0.8%, two ATR), capped at 2%. Range target uses room to the mean.
- Fresh quotes after candle processing, spread at most 0.20%, limited price
  drift, and target room above costs are required for every entry.
- First scan records a forward boundary. No retrospective fills. Subsequent
  entries use the next newly closed candle within four minutes of its close.
- Independent $100 starting ledger; $15 stakes; at most three positions and two
  in the same direction; 12 entries per UTC day; one-hour cooldown after exit.
- Eight-hour maximum hold; own-asset trend reversal can exit earlier.
- $2 UTC-day and $5 campaign equity-loss triggers; poll/gap losses can exceed
  those triggers. A daily halt resumes on the next UTC day with fresh marks.
- Campaign lasts seven calendar days from first activation. Restart preserves
  its deadline, balance, positions, cooldowns and consumed signal boundaries.
- Long buys at ask and sells at bid. Synthetic short sells at bid and covers at
  ask. Fees use Kraken's published Tier 1 **0.80% taker per side**, checked on
  October 3, 2026: [official schedule](https://support.kraken.com/articles/cross-platform-fee-tier-changes).
  Entry fee uses entry notional; exit fee uses actual simulated exit notional.
  Another 0.10% of entry stake per side is a slippage **assumption**, giving
  roughly 1.8% round-trip costs plus observed spread. Open marks include exit
  fees; closing realizes those costs once. Tier discounts, borrowing/funding
  and real short availability are excluded. It submits no broker orders.

The old 0.74% V9 assumption is retained in V9's historical record, but is not
reused for V10. Higher targets do not prove that they are reachable. After-cost
reward/risk is worse than gross reward/risk, and frequent small trades can
exhaust the loss allowance through costs alone. Forward results must show
positive expectancy before this candidate deserves any real capital.

## Shutdown and diagnostics

Mac shutdown stops the process. After restarting Docker, the container resumes
the same campaign. Missed candles are not traded retrospectively; overdue exits
use the first fresh executable quote, never an invented stop/target fill.
Keep the lid open, the Mac plugged in and Docker running for continuous operation.

To pause new entries while continuing to manage positions:

```bash
bash trading_stack/drain_v10_mac.sh
```

Do not delete the ledger to hide a loss or reset a deadline. Completed campaigns
require a deliberate separately versioned run, not an automatic reset.

State lives in the existing Docker volume under `paper-v10/`; V9 uses
`paper-final-v9/`. Ledger state and OPEN/CLOSE events commit atomically. A process
lock prevents two runtimes from owning one ledger. JSON is a dashboard projection.
Diagnostics distinguish strategy waits, entry limits, stale quotes, missed entry
windows and portfolio caps. Successful quote cycles are not strategy evaluations.

## Verification limits

Behavioral tests cover long/short accounting, stops, targets, expiry, restart,
costs, partial feeds, daily/session limits, candle causality, and dashboard view
selection. Generated test prices are **fixtures**, not performance evidence.
Fresh Kraken data and Docker execution must be verified by the Mac launcher;
the build workspace cannot reach Kraken or run Docker. Nothing in this release
establishes positive expectancy. More signals do not imply more profit.
Dashboard rendering logic is covered by a DOM regression harness. A visual
browser check was blocked because the preview browser could not open localhost;
the loaded layout has not received a browser visual pass in this workspace.
