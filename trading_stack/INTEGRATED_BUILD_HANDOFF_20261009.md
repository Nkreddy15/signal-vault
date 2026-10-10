# Signal Vault integrated paper build

Continues `cloud-paper-multimarket-20261004` at
`a8acca9b6e65b3d1b5c1e741aee9caf8546c6502`. Review branch:
`signal-vault-integrated-20261009`. This is experimental research, not a
demonstrated profitable strategy or a running new cloud campaign.

## What changed

- The supplied OmniQuant regime detector is pinned with its MIT license. Three
  frozen native four-hour crypto hypotheses share one $500 virtual account:
  slow breakout, trend pullback and range reclaim. Complete bars, gap checks,
  realistic costs and durable trailing parameters are enforced.
- PredictArb's supplied scanner records depth-aware complete-set buy and
  split-then-sell hypotheses in both directions. Complementary token identity,
  supported fee curves and synchronized timestamps are checked. This lane is
  read-only; it allocates no capital and contains no wallet or order transport.
  Scanner configuration excludes the original second-account, automatic tuning
  and metered AI settings.
- Existing stock and Kalshi adapters remain available for research. Their
  entries are disabled in this experiment. Jupiter/new-token discovery remains
  available; DEX entries and paid Jev calls are disabled. Claude and social-data
  services are not connected or represented as working.
- The accepted template, CSS and main dashboard JavaScript are byte-for-byte
  unchanged. The existing cloud integration adds scanner evidence, regime
  health and native four-hour chart selection.

## Measured results

All predefined scenarios are included, each with a separate initial $500. The
two samples are retrospective. The first was previously inspected; the second
is a bounded public Kraken capture, not a certified untouched holdout.

| Cost scenario | Jan 21–Jul 1 net return | Jul 1–Oct 9 net return | New sample ending equity | New sample max drawdown |
| --- | ---: | ---: | ---: | ---: |
| Kraken 0.8% per-side taker | −4.84% | −1.98% | $490.11 | 4.93% |
| Same, adverse slippage | −4.97% | −2.82% | $485.90 | 5.00% |
| Hypothetical 0.25% per-side fee on Kraken data | −3.21% | +1.16% | $505.78 | 4.36% |

The newer sample has 37 closed trades per scenario. The lower-fee row is cost
sensitivity, **not an Alpaca backtest or broker-confirmed result**. It also
loses on the older sample. Trading returns exclude hosting, taxes and costs
outside the specified assumptions. No family was discarded after seeing its
results, and no strategy was automatically promoted.

The final report is `research/integrated-comparison-20261009.json`. It includes
trade records, equity, attribution, hashes and limitations. An initial
history-window bug report is retained separately and explicitly invalidated.
The 120-bar correction and DOGE alias correction are documented in
`INTEGRATION_EXPERIMENT_20261009.md`; thresholds were not tuned from that run.

Reproduce with the original archive and saved public capture:

```sh
gzip -dc trading_stack/research/kraken-4h-20261009.json.gz > /tmp/sv-kraken-4h.json
python -m trading_stack.cloud_paper.research_integrated \
  --archive /path/to/signal-vault-research.zip \
  --capture /tmp/sv-kraken-4h.json --output /tmp/sv-integrated-comparison.json
```

## Verification

115 Python tests passed, and both dashboard DOM/API harnesses passed. The cloud
harness now also checks OmniQuant/PredictArb status, escaped scanner details and
automatic native four-hour chart selection. These are fixtures, not trades.

The actual local supervisor, worker and Gunicorn processes passed a two-cycle
restart smoke using public Kraken data and an isolated temporary database:
HTTP 401 without authentication, health HTTP 200, unchanged campaign identity,
configuration/start/deadline across restart, $500 cash, no orders, SQLite
integrity `ok` and 4,320 stored native candles. Entries were explicitly disabled
for this smoke. Evidence: `research/integrated-runtime-smoke-20261010.json`.

