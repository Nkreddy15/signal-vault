# Small-profit scalping screen

The requested behavior is repeated autonomous entries and quick exits for small **net** gains. The active worker already has a 0.3% net-of-cost profit exit, but its six watched pairs did not qualify under its rising long-trend entry rules at 10:45 AM Eastern. It remained RUNNING, with four closed trades, no open positions, $494.57 cash/equity, and -$5.43 cumulative paper P&L. The account was not reset or changed by this research.

This proposal tests faster entry hypotheses: native five-minute short-trend pullbacks, oversold rebounds with two rising closes, and range recoveries. It uses a fixed 20-pair universe, current risk bounds, stop protection, a one-hour holding cap, a ten-minute same-pair cooldown, and 0.3% net profit exits. It requires observed historical price headroom to clear fees, spread and slippage. That headroom and the take-profit level are rules, not expected returns or calibrated evidence of an edge.

## Captured data and fixed test

`scalp5m-capture-20261012.json.gz` contains 720 fully closed native five-minute Kraken bars for each of 20 pairs. The list was fixed before capture; no winning constituents were selected from historical results. Capture ends October 12 at 14:50 UTC. A full lagged 24 hours is reserved for liquidity filtering, leaving approximately 36 hours for screening. This short, overlapping sample is not an untouched holdout and cannot establish a durable edge.

Entries use the next bar's open, lagged liquidity, position/risk/exposure caps and adverse stop-first ordering when both stop and target appear in one bar. Exit costs are included in residual equity. Each scenario starts from an independent simulated $500. No executed cloud trade is inferred from these numbers.

| Scenario | Closed trades | Wins / losses | Ending equity | Net P&L | Modeled fees |
|---|---:|---:|---:|---:|---:|
| Current 0.8% fee per side | 8 | 0 / 8 | $491.75 | -$8.25 | $7.27 |
| Hypothetical 0.25% fee per side | 22 | 2 / 20 | $485.65 | -$14.35 | $7.30 |

The lower-fee comparison admits more cost-cleared signals, but their market losses outweigh the small winners. It reuses Kraken candles and liquidity and is **not Alpaca execution evidence**. Both chronological halves of the current-fee screen also lose money. No parameters were searched or tuned after these results.

These results do not support activating this candidate to produce profit. More completed trades multiplied negative average P&L in this sample. The new strategy source is isolated research: it is not dispatched by `strategies.py`, is not accepted by the current runtime config loader, has no API/order authority and does not change the active worker, fees, balance or dashboard.

## Fee and availability evidence

Kraken's current lowest-tier spot taker rate is 0.8% per side: https://www.kraken.com/features/fee-schedule and https://support.kraken.com/articles/cross-platform-fee-tier-changes . With the active 0.1% entry/exit slippage allowance, a 0.3% net profit requires a bid roughly 2.1% above the pre-entry ask before an additional spread. A $50 winning position nets $0.15 while paying approximately $0.81 in fees. Reducing the gross target without covering costs would report false profits.

Alpaca publishes a lowest-tier 0.25% crypto taker rate: https://docs.alpaca.markets/us/docs/crypto-fees . Its fees are denominated in the received asset/fiat and can be posted later as CFEE/FEE activities. Correct broker integration would need to reconcile those activities and verify actual account routing and availability. Public read-only Alpaca `us` quotes and native five-minute bars responded successfully during this investigation; no broker orders or accounts were created. A lower advertised rate by itself did not make the fixed strategy positive in the sensitivity test.

## Verification and reproduction

Six unit tests passed for exact net-of-cost arithmetic, rebound entry without the old long-trend condition, fee-headroom rejection, refusal of stale/gapped/partial/invalid candles, volume checks, repeatable signal IDs and preservation of inputs.

Run:

```sh
python -m unittest trading_stack.test_scalping -v
python -m trading_stack.research.screen_scalp_20261012
python -m trading_stack.research.screen_scalp_20261012 --cost-sensitivity
```

Complete results are in `scalp5m-screen-20261012.json` and `scalp5m-cost-sensitivity-20261012.json`. The active paper deployment remains pinned to `d3ed10dc30fa3eb2dfc26c4aa7db9c8e8ea7c5ed`; this research does not trigger a deployment. Forward profitability and a winning scalp execution model remain unresolved.
