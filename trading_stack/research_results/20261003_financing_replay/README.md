# Observed-data financing research

152 actual development replays on the supplied six-month Kraken archive: 128 weekly financing/eligibility sensitivities and 24 fixed bear hypotheses. Trading begins March 1 after feature warm-up. No broker orders or activation.

`financing-summary.json` and `bear-summary.json` contain every scenario configuration and aggregate outcome. The two failed-rebound ledgers contain all trades, financing assessments and independent-month account summaries for the best headline result and its operating-cost replay. Equity curves are omitted from those two checked-in ledgers; their full originals and all other full reports are reproducible below.

`accounting-checks.json` records a hash of each original full report, reconciles all 152 ending accounts against net trade P&L and operating cost, reconciles trading and financing fees, checks chronological entries, and confirms no pending positions or activation. It also records unchanged trigger/extrema legacy baselines. `source-sha256.json` identifies the exact research sources. Input candle hashes and universe selection are preserved in both summary indexes; verbose rejected-universe diagnostics are omitted from these indexes.

To regenerate the full reports with the original data attachment:

```bash
PYTHONPATH=trading_stack/crypto python trading_stack/crypto/financing_edge_lab.py --bundle /path/to/signal-vault-research.zip --output-dir /path/to/financing-replay
PYTHONPATH=trading_stack/crypto python trading_stack/crypto/bear_regime_lab.py --bundle /path/to/signal-vault-research.zip --output-dir /path/to/bear-replay
```

Dependencies are the research image's pandas/numpy environment. The ZIP loader preserves round-trip float precision. These commands never access broker credentials. See `trading_stack/FINANCING_RESEARCH_FINDINGS.md` for limitations and the separate stock-data export command.
