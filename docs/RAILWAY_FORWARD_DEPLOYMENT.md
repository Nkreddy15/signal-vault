# Railway-specific activation: BLOCKED until owner selects a permitted plan

**2026-09-29 deployment attempt:** Railway connected successfully to this
ChatGPT session, but `create_project` returned the account-level error
`Your trial has expired. Please select a plan to continue using Railway.`
No project, service, paid plan, volume, network worker or remote credentials
were created by that failed attempt. Do not present code-only preparation as
a hosted service. The old Mac LaunchAgent and the separately reconciled
one-time $15 Alpaca PAPER BUY remain untouched.

**Owner action:** Review Railway billing in your own account. If Railway
offers an acceptable Free plan, select that yourself; otherwise choose a paid
plan only after explicitly deciding its price, resource usage exposure, and
hard limit. This repository cannot and must not change billing or select a
paid subscription on your behalf.

## Railway architecture (different from the generic Docker Compose example)

Use Railway's **native UTC cron job** `7 * * * *` rather than a long-lived
`--serve` daemon. Each cron worker starts around UTC minute :07,
records no more than ONE fresh, consecutive fully closed hourly BTC/USD bar,
computes SHA-bound offline EMA v0.1/v0.2/v0.3 research-only signals, then exits.
This avoids idle compute between hourly runs. Railway warns cron may start
a few minutes late; the existing collector permits current-hour minute
03–24 and otherwise skips. Gaps are never silently backfilled. Railway also
skips a scheduled tick if the previous execution has not terminated.

Use the root `Dockerfile` and entrypoint
`python -m signal_vault.railway_forward_cron --once`.
The code refuses service startup unless:
- Railway automatically supplies
  `RAILWAY_VOLUME_MOUNT_PATH=/var/lib/signal-vault/forward` via an actual
  **attached persistent volume** mounted there; no fallback to an ephemeral
  image directory or Mac records is permitted.
- Volume root is a real nonsymlink 0700 private directory, writable by the
  worker. Railway documents that attached volumes are root-owned, so this
  Railway-specific image should use `RAILWAY_RUN_UID=0` in service variables.
  The adapter restricts permissions of ONLY the dedicated volume mount root
  at each cron run, without deleting/mutating old captures. This root runtime
  is a platform permission tradeoff: never mount the host root, Docker socket,
  other projects or broker execution files.
- Two separate PRIVATE or sealed Railway **service variables** (not ChatGPT,
  GitHub, image layers or CLI arguments) exist:
  `SIGNAL_VAULT_FORWARD_DATA_KEY_ID` and
  `SIGNAL_VAULT_FORWARD_DATA_SECRET`.
  Enter actual values yourself in Railway Variables; they must be a separate
  Alpaca PAPER-only credential pair usable for historical DATA GET. They are
  read *just in time*, after the inherited hourly/archive preflight; this
  adapter never prints their values. No generic/LIVE credential fallback.
  Provider PAPER API keys can have broader permissions than this GET-only
  worker. Separate the key and protect the Railway workspace accordingly.
- NO `ALPACA_API_KEY_ID`, `ALPACA_LIVE_KEY_ID`, generic APCA variables,
  `ALPACA_PAPER_KEY_ID`, `ALPACA_PAPER_SECRET_KEY`, or
  `SIGNAL_VAULT_ENABLE_PAPER_ORDERS` can be configured in this worker.

### Planned Railway project settings

| Item | Value |
|---|---|
| Project | `signal-vault-forward-research` (PRIVATE; new, do not reuse unrelated projects) |
| Source | private `Nkreddy15/signal-vault`, branch `main` |
| Service | `btcusd-hourly-get-research` |
| Build | repository-root Dockerfile; read-only Python source |
| Start command | `python -m signal_vault.railway_forward_cron --once` |
| Cron | `7 * * * *`, UTC |
| Restart | NEVER; avoid duplicate failed-capture retries |
| Replicas | 1 |
| Public domain | NONE |
| Volume | private persistent mount `/var/lib/signal-vault/forward` |
| Runtime variable | `RAILWAY_RUN_UID=0` for root-owned Railway volume |
| DATA variables | exact two names above, entered privately in Railway UI |
| Risky order API / PAPER auto-orders / LIVE | Unavailable in this entrypoint |

**Security and cost guard:** enable an appropriate Railway workspace Compute
hard usage limit before sustained operation. Railway's documented minimum
custom Compute hard limit is $10, not a promise that the service costs $10,
and reaching it can shut down the workload and interrupt consecutive
research. Do not purchase a plan or approve an expense without operator
authorization. Check actual usage and billing directly in Railway.

### Owner-side no-network preflight

After the project's volume and private variables are installed, run within
the service context only:

```sh
python -m signal_vault.railway_forward_cron --preflight
```

Expected `RAILWAY_LOCAL_PREFLIGHT_PASS_NO_NETWORK`.
`--status` independently reads only offline provider-capture evidence.
A fresh cloud volume always starts with a distinct historical bootstrap and
**zero** prospectively observed bars; it must not adopt or merge the old Mac
segment. After a first consecutive later hourly tick, accept only
`ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED` and a newly recorded,
immutable SHA-bound shadow receipt as proof of real cloud collection.
No broker account query, BUY, SELL, POST, funding, website or live trading
is permitted.

No persistent-volume backup/restore procedure has been remotely verified;
record private encrypted backups before relying on a full-week sample.
Keep the old Mac collector unchanged until a cloud bootstrap PLUS at least
one next-hour genuinely prospective record have been verified. It is fine to
turn off the Mac if you accept that the local segment then breaks; a fresh
cloud segment is separate and must not fabricate a missing hour.

Railway documentation reference:
[Volumes](https://docs.railway.com/volumes),
[Cron jobs](https://docs.railway.com/cron-jobs),
[Cost control](https://docs.railway.com/pricing/cost-control).
