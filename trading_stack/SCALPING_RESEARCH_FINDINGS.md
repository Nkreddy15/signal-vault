# Scalping screen — fixed specification before replay

This screen responds to the request to test small profits and hundreds of trades per day. It uses the already-supplied 24-asset January–June 2026 archive, trading March–June after feature warm-up, from $100. The data contains observed 15-minute candles. This is not a one-minute or order-book scalping backtest.

The three fixed long-only rules are a four-bar breakout with EMA trend and volume confirmation; a 20-bar oversold rebound with RSI confirmation; and an EMA trend pullback. Each uses a 0.50% stop and target, no trailing, and a four-bar maximum hold. Signals use completed bars; execution starts on the next adjacent observed opening quote. The equal-opportunity blend shares one cash account and excludes the control rule.

The churn control enters every eligible observed bar and holds at most one bar. It exists to measure the effect of turnover, not to propose indiscriminate trading. Features require 64 consecutive observed bars and reset on gaps; no missing execution bar is invented. Risk is 1% per trade, full notional is reserved, shared slots and 80% allocation limits remain, and existing daily-loss/drawdown halts apply. There is no leverage or forced minimum number of trades.

The 60-scenario matrix contains five families (three rules, their blend, and churn control), three cost profiles, two execution assumptions and two operating-cost assumptions. Current Kraken taker tiers model declining fees only after actual rolling trading volume earns a tier. Alternative 0.10% per-side fees are hypothetical, while a zero-cost control removes fees, spread and slippage. The nonzero profiles include 15bps spread and 0.10% slippage per side. Operating cost is independently replayed at $0 and an illustrative $0.10/day.

The normal research engine rejects targets below its cost buffer. This screen explicitly disables that guard in its own configuration so small targets can actually be replayed and losses measured. The default stays enabled for all existing callers. No paper engine is changed, enabled or restarted.

At the published starting Kraken tier, 0.80% taker fees on each fill exceed a 0.50% gross target before spread and slippage. Maker fees are not substituted for taker fills: candles cannot establish maker execution, queue priority or fill probability. The current fee schedule is a present-cost sensitivity, not reconstructed historical January–June fees. Sources: [Kraken fee schedule](https://www.kraken.com/features/fee-schedule), [archive description](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data).

All scenarios, including failures and zero-cost controls, will be reported. Count entries per UTC day, calendar-day and active-day averages, turnover, trade fees, holding time, account halts, monthly outcomes and drawdown. Counts represent modeled entries, not orders submitted to a broker. High trade counts are not themselves evidence of positive expectancy. This reused development dataset cannot qualify a strategy for activation.

Run from the repository root on the existing Mac research installation:

```bash
bash trading_stack/research_scalping_mac.sh
bash trading_stack/research_scalping_mac.sh 500
```

The current research image can also run `scalping_edge_lab.py --bundle /path/to/signal-vault-research.zip --output-dir /path/to/scalping-output`. This requires no broker keys or network requests. Real one-minute scalping would additionally require observed minute/trade/quote data and a venue-specific execution model.

## Actual results: $100 versus $500

The same 60 frozen configurations were replayed independently with each starting balance: 120 observed-data scenarios. Existing equity-based slot limits scale from two at $100 to six at $500; fractional position sizing and earned volume fee tiers are recalculated in each account. Profits are not multiplied after the fact. Independent monthly accounts also use the selected starting balance.

Trigger-execution results without daily operating cost:

| Family and cost profile | $100 ending balance | $500 ending balance | $500 trades | $500 maximum entries/day |
|---|---:|---:|---:|---:|
| Breakout, Kraken fees | $74.51 | $373.77 | 154 | 53 |
| Reversion, Kraken fees | $74.16 | $373.40 | 161 | 40 |
| Pullback, Kraken fees | $74.89 | $374.84 | 153 | 53 |
| Blend, Kraken fees | $74.74 | $374.89 | 154 | 60 |
| Churn control, Kraken fees | $73.93 | $374.65 | 174 | 72 |
| Churn control, zero fees/spread/slippage | $108.39 | $577.57 | 70,200 | 576 |

All 80 scenarios with nonzero fee profiles lose money: 40 with current Kraken tiers and 40 with hypothetical 0.10% fees per side. At $500, native turnover reached the 0.38% taker tier, but that did not make the 0.50% target profitable. The churn control with hypothetical lower fees can exceed 100 entries/day, yet still loses. The ordinary breakout/reversion/pullback rules also have no positive trigger-execution result even with all costs removed. One breakout extrema/zero-cost sensitivity is positive; the execution disagreement is recorded rather than treated as validation.

The $500 zero-cost churn control's $577.57 headline assumes away the costs of 70,200 trades. It is not an execution candidate. The native-fee counterpart halts after losing about 25%. The account halt is retained rather than allowing forced turnover to continue draining capital. Zero-cost control plus $0.10/day ends at $565.07; this still excludes trading costs. The $100 zero-cost control plus the same daily operating allowance ends at $85.31. Costs change positions and trade paths, so the results are separate replays.

For comparison, the earlier failed-rebound short hypothesis was also replayed at $500 using its unchanged light illustrative borrowing rates, Kraken fees, 15bps spread and 0.10% slippage. Trigger ends at $542.54 (15 trades) before running costs, and $529.21 with $0.10/day. Extrema ends at $539.63/$526.36. The $100 trigger counterparts are $106.88/$93.43. More capital helps amortize a fixed running bill and alters opportunity/fee capacity; this remains a thin, reused-data short simulation with unmodeled actual collateral, borrow availability and liquidation rules. It does not establish a deployable profitable bot.

The evidence directory `research_results/20261003_scalping_replay/` contains all 120 scenario summaries, four full native-fee trade ledgers, four $500 failed-rebound comparison ledgers, original full-report hashes, source hashes and account reconciliation receipts. All 120 scalping accounts and four bear accounts reconcile ending cash to net trade P&L and operating costs; all activation flags are false. Four new scalping mechanics tests plus 21 existing core/financing checks passed. Docker execution on the Mac is not verified here; the observed-data Python replays were completed here without broker keys or orders.
