# V11 cloud trial

Prepared October 3, 2026. **Not deployed or activated.**

The cloud supervisor runs the existing `paper_v11.py` and the existing owner
dashboard together in one replica. It reads public Kraken prices and submits
no broker orders. The frozen strategy, fees, virtual cost allowance, entry
schedule and 48-hour deadline are unchanged. Hosting does not create signals.

## Concrete Railway target

- Project: `signal-vault-forward-research`
- Existing unused service: `btcusd-hourly-get-research`
- Source: `Nkreddy15/signal-vault`, `phase-162-multimarket-reset`, pinned commit
- Root directory: repository root
- Config file: `/trading_stack/railway.v11.toml`
- One replica, maximum 0.5 GB memory / 0.5 vCPU, sleeping disabled
- **A separate persistent 500 MB volume mounted at `/data` is required**
- HTTPS Railway domain for the existing dashboard, protected by owner login
- Variables: `PAPER_V11_STATE_DIR=/data/paper-v11-500`,
  `V11_DASHBOARD_USER=nikhil`, random `V11_DASHBOARD_PASSWORD` (32+ characters),
  and `V11_ALLOW_NEW_ACCOUNT=1` only after explicit approval of a fresh account
- No Alpaca/exchange keys, local `.env`, or old account contents are copied

The existing hourly collector and its volume are separate resources. A new
cloud account starts at $500 and runs for 48 hours from its first runtime
start. **It does not continue or merge the Mac account.** The Mac ledger and
export remain its own evidence. Existing cloud ledgers always resume their
original balances and deadlines; a conflicting frozen specification fails.

Do not activate until the local V11 container has stopped. Before shut down,
run `bash trading_stack/stop_v11_500_mac.sh` and then
`bash trading_stack/export_v11_500_mac.sh`. The stop command ends the Mac
campaign; it is not a pause. Its export is saved in Downloads.

## Cost and activation boundary

The user's earlier restriction was no new paid resources or plan upgrade.
This setup needs a separate durable volume and continuous compute, so it is
prepared but not provisioned. Current Railway docs describe $1/month Free
credit; Hobby costs a minimum $5/month and includes $5 usage. Usage above the
included amount is extra. An exact 48-hour bill and remaining credit have not
been verified. The simulator's $0.10/day allowance is **not** a hosting quote
or a billing cap. Hardware limits do not impose a dollar spending limit.
The Free plan permits only one volume per project, which is already in use
here; Trial permits three. The account's current billing tier/remaining trial
credit must be checked rather than assuming a paid upgrade is necessary.

- https://docs.railway.com/pricing/plans
- https://docs.railway.com/volumes/reference
- https://docs.railway.com/pricing/cost-control

Approval must cover cloud deployment, any required plan change/storage charge,
and a fresh isolated $500 cloud paper trial. Before committing staged changes,
check that the environment has no unrelated pending work. Pin the exact tested
commit and set a user-approved provider spending limit before deployment.

## Operation and completion

No laptop is needed once cloud deployment, persistent storage, owner login,
fresh V11 cycle and the $500 dashboard selection are verified. The service
reuses the current daily-candle dashboard, including trade inspection.
`/healthz` reports HTTP liveness, not successful market-data collection;
verify `/api/paper-v11` independently before claiming the trial is running.

The supervisor stops if the worker or dashboard crashes; the provider can retry
up to three times without resetting a saved account. SIGTERM stops both
processes while preserving the ledger. After V11 ends and all synthetic
positions close, it writes `/data/paper-v11-500/cloud-results.zip`, prints
`CLOUD_TRIAL_ENDED` with final equity/counts, and exits successfully. The
dashboard then becomes unavailable; retained results and logs are still the
evidence. A failed public feed may keep pending exits running beyond 48 hours;
no closure price is fabricated. Provider usage can continue during that wait.

Local code/authentication/account checks are automated. This environment has
no Docker daemon, so the cloud image and actual Railway runtime remain to be
verified during deployment. No prospective cloud profit is claimed.

Validation: seven cloud-specific tests pass, including real dashboard selection
from an unchanged V11 ledger projection, plus the original 13 V11 runtime tests
and three launcher checks. Process tests use mocks; they do not verify a real
Docker image, provider bill, market profitability or cloud deployment.
