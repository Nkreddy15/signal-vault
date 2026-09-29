# Signal Vault v0.3 — one preregistered 24-hour momentum gate

**Written before the owner's first v0.3 backtest. Status: OFFLINE HYPOTHESIS, NOT A PAPER-ORDER APPROVAL.**

## Development observations prompting this hypothesis

The owner verified the pre-gap development CSV SHA-256
`0f31fa3e6226a504db4b60185ae7388ae8979c14e3ccef1fc1b98e2b809071cc`
(1,843 continuous BTC/USD closed hourly bars from 2025-12-25 22:00 UTC until
2026-03-12 17:00 UTC exclusive). The owner ran a strictly past-only entry-context
audit of v0.1 and v0.2. All summaries reconciled.

| Median past-only pre-BUY metric | v0.1 subsequently winning (7) | v0.1 subsequently losing (26) | v0.2 subsequently winning (7) | v0.2 subsequently losing (24) |
|---|---:|---:|---:|---:|
| 24-hour close-to-close BTC return | +80.289 bps | +42.759 bps | +59.898 bps | +43.583 bps |
| 6-hour close-to-close BTC return | +110.101 bps | +72.382 bps | +159.300 bps | +94.266 bps |
| EMA spread (fast minus slow) relative to last close | +2.861 bps | +1.081 bps | +10.756 bps | +4.598 bps |

Trades **exiting under 24 hours** had median *pre-entry* 24-hour return of
+8.611 bps (v0.1, 21 trades) and +27.137 bps (v0.2, 20 trades), compared
with +80.974 and +62.329 bps respectively for positions exiting at or
after 24 hours. The outcome and holding-duration labels are known only
after the trade. These are correlated small-sample descriptive associations,
**not evidence of a market edge**. In particular, signed trend efficiency
did not consistently separate winning/losing cohorts in v0.2.

## Exactly one new candidate (fixed before v0.3 execution)

**v0.3 = unmodified v0.1 12/26 hourly EMA crossover, with one additional
entry-time BUY veto:** on the completed hourly bar that first confirms the
bullish crossover, compute

`24h_close_to_close_return_bps = 10000 * (last_closed_price / closed_price_24h_earlier - 1)`.

Accept a v0.1 BUY only when this prior-day return is **at least +50 bps
(+0.50%)**, evaluated using completed hourly bars only, before the next
execution candle begins. Otherwise emit HOLD; do not queue a delayed or
replacement BUY. The +50 bps cutoff was **chosen using observed exploratory
development summaries**, not independently discovered. There will be **one
fixed cutoff and one fixed comparison**, not a grid search or retuning after
results arrive.

Preserve v0.1's immediate bearish-cross SELL (no forced holding period),
EMA windows, $100 reset bankroll, $15 buy size, one-position constraint,
existing Guardian controls, next-open hypothetical fills, 0.25% assumed
taker fee and 0.10% assumed slippage per side, and the $10 modeled venue
minimum. No shorts, leverage, ML override, quote-lookahead, new permissions
or actual provider POST. v0.1 and v0.2 must remain byte-for-byte behaviorally
unchanged for their existing configs.

## Locked experiment and progression rule

Implement version `btc-hourly-ema-cross-24h-momentum-v0.3-RESEARCH-ONLY` with
`entry_minimum_prior_24h_return_bps=Decimal("50")` (and standard immediate
entry confirmation). The only allowed empirical run at this stage is
`PYTHONPATH=src python -m signal_vault.research_v03` on the exact pinned
*pre-gap* development CSV. Report baseline v0.1 and v0.3 with/without the
unchanged modeled costs, identical passive comparator, filled-side counts,
fees, drawdowns, end-of-window open mark, and fixed 168-hour disjoint fold
summary. Do not open the reserved post-gap historical file to debug or
optimize a negative development result.

Conservative advance-to-independent-evaluation gate (all must hold):
1. v0.3 after-cost aggregate P&L strictly positive on the development run.
2. v0.3 zero-cost aggregate P&L strictly positive (not merely fees avoided).
3. v0.3 after-cost P&L strictly greater than both v0.1 and the same-allocation
   passive BTC comparator.
