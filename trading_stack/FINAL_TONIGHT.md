# V9 overnight PAPER release

Run `bash trading_stack/start_final_tonight_mac.sh` after pulling the
`phase-162-multimarket-reset` branch. Review with
`bash trading_stack/status_final_mac.sh`; the existing dashboard stays at
http://127.0.0.1:8090.

This is a runtime upgrade around the frozen V8 72-hour bearish-breakdown
hypothesis, **not a claim that V8 passed validation**. V8's best development
candidate returned about 5.61% across six months and 26 trades but failed its
frozen gate. The unseen holdout remains untouched. New runtime limits also
change exits; that runtime has no validated backtest performance.

The final engine simulates short entries on BTC, ETH, SOL, XRP, DOGE and ADA
using public Kraken bid/ask data. These are synthetic positions, not exchange
or broker paper orders; Kraken spot does not become a short-selling venue.
Borrowing, funding, venue eligibility and liquidation are not modeled.

One $100 simulated ledger; $15 positions; at most three open and six entries
per eight-hour session. The existing hypothesis uses a 12% gross target, 4%
gross stop and 24-hour cooldown. A $3 total session loss trigger stops entries
and attempts to close all positions at the next observed ask. Polling, stale
data and gaps mean this is not a guaranteed maximum loss. Session end also
closes simulated positions at observed quotes; if data is unavailable, it
keeps retrying and reports degraded status. Cost model: 0.74% allowance on
entry notional per round trip plus the observed bid/ask spread, charged once
in realized P&L and included in open marks. No overnight profit or fill quota.

Operational fixes:

- SQLite transactions couple each fill with its ledger state; a process lock
  prevents two writers. Restart resumes the same deadline and ledger.
- Entries use synchronized, complete hourly candles, a ten-minute entry
  window and fresh bid/ask quotes. First boot never backfills a trade.
- Candle data is fetched once per new closed hour; quotes/stops refresh every
  30 seconds. Candle-fetch failure does not skip the earlier price-stop check.
- Dashboard shows V9 trades, clickable candles, targets/stops and reasons for
  no signal, with V1 results kept separately. Stale cycles are visibly marked.
- Cutover checks V1 is dry-run, pauses its entries, backs up its SQLite files,
  and restarts the same V1 strategy/database with a persistent entry veto.
  Existing V1 positions retain V1 exits. The new simulation uses a new ledger.
- Older V8 sidecars stop only after a successful final-runner health check.
  Stocks stay on their existing configuration and schedule.

`VERIFIED` is printed only after the new runner completes a fresh public-data
cycle and the dashboard can read it. Keep Docker running, AC connected and
the Mac lid open. Closing ChatGPT does not stop local Docker processes.

Re-running the starter resumes an unfinished session. It refuses to silently
reset a completed or halted session. Do not delete the ledger to improve the
score. Inspect the complete session before creating any new experiment.

Emergency stop: `docker compose --env-file trading_stack/.env -f
trading_stack/docker-compose.yml --profile final stop crypto_final`.
This preserves open simulated positions; restarting resumes their management.
The V1 entry veto remains in place until deliberately removed.

Validation performed in the coding environment is recorded in the release
message. The actual Docker build, V1 migration and Kraken availability are
checked on the Mac by the starter; this environment has no Docker or Mac control.
