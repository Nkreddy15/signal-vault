# User-authorized, unattended BTC/USD READ-ONLY forward capture (macOS)

**Build status:** The GET-only short-lived hourly worker and explicit macOS
user LaunchAgent setup are implemented and tested using fake providers and
isolated temporary files. Nothing was installed or activated on the owner's
Mac by GitHub updates or this conversation. The owner must explicitly run
the one-time setup below after pulling the source.

This replaces the need to type a manual capture command EVERY hour. It does
NOT trade, open positions, submit Alpaca paper POST, read a live account,
fund anything, run strategy signals, upload evidence, spend money or connect
to a cloud/hosted service. The owner may stop the per-user job at any time.

## Behavior

- A short-lived job runs at **local minute :07 of each hour**, which is also
  UTC minute :07 for hour-aligned US Eastern offsets. This is not a constantly
  running daemon. Each tick checks real current UTC time. Allowed start is
  UTC minute :03 through :24; delayed wakeups in minute :25 through :59
  are explicitly SKIPPED without requesting credentials or historical data.
- The **first** eligible auto tick uses a fresh, nonoverwriting 72-closed-hour
  Alpaca BTC/USD historical DATA **GET only** (existing fixed HTTPS data
  endpoint; redirects refused), and creates a separately named private
  `data/forward/observations-auto-YYYYMMDDTHHMMZ.sqlite3` bootstrap with
  **ZERO** retroactively claimed forward observations. The previously
  owner-verified `data/forward/observations.sqlite3` and its 3-record
  archived snapshot are never reset or appended to by this new automation.
- Each *following consecutive* eligible hourly tick independently audits
  the auto journal and every previous captured CSV/manifest **before**
  requesting local Keychain credentials or network data. It captures a NEW
  immutable rolling CSV pair, validates prior overlap and capture freshness,
  appends precisely ONE genuinely new fully closed UTC candle atomically,
  and recomputes the full local audit before advancing the private operational
  segment pointer. All successfully observed new candles remain exploratory
  development evidence and are NEVER buy/sell recommendations.
- If the Mac slept, was turned off, logged out, lost network/Keychain access,
  encountered a stale/corrupt provider response, or otherwise missed an hour,
  the collector **NEVER backfills**. An operator-safe refusal/incident receipt
  is preserved. If the earlier segment's original evidence remains intact and
  the next scheduled tick is in the eligible minute window, the code
  automatically starts a DIFFERENT explicitly named new future bootstrap
  with zero forward records, recording its previous segment and first missed
  expected close in a sanitized receipt. It does not merge segments, claim
  continuity, overwrite a capture, edit history, or silently reset the
  original or older auto journal. A corrupted older segment HALTS without
  constructing a new one to conceal the source problem.
- If a capture or raw source manifest already occupies the current hour
  (including a manual capture or orphan from a previous failed attempt),
  it refuses to overwrite or reuse that file. Next hour can start a
  new separate prospective segment if necessary.
- Full archive audit, unique local JSON receipts, owner-only segment pointer
  and process locks are kept in Git-ignored `data/forward/automation/`
  (0700 parent, 0600 files). No Keychain values are put in logs/receipts
  or the LaunchAgent plist. A single tick may use more than one network
  transport request if the DATA endpoint requires pagination/retries;
  its **only** allowed remote operation is the existing BTC/USD historical
  DATA GET. No generic/live broker credential fallback exists.

## ONE-TIME owner activation on your Mac

Only after **Fetch/Pull origin** in GitHub Desktop, from the existing
`signal-vault` repo directory with **`.venv` activated**:

First preview the planned user schedule; it writes nothing:

```sh
PYTHONPATH=src python -m signal_vault.mac_forward_agent --preview
```

Next add the TWO *existing Alpaca PAPER data* credential fields to your
**macOS login Keychain**, interactively. These commands must be run
locally in Terminal, NOT copied with actual secrets into GitHub/chat.
**Keep `-w` as the FINAL flag with NO password argument:** macOS security
will prompt for the value without putting it in the shell command line.
`-U` updates a preexisting matching entry rather than creating a duplicate.

```sh
# At the first interactive prompt, enter the PAPER data KEY ID:
security add-generic-password -U -a signal-vault-forward -s com.signalvault.forward.alpaca-paper-data-key-id -w

# At the second interactive prompt, enter the PAPER data SECRET:
security add-generic-password -U -a signal-vault-forward -s com.signalvault.forward.alpaca-paper-data-secret -w
```

