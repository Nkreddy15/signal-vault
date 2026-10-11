# Signal Vault native 15-minute revision

The user requested a shorter interval than the four-hour release. This revision
uses native Kraken 15-minute closed bars, including 120-bar historical warmup,
the same three entry families and pinned OmniQuant regime detector. The worker
refreshes cached history at the next closed candle instead of waiting for the
five-minute cache age. Entries still require their strategy and cost checks.

## Account and experiment history

Version: `SV-INTEGRATED-PAPER-15M-20261011`.
Configuration hash: `96456cacb3b6cd068a1f7d2c85802879bea45a177f71a58998db538208bcc2aa`.

The existing campaign is revised under its worker lock, with an exact prior-hash
permission, an automatic backup and an atomic `CONFIGURATION_REVISION` event.
The revision refuses open positions, pending orders, unhandled owner commands,
capital changes, altered fees, changed risk settings and changed deadlines.
Cash, prior losses, trades, fees, equity history, start and deadline are retained.
The prior configuration is retained in the revision record. Results across the
revision are not a single frozen-strategy experiment.

The dashboard reports the interval and revision count. Native 15m chart bars
and actual fill markers are supported. Higher-interval crypto charts aggregate
only complete, contiguous bars; no smaller candles are invented for other feeds.
Accepted dashboard CSS, template and main dashboard.js are unchanged.

## Validation

- 123 Python tests passed, including native 15m signal paths, unfinished/gapped
  candle refusal, boundary refresh, complete-hour aggregation, loss-preserving
  revision, mismatch/risk/position refusal and concurrent-worker lock refusal.
- Both dashboard DOM/API harnesses passed, including 15m selection and fill
  marker placement. Desktop/mobile visual browser QA remains unverified.
- Six native public 15m histories each contained 720 closed bars. A copied
  exported cloud account passed the revision without changing account identity,
  cash, fees, prior orders/trades, cycles, start or deadline.
- A short retrospective screen from October 5 16:00 UTC to October 11 22:00 UTC
  returned -2.3975%, $488.01 ending modeled equity and five closed modeled trades.
  This is overlapping retrospective research, not an untouched holdout or
  actual broker profit. Costs and risk were not changed or tuned from the result.
  Capture and summary: `research/native15m-20261011.json.gz` and
  `research/native15m-screen-20261011.json`.

## Release settings

Use the existing paper service, database subdirectory and persistent volume.
Stage the reviewed source together with:

```text
SV_CONFIG=trading_stack/cloud_paper/campaign.intraday.json
SV_CONFIG_REVISION_FROM=10b628dc1e24416eab5772c98d610a90f0ab3156a7854b4c675c912bb190da8f
SV_ALLOW_NEW_CAMPAIGN=0
```

Verify the live prior hash and flat account before committing. After success,
clear the one-time revision permission. Restart with the new frozen hash; a
restart must not add another revision or recreate the $500 account. Verify
HTTPS/authentication, fresh native 15m history, preserved identity/deadline,
revision event, backup integrity and normal worker heartbeat.

Crypto remains internal simulation. PredictArb and DEX remain read-only; stock
and Kalshi entries remain off. Paid AI and real-money routes remain off. The
existing Free-plan sleep setting still limits uninterrupted monitoring.
