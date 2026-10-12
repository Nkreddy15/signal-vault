# Entry build: 12 October 2026

The new entry strategies remain research only. No candidate passed the declared development gate. The authenticated native-feed probe was deployed successfully on Railway. Its first request returned HTTP 400; switching to the documented all-market ticker query fixed it. The final check passed with six fresh pairs, 999 closed native candles and observed depth for approximately $49.43 of BTC at the current ask. This is a read-only estimate, not an exchange fill. The active account is still the same paper campaign, with $494.56770092135 equity, four closed trades, no open positions and net P&L of -$5.43229907865 at the deployment verification.

## Build

- One shared closed-bar feature extractor for both research and inference: 24 hours of contiguous native 5-minute candles, complete 15-minute confirmation, returns, finite-history EMAs, rolling RSI/ADX proxies, ATR, volume, VWAP, candle shape and native taker-buy volume. RSI/ADX here use rolling arithmetic, rather than Wilder smoothing.
- Confirmed trend-continuation, breakout-retest and VWAP-recovery proposals. A regularized logistic score can reject weak candidates. The exported classifier is a raw score, without a claim that its probabilities are calibrated.
- Passive pullback entry research with cash/exposure reserved for pending limits, ten-minute expiry, 30- or 60-minute maximum holding, stops and a +0.3% target **after** entry and exit costs. Market-entry research uses a 60-minute maximum holding.
- Native public quotes, asset minima, candle checks and depth-based sweep estimates. This client only allows whitelisted public GET endpoints. It has no API keys or authenticated order path.
- Authenticated `/api/research/venue-health` with one asynchronous worker and a five-minute cache. It never writes the execution ledger. Exact HTTP failure codes are exposed without response bodies or secrets.

## Protocol and evidence

Six USD pairs: BTC, ETH, SOL, XRP, DOGE and ADA. Thirty official monthly archive ZIPs for May–September were downloaded and verified against their published SHA-256 checksums. ZIP candles in September were not opened. Development used May–August; training ended before 16 August and calibration used 16–31 August. Each development series contained 35,316 candles and one gap; proposals require contiguous past candles. Held missing bars disqualify a candidate.

Initial crossing rules produced only 99 usable training examples. Before opening any reserved outcomes, development history was extended and ongoing trend-continuation proposals were added. This produced 1,266 development proposals, of which 767 fit the purged training interval; 100 reached the target under the label assumptions. The model's fitted standardization and coefficients match the pure-Python export to less than 1e-12.

Costs: published Binance.US Advanced Spot standard taker fee of 0.02% per side, 0.1% adverse exit slippage, 0.05% total modeled spread. Market entries also incur 0.1% entry slippage. Stress doubles slippage and spread. Passive entries execute hypothetically at their limit, still pay the 0.02% entry fee and require strict trade-through. The published zero maker fee was not assumed. Neither an account's eligibility/rate nor historical spreads and order-book liquidity have been verified.

Labels may inspect future candles for training. Portfolio decisions never use those labels. A training label crossing the time cutoff is purged. Stops win ambiguous same-bar stop/target cases. Passive entries cannot claim a target exit in their entry bar; stops are active immediately. No fabricated end-of-test liquidation creates a profit. Pending orders do not count as completed trades.

## Development results

These are isolated $500 portfolio simulations, not the active account or live returns.

| Market-entry variant | Calibration closes | Net return | Stress return | Qualified |
|---|---:|---:|---:|---|
| Rules baseline | 285 | -8.856% | -10.003% | No |
| Raw score threshold 0.55 | 7 | -0.458% | -0.552% | No |
| Raw score thresholds 0.65 / 0.75 / 0.85 | 7 each | -0.458% each | -0.552% each | No |

All raw score variants also require the score to exceed a cost/stop-aware break-even heuristic. This is not proof of expected profit. The seven-trade filter result was -$2.2905 net; its four target exits were outweighed by three stops.

Before evaluation, six patient-entry hypotheses were declared: 0.5, 1.0 or 1.5 ATR pullbacks, each with a 30- or 60-minute maximum holding. They use the same frozen development proposals. Stops start at the executable bid and are 0.75 ATR away, capped at 0.3% of the limit price. Per-trade risk, four-position maximum, 20% position cap, 60% exposure cap, 2% daily loss guard and 10% drawdown guard are retained.

| Pullback | Max hold | Calibration closes | Net return | Stress return | Qualified |
|---|---:|---:|---:|---:|---|
| 0.5 ATR | 30 minutes | 101 | -4.253% | -4.935% | No |
| 0.5 ATR | 60 minutes | 101 | -4.181% | -4.775% | No |
| 1.0 ATR | 30 minutes | 58 | -2.629% | -3.321% | No |
| 1.0 ATR | 60 minutes | 58 | -2.731% | -3.360% | No |
| 1.5 ATR | 30 minutes | 34 | -1.313% | -1.307% | No |
| 1.5 ATR | 60 minutes | 34 | -1.349% | -1.307% | No |

All patient variants also lost money in the earlier training period. Every frozen selection is `REJECTED_IN_DEVELOPMENT`. Consequently neither reserved-validation command was run. Reserved history may overlap earlier project research; it is not claimed to be independently untouched. Historical candle trade-through does not prove a real limit fill or queue priority.

`entry_study_20261012/entry_build_evidence_20261012.json.gz` preserves complete protocols, archive identities, the rejected model, all proposal labels, complete trade ledgers, equity curves and frozen selections. Its SHA-256 is `bcaadafadf2cfe85bf1f18ebb0818279332271c336587d15a487f7f35b5bbb49`. Archives are reproducible from pinned URLs/checksums; the restore command excludes reserved data by default. Raw archives are not included in the runtime image.

## Reproduce

From the repository root with Flask, NumPy and scikit-learn available:

```bash
python -m trading_stack.research.download_entry_archives
python -m trading_stack.research.entry_study prepare
python -m trading_stack.research.entry_study fit
python -m trading_stack.research.patient_study develop
python -m unittest trading_stack.test_entry_model -v
```

The source and protocol hashes gate reuse of cached events. Frozen validation also checks archive identities and patient cost settings before opening any reserved data. Model refitting stops if reserved validation has opened. `entry_study validate` and `patient_study validate` refuse to inspect reserved outcomes when development qualification fails. Full portfolio regression: 153 Python tests; cloud and final dashboard DOM harnesses passed. Browser visual inspection was not performed. Test results do not establish profitable trading.

## Sources

- [Binance.US fee schedule](https://www.binance.us/fees), standard Advanced Spot taker rate; no BNB discount assumed.
- [April 2026 fee announcement](https://blog.binance.us/zero-fee-trading/).
- [Official API documentation](https://docs.binance.us/).
- [Official historical data and checksum documentation](https://www.binance.us/institutions/market-history).

Promotion requires positive development and reserved historical results under both cost cases, enough closed trades, clean risk/data checks, verified live native data and explicit internal-paper execution metadata. The native feed gate now passes; the profitability gate still fails. No research result permits real-money trading.