The installer checks accessibility of these separate generic-password items
without printing either value or sending any provider request. Never pass
`-A` (unrestricted Keychain access), never place passwords in shell
variables, CLI flags or `.plist` contents.

Finally **explicitly install and activate** one local user LaunchAgent:

```sh
PYTHONPATH=src python -m signal_vault.mac_forward_agent --install

# Expected: plist_exists=true and launch_agent_loaded=true
PYTHONPATH=src python -m signal_vault.mac_forward_agent --status
```

The owner-only plist at
`~/Library/LaunchAgents/com.signalvault.forwardobserver.plist`
contains only the absolute local project venv Python path, the GET-only
module and `--once` argument, the absolute working directory/PYTHONPATH,
private log paths, `Umask=077`, `RunAtLoad=false`, `KeepAlive=false`,
and a `StartCalendarInterval` of local minute 7. A unique existing plist
is **never overwritten**, and a failed `launchctl bootstrap` is reported
as NOT activated rather than treated as success. It installs no privileged
system-wide daemon and neither admin/root access nor a cloud server is
required for a logged-in local user.

**Important for unattended reliability:** Leave the Mac ON, logged into the
correct user account, and awake/connected at minute :07. macOS launchd
coalesces wake-up invocations after sleep; a late invocation is skipped rather
than recording an earlier closed candle as freshly forward observed. An
unlocked/authorized login Keychain may be required for retrieval. If first
use prompts for Keychain permission, review the app/service and grant only
the intended local `security` access. If access fails unattended, the
runner records a nonsecret HALT receipt, and no provider request occurs.
Moving/renaming your local source checkout or deleting its `.venv`
invalidates the absolute paths in the plist; safely stop/reinstall the
agent rather than secretly rewriting the job.

## Daily 15-second health check, not hourly attendance

The LaunchAgent does not start instantly after installation because
`RunAtLoad=false`; first eligible tick is the next local minute :07.
That first tick is expected to report
`FIRST_AUTO_SEGMENT_BOOTSTRAPPED` and ZERO prospective new observations.
One hour later, if the Mac remains awake and authorized, a successful tick
reports `ONE_NEW_PROSPECTIVE_CANDLE_RECORDED` and count 1.

At any time inspect verified archived auto-segment status **offline**:

```sh
PYTHONPATH=src python -m signal_vault.unattended_forward_cycle --status

# Optional: list receipt filenames (do not paste raw source CSV or Keychain):
ls -lt data/forward/automation/receipts | head

# Optional: inspect only sanitized scheduler JSON or generic Python failure logs:
tail -n 50 data/forward/automation/launch-agent.out.log
tail -n 20 data/forward/automation/launch-agent.err.log
```

`--status` also reports the latest sanitized tick decision/failure class,
but does NOT itself collect, authenticate, place orders or set a scheduler.
A `HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE` decision means do not rename/delete
raw evidence or retroactively observe. Ask for help using ONLY the
nonsecret status/receipt JSON, never Alpaca keys or private archived data.
No paid email/SMS, hosted monitoring, public endpoints or remote access is
installed by this phase.

## Stop it at any time

```sh
PYTHONPATH=src python -m signal_vault.mac_forward_agent --uninstall
PYTHONPATH=src python -m signal_vault.mac_forward_agent --status
```

The explicit stop removes only this verified user LaunchAgent plist and
stops its launchd job. It preserves ALL existing and future-segment
observations, CSV/manifest archives, verified backups and both Keychain
items. Keychain credentials can be reviewed/deleted separately by the
Mac owner in Passwords/Keychain Access if no longer wanted. Do not edit,
delete, replay or rebootstrap earlier journal segments as part of shutdown.

## Scope and validation

Automated scheduling of **market-data GET-only observations** was explicitly
approved by the owner after the first three manual capture/backup/recovery
acceptance tests. It is NOT consent to use the old paper-order daemon,
Alpaca paper order POST, live trading, deposits, deployment, discretionary
spend, automatic social/marketing actions, or real-money experimental
trading. No ChatGPT conversation or GitHub push can install/run a process
on the owner's personal Mac without the above local action.

CI tests inject fake sources and real isolated temporary SQLite/CSV archives:
0/1/2 consecutive hourly ticks, duplicate tick idempotence, missed-hour
segment isolation, original manual journal protection, corrupt evidence
fail-closed, owner-only pointer and receipts, clock rollback, path collision,
Keychain redaction and forbidden LIVE/generic env vars, Mac plist structure
and explicit install/stop protections. Real Mac Keychain/launchd integration
is only validated after the owner's own one-time installation and first
two successful scheduler ticks.
