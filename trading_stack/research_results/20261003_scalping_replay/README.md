# Scalping and capital comparison evidence

120 actual observed-data scalping replays: 60 fixed configurations each at $100 and $500. Account window March–June 2026; January–February candle history supplies feature warm-up. Original 24-asset archive selection is retained. No strategy activation.

Both summaries report all scenarios, configurations, input hashes, feature specification, cost assumptions, frequency and monthly summary statistics. Four native-fee ledgers preserve all trade records, independent monthly account results and aggregate outcomes for blend and churn control at each capital size. Equity curves and verbose universe rejection diagnostics are omitted from the checked-in ledgers. Full originals can be reproduced with the source and supplied archive.

`accounting-checks.json` records hashes of all 120 original full reports and checked ending-equity residuals. Each trade's costs, chronological entry/exit, long-only side and blend's exclusion of the control were verified. No pending positions or activation flags were allowed. `bear-capital-comparison.json` separately preserves four $500 replays of the earlier selected failed-rebound hypothesis, original $100 comparators, full trades and independently reconciled financing totals; individual financing event rows are omitted there. These are reused development data, not validation.

`source-sha256.json` identifies exact scalping/accounting source. Reproduce using:

```bash
PYTHONPATH=trading_stack/crypto python trading_stack/crypto/scalping_edge_lab.py --bundle /path/to/signal-vault-research.zip --starting-balance 100 --output-dir /path/to/scalping-100
PYTHONPATH=trading_stack/crypto python trading_stack/crypto/scalping_edge_lab.py --bundle /path/to/signal-vault-research.zip --starting-balance 500 --output-dir /path/to/scalping-500
```

No downloads, keys or broker requests occur in these replay commands. The 15m screen cannot establish minute-level or order-book execution. See `trading_stack/SCALPING_RESEARCH_FINDINGS.md` for all results and limitations.