4. v0.3 maximum after-cost drawdown no greater than v0.1's.
5. At least four v0.3 completed sell exits, and no rejected risk actions.

If any item fails: **do not promote**, stop v0.3 here and diagnose the broader
strategy design. Passing this exploratory gate is **not** a claim of future
profit or a statistical proof. A frozen passing candidate may subsequently
be evaluated exactly once on the uninspected post-gap dataset
`btcusd_older_postgap.csv` (2026-03-12 18:00Z through 2026-06-23 22:00Z
exclusive, SHA-256 `56ce999182c0537b99ef9b7eff71ab9e6842e211ece7fcdfdff6c7dca90ca076`),
subject to an explicitly reviewed evaluation command. An even stronger
prospective holdout would be data first arriving **after** the latest period
examined in September 2026. Never reuse an inspected period as supposedly
unseen. No result authorizes Alpaca paper-order POST, live trading, money
movement, hosting or spending.

## Recorded first and ONLY predeclared development run — owner-reported 2026-09-28

The owner executed `PYTHONPATH=src python -m signal_vault.research_v03` on GitHub head `12475bd7cb996c27e1a5890704543983c3fcac44`. The runner verified the exact pre-gap CSV SHA-256 `0f31fa3e6226a504db4b60185ae7388ae8979c14e3ccef1fc1b98e2b809071cc` and explicitly did not open post-gap observations.

| Metric | Original v0.1 | Preregistered v0.3 |
|---|---:|---:|
| After-cost full-development net P&L ($100 initial) | -$4.9128961148 | -$2.2277733837 |
| Zero-cost full-development net P&L | -$1.4141588344 | -$0.6614925183 |
| Estimated fees | $2.5035522826 | $1.1208263825 |
| Simulated fills | 67 | 30 (15 buy/sell pairs; closed) |
| After-cost max drawdown | $5.5819649357 | $3.4372539539 |
| Same-allocation passive BTC P&L (after cost) | -$3.0042961546 | -$3.0042961546 |
| Rejected actions | 0 | 0 |
| Open position at end | Yes | No |

168-hour development folds (eleven distinct evaluation windows, past-only warmup, each reset to $100):
- v0.1: aggregate net -$4.6752502811, median fold -$0.4296251528, 2 positive folds, 4 folds above passive comparator, 64 fills.
- v0.3: aggregate net -$2.0126983476, median fold -$0.2732507049, 4 positive folds, 6 folds above passive comparator, 28 fills.

**Exact predeclared gate outcome: FAILED.** The two failed criteria were:
1. `after-cost aggregate development P&L is not positive`
2. `zero-cost aggregate development P&L is not positive`

The new veto reduced modeled fills by 37 and estimated fees by approximately $1.38273; after-cost P&L improved by approximately $2.68512 versus v0.1. But gross/zero-cost research P&L remained negative and the eleven-fold aggregate was also negative. Because the original v0.1 and v0.3 endpoint position statuses differ, these aggregate comparisons must not be described as clean paired trade treatment effects. The +50 bps cutoff was chosen after looking at development summaries, so its development performance cannot establish predictive validity.

### Binding research disposition

**v0.3 is frozen as failed and NOT eligible for reserved-holdout review, provider-paper order submission or live trading.** Do not adjust the threshold, change risk limits to show positive returns, reuse development cohorts as independent testing, or open `btcusd_older_postgap.csv` to rescue it. v0.1 and v0.2 likewise remain not promoted.

Next engineering/research direction: pause serial EMA parameter/filter adjustments and independently review the $15-notional transaction economics and whether a materially different, lower-turnover trading design merits preregistration. A read-only prospective data/decision journal can be designed without paper-order POST or hosting/spend, but collecting observations is not itself evidence that these failed versions should trade. Preserve the four original owner-held CSVs, SHA manifests and known March 12 one-hour gap.