```sh
python -m unittest trading_stack.test_cloud_paper trading_stack.test_regime_v2 \
  trading_stack.test_discovery trading_stack.test_integrated trading_stack.test_v11 \
  trading_stack.test_v11_launcher trading_stack.test_v11_cloud -q
node trading_stack/test_final_dashboard.cjs
PYTHON=python node trading_stack/test_cloud_dashboard.cjs
python -m trading_stack.verify_integrated_runtime
```

Browser screenshot/interaction QA remains unverified: the Chromium download
returned a 195-byte HTML response rather than a browser archive. The DOM harness
passes, but no desktop/mobile screenshot pass is claimed. Docker is unavailable
locally, so the image itself has not been built here. The isolated browser
fixture accepts `--config trading_stack/cloud_paper/campaign.integrated.json`;
its synthetic trades must never be counted as campaign performance.

## Cloud release

Railway project `signal-vault-forward-research`, production environment
`628e903d-c28f-42c1-bf59-9f7d91574dd0`. The existing hourly research collector
continues on its own service and volume. It is not the new paper worker.

The previously empty `btcusd-hourly-get-research` service
(`469a640b-03af-4d3e-be47-441cacff16dd`) is the release target. Prepare its source
at the review commit, the explicit Dockerfile/start/healthcheck service settings,
one replica in us-west2, a separate 500 MB volume at `/data`, and these settings:

```text
SIGNAL_VAULT_MODE=paper
RAILWAY_DOCKERFILE_PATH=trading_stack/Dockerfile.cloud-paper
SV_CONFIG=trading_stack/cloud_paper/campaign.integrated.json
SV_STATE_DIR=/data/cloud-paper-integrated-20261009
SV_ALLOW_NEW_CAMPAIGN=1
SV_DASHBOARD_USER=nikhil
SV_ALLOW_AI_CALLS=0
```

A unique random dashboard password was staged directly in Railway. View or
replace it there; no secret belongs in Git or this document. Do not set
`SV_LOCAL_TEST` in production. The seven-day
campaign starts only when the durable database is first initialized. Remove
`SV_ALLOW_NEW_CAMPAIGN` after verified initialization. Preserve the database and
frozen configuration when restarting; do not reset the account to conceal losses.

Railway rejected the legacy Config as Code path as deprecated, so this release
uses direct service settings and `RAILWAY_DOCKERFILE_PATH`. The old `.toml` is
retained for the prior checkpoint and is not selected on the new service.
Railway also rejected `sleepApplication=false`: its response requires sleep
mode on Free-plan services without a cron schedule. The reviewed preparation
therefore retains `sleepApplication=true`. Sleeping is incompatible with
guaranteed continuous protective monitoring; no keepalive workaround was added.
The preparation needs a permitted continuous-hosting arrangement before it can
fulfil the unattended trading goal.

The release must remain staged until the user's no-paid-testing requirement can
be honored. Available credit and a hard spending protection have not been
verified; staging does not start a worker. No private dashboard URL or new
cloud campaign start is claimed. Before activation, inspect **all** staged
environment changes and verify that the collector is unaffected. After
activation, verify terminal deployment success, HTTPS/authentication, fresh
provider data, durable-volume restart and database/backup integrity. Source
publication and staging are not proof of those deployment checks.

## Remaining evidence

- Current Kraken costs do not demonstrate an edge. A cheaper venue needs its
  own historical feed, executable costs and eligibility checks; the sensitivity
  row cannot substitute for them. Reserve genuinely future observations before
  promoting a strategy.
- A direct public Polymarket probe returned HTTP 403 in this environment. The
  scanner must expose unavailable/error coverage; no working execution or
  collateral conversion is claimed. The two-cycle smoke only observed the
  initial scan state.
- Alpaca paper and Kalshi demo credentials are absent locally. No real broker
  fill/partial/cancel/settlement verification has been performed. Kalshi also
  requires independent calibrated probability evidence before any entry.
- Paid AI/news/social APIs stay off. No API key, wallet credential or live-money
  route is introduced by this release.
