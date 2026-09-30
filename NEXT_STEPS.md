# Signal Vault — current next steps (2026-09-30)

**NO OWNER DESKTOP ACTION IS REQUIRED. Do not Fetch/Pull/run Terminal for the cloud collector.** The production Railway BTC-first six-crypto GET-only service is already configured and freshly built. The next production milestones are time-dependent scheduled evidence, not a Mac command.

1. **COMPLETE:** first post-activation runtime tick at 2026-09-30 03:08:20Z verified BTC first (BTC prospective count 7) and a six-crypto 72h historical baseline with **0** prospective hours / **0** prospective asset-bars. Baseline source SHA-256: `565a0066157736ba9ddfd9cc44032ef3689e2acd1737980e8141f1faa5f97bfb`.
2. Verify the next exactly contiguous hourly tick (scheduled around 04:07Z): BTC must continue; six-crypto must add 6 source asset-bars but exactly **1** distinct prospective UTC hour and create the immutable six-market offline shadow. Any missed hour resets only the sidecar's current segment via a new historical baseline; never backfill.
3. Continue unattended hourly collection toward **168 consecutive distinct sidecar prospective UTC hours**. Historical bootstrap bars, six-asset multiplication, old BTC hours, and stock history do not count toward that 168-hour sidecar threshold.
4. Keep automatic PAPER orders DISABLED and LIVE unavailable. Historical/synthetic strategy results do not authorize order submission. Any future PAPER order activation requires a separate explicit owner decision after forward evidence, realistic execution/friction review, account eligibility/minimums, and reconciliation design.
5. Continue engineering offline/read-only integrity, incident recovery, evidence manifests, monitoring and failure tests while the clock-based collector accumulates data. Only interrupt the owner for a true permission/access/paid-resource/trading decision.

**Current production identifiers:** Railway project `11cfaecd-9956-46a7-b94a-99a1dc4cd4c9`, environment `628e903d-c28f-42c1-bf59-9f7d91574dd0`, service `d3d04ec9-1f74-428a-a4a3-03a35bce2dd2`, fresh deployment `e35d6734-6390-49c5-b7fd-fac7fd7d6213`, source main `0f84c41290702c40f80f9d18ea289b7c4feaa2ce`. Volume remains 500 MB at `/var/lib/signal-vault/forward` and cron remains `7 * * * *` UTC.

---

# Signal Vault — user-approved unattended GET-only Mac activation prepared (NOT INSTALLED)

**CURRENT NEXT OWNER ACTION — ONE-TIME MAC SETUP ONLY, NO MORE
EVERY-HOUR TERMINAL ATTENDANCE.** Owner explicitly authorized building an
unattended BTC/USD historical DATA **GET-only** collector and preparing
one-time activation on their Mac after the 3 actual forward observations,
full evidence/snapshot audits, and scratch recovery/four-fault Phase 2O drill
all passed. New private GitHub main contains:
`src/signal_vault/unattended_forward_cycle.py`,
`src/signal_vault/mac_forward_agent.py`, fake-provider/Mac-install tests,
and `docs/UNATTENDED_FORWARD_COLLECTION.md`.

**No scheduler has been installed on the owner's Mac via GitHub or ChatGPT.**
After successful final CI and ordinary GitHub Desktop Fetch/Pull, the owner
can locally run:

```sh
# In their EXISTING checked-out signal-vault repo, activated .venv:
PYTHONPATH=src python -m signal_vault.mac_forward_agent --preview

# Two local macOS Keychain interactive password prompts: -w must be last
# flag without passing values as shell command arguments.
security add-generic-password -U -a signal-vault-forward -s com.signalvault.forward.alpaca-paper-data-key-id -w
security add-generic-password -U -a signal-vault-forward -s com.signalvault.forward.alpaca-paper-data-secret -w

# Explicitly activate user-only job, then verify local macOS load state.
PYTHONPATH=src python -m signal_vault.mac_forward_agent --install
PYTHONPATH=src python -m signal_vault.mac_forward_agent --status

# Once the next minute :07 tick runs, check verified segment/last receipt OFFLINE.
PYTHONPATH=src python -m signal_vault.unattended_forward_cycle --status
```

The first eligible scheduled :07 tick creates a **fresh separate auto segment**
with zero forward observations, never altering original
`observations.sqlite3` (3 owner-verified manual records) or the older
owner-verified archive `forward_20260929T070754_619609Z`. The following
consecutive hour can append the first new prospective auto observation.
If Mac sleeps/shuts down, a late wake is skipped and the next eligible fresh
hour creates another separate named segment without hindsight backfill; the
old source chain must audit clean first. Receipts and actual journal are
private and Git-ignored; Keychain secrets are NEVER placed in plist,
logs, GitHub or terminal commands. Only the fixed Alpaca BTC/USD historical
data host/path is allowed, no broker POST, live credentials, funding or paid
resource. `--uninstall` removes the verified label/plist but PRESERVES
all evidence/backups and original Keychain entries.

**After first real Mac auto-scheduled runs** request only nonsecret JSON from
`mac_forward_agent --status` and
`unattended_forward_cycle --status` (bootstrap count 0, then
consecutive observation count 1), not passwords or raw CSV. Real macOS
LaunchAgent/Keychain integration is pending actual owner activation and
must not be claimed validated by fake-provider CI alone. The Mac must be
powered on, logged into same user, awake and internet connected at minute
:07; locked/inaccessible Keychain fails closed. Developer then proceeds to
offline operator incident report, fake-broker UNKNOWN_RESULT/partial-fill
fault tests and separately preregistered strategy research, keeping PAPER
order POST and live mode disabled.

**Use private GitHub `Nkreddy15/signal-vault` branch `main` after the latest Phase 2K fast-forward pull.** Verify SHA/tree and run `make test`, `make compile`, `make demo` before editing; do not replace newer changes with an older ZIP. No live, broker paper POST or paid actions are authorized.

**Current immediate task (Phase 2J):** The owner already ran the fixed offline `research_economics` audit on GitHub head `3ad835e`; the exact modeled $15 reference-price hurdle was **70.3086237096701855 bps (+0.7031%)**, assuming 25 bps fee and 10 bps slippage on EACH side. Flat BTC price produces -$0.10473 after these hypothetical costs; v0.3 still lost even when costs were zeroed. Result documented in `docs/FORWARD_OBSERVATIONS.md`.

**Forward journal milestone verified by owner:** A 72-hour read-only capture ending at 04:00Z was used for one zero-observation bootstrap at 04:09:24Z. The owner then captured a fresh 72-hour BTC/USD window ending 05:00Z (SHA-256 `af181756673f49c40e827b488ae79cdb7920abe8b1963ac724a80014b1ff3850`) and successfully added exactly ONE new observed candle (04:00–05:00Z) at 05:05:56Z. The follow-up journal status agrees: observation count 1, no brokerage orders. Raw market CSVs, manifests and SQLite journal remain local under Git-ignored `data/forward/`.

**Next milestone: a one-command manual GET-only capture plus observation is now built and fake-transport tested.** The previous two-command ordering error (trying `--observe` before creating the new CSV) motivated `src/signal_vault/manual_forward_cycle.py`. On latest GitHub `main`, a single explicit `PYTHONPATH=src python -m signal_vault.manual_forward_cycle` validates the existing local journal FIRST, refuses missing or nonconsecutive hours before prompting for secrets or making a network request, then uses the same fixed-host Alpaca BTC/USD DATA GET and privately entered PAPER DATA keys to capture/verify exactly 72 closed candles and append exactly ONE new observation. Only call it between minute 03–24 of the **immediately next consecutive UTC clock hour**. It preserves raw CSV/manifest evidence if journal processing fails, refuses overlapping manual instances via an owner-local file lock and records no orders, strategy signals or hypothetical trade P&L. **Not yet executed against the owner's real provider by the assistant or verified on the owner's Mac.** No background service runs.

**Additional safe development completed while waiting (Phase 2L):** Added
`src/signal_vault/forward_evidence_audit.py`, a purely **OFFLINE READ-ONLY**
cross-check. After fetching the latest source, an operator can run
`PYTHONPATH=src python -m signal_vault.forward_evidence_audit` at **any
time**, even after the original captures expire for prospective collection.
This requires that the original 72h bootstrap CSV/manifest and every later
standard-named capture/manifest are still kept under `data/forward/captures/`;
they remain on the owner's Mac and are never uploaded. It opens SQLite with
`mode=ro`, checks `integrity_check`, source SHA-256 and capture timestamps,
reconstructs every anchored candle hash and rolling overlap, checks no time
gaps and recomputes all recorded numeric observations from their own original
CSV. It refuses missing/tampered/insecure evidence and makes **zero** provider
requests, journal changes, orders or strategies. Its PASS means **internal
unsigned local-evidence consistency only**, not provider authentication,
profitability or a reserved validation holdout. See
`docs/FORWARD_OBSERVATIONS.md`. Synthetic audit tests include two sequential
prospective observations, feature/SHA/manifest/timestamp corruption and
read-only file preservation. This auditor does not change the
`manual_forward_cycle` command needed for the next UTC observation.

**New optional credential-free preflight (Phase 2M):** After pulling
latest `main`, run `PYTHONPATH=src python -m
signal_vault.forward_readiness` before deciding whether to capture. It
requires that the original owner-local journal and all earlier captured
CSV/manifest files pass the Phase 2L **offline internal evidence audit**,
then reads the clock and determines the exact single consecutive next
UTC-hour capture window. It reports WAIT if the next hour has not closed,
WAIT during minutes 00–02, READY during `:03`–`:24`, EXISTING_CAPTURE
if that hour already has a fresh SHA/source-verified CSV/manifest pair, or
HALT/MISSED when backfill would be required. The command never prompts for
keys, calls a provider, alters SQLite, captures data, starts a scheduler, or
creates any order. A readiness result is an operational *data collection*
check, NOT evidence of trading eligibility or predictive edge. Run
`--db data/forward/observations-segment-02.sqlite3` only for a different
already-bootstrapped named segment. This functionality is offline
synthetic-test validated (GitHub CI 286 tests passed on 3.11 and 3.12 at
run `36526615489`), not yet owner-side Mac-tested.

**The owner's original clock plan is unaffected:** the one-button manual
collector is still `PYTHONPATH=src python -m
signal_vault.manual_forward_cycle`, between **2026-09-29 06:03 UTC and
before 06:25 UTC**, provided no new capture already exists for 06:00 UTC.
Do not run `--bootstrap` again against the original journal. A readiness
result of EXISTING_CAPTURE requires preservation and possible explicit
review of `forward_observer --observe --csv <EXACT_PATH>`, not re-capture
or deletion. The new readiness code can be pulled after the old collector
has finished its intended window if preferred.

**Owner outcome: REAL Phase 2K single-command continuation succeeded (2026-09-29 UTC).** After the original 05:05:56Z first manual two-command observation, the owner ran `PYTHONPATH=src python -m signal_vault.manual_forward_cycle` at the next eligible hour. It captured 72 authentic-looking provider GET-only hourly candles ending `06:00Z`, at `data/forward/captures/btcusd_72h_end_20260929T0600Z.csv` (SHA-256 `a3561b7f7cd64c5f2cd0bb3c7f5d098223f0d47896208a88799fb5d935c2b91f`), verified file/manifest, and atomically appended the second prospective hour (05:00–06:00Z) at `06:03:59.085819Z`; local journal now reports `new_forward_observation_count=2`, outcome `ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE`, no broker orders or scheduler. The only actual source is the owner's shared Terminal output; the assistant has not materialized owner-local raw data.

**Next useful owner verification (can run at any time, no credentials/network/write):**
`PYTHONPATH=src python -m signal_vault.forward_evidence_audit`.
For this specific original journal expect
`PASS_INTERNAL_CONSISTENCY_ONLY`, `prospective_observations_verified=2`,
`archived_csv_manifest_pairs_verified=3`. If it fails, do not change raw
evidence; share error. The prior earliest 03:00Z capture is not part of this
journal. If intentionally collecting hour three consecutively, run
`PYTHONPATH=src python -m signal_vault.manual_forward_cycle` in UTC
`2026-09-29 07:03:00Z–07:24:59Z` only. Optional
`PYTHONPATH=src python -m signal_vault.forward_readiness` can verify
eligibility first without credentials. If missed, retain the current
2-observation journal and begin only a distinct, freshly bootstrapped
segment on a later hour; never replay prior captures as forward data.

**Phase 2N BUILD NOW IMPLEMENTED (OFF by default):** The repository now
contains a dedicated forward observation archive utility at
`src/signal_vault/forward_snapshot.py`. This is separate from the existing
paper-order-ledger backup. It verifies the full local original source evidence
first, uses SQLite's backup API to take a consistent standalone local journal,
then copies the exact one-bootstrap-plus-N recorded-hour immutable CSV/source
manifest pairs referenced by that consistent journal. Before publishing a
new, private owner-only directory under ignored
`data/forward/backups/`, the *copied* journal and copied source files must
pass a second independent offline audit. It never opens Alpaca, prompts for
credentials, trades, overwrites an existing snapshot, resets an owner database
or restores into the active original. It produces a locally unsigned,
unencrypted, same-Mac archive; no third-party provider attestation or offsite
backup is claimed. Run only after an owner-side full source audit passes:

```sh
# At any time; entirely READ-ONLY, with expected post-06:00Z counts:
PYTHONPATH=src python -m signal_vault.forward_evidence_audit
# Expect PASS_INTERNAL_CONSISTENCY_ONLY, observation_count 2,
# and three source CSV/manifest pairs for the originally bootstrapped segment.

# Once that returns PASS and AFTER pulling the new Phase 2N code:
PYTHONPATH=src python -m signal_vault.forward_snapshot --create
# Manually copy the exact printed snapshot folder BASENAME into:
PYTHONPATH=src python -m signal_vault.forward_snapshot --verify <NAME>
```

Do not paste PAPER keys, raw CSVs or database bytes to ChatGPT or GitHub;
send only the nonsecret auditor/backup JSON. Full failure/limited
restoration procedure: `docs/FORWARD_SNAPSHOTS.md`. Synthetic fake-provider
tests cover zero/one/two hour chains, source non-mutation, extra unrelated
capture exclusion, hash checks, tampering, symlinks, path traversal and
isolated segment backup. This is NOT a restored operational paper account.

**Roadmap AFTER Phase 2N:**
1. Local read-only source/snapshot validation and failure injection on a
   separate temporary scratch directory; preserve originals and demonstrate
   that restoration never automatically enables order submission. Complete
   paper ledger interruption/UNKNOWN_RESULT and provider-drift test drills
   against fakes; choose separately between a single-host SQLite PAPER pilot
   and a real PostgreSQL Python/concurrency port. PostgreSQL migration SQL
   alone is not operational high availability.
2. Optional operator-only status/incident report for observation coverage,
   source hashes, gaps/segments, modeled cost assumptions and data quality.
   No personal secrets, order execution or public dashboard exposure.
3. Verify actual PAPER account/venue constraints, spread and fee rules using
   only separately owner-invoked approved GET requests, and compare against
   the fixed hypothetical 70.3086bps round-trip hurdle; do not assume
   empirical profitability from hypothetical costs.
4. Design/preregister a substantially different, reduced-turnover research
   candidate on permitted development data. v0.1/v0.2/v0.3 FAILED and are
   NOT promoted. Keep the reserved post-gap v0.3 dataset unopened. Any
   inspected forward observation is exploratory development data, never
   described retroactively as a sealed independent validation sample.
5. Only if a fixed candidate passes its predeclared evidence gates, develop
   an offline-only shadow signal/report and validate incident behavior.
   Actual Alpaca PAPER order POST, unattended deployment, hosting, paid
   services, live transfer and deposits each require distinct explicit
   decisions. No live code path is currently enabled.

**Phase 2N first real-data snapshot now PASSED (owner report, 2026-09-29 07:07:54Z):** The owner's original forward journal has been independently audited at 3 genuine new observations and four source CSV/manifest pairs. Owner ran `PYTHONPATH=src python -m signal_vault.forward_snapshot --create` successfully: `OFFLINE_FORWARD_SNAPSHOT_CREATED_AND_ISOLATED_VERIFIED`, `PASS_INTERNAL_CONSISTENCY_ONLY`, 3 observations, 4 source capture pairs, 9 SHA-verified copied files, no journal mutation, network or orders, overwrite disabled. Unique existing private Mac-local snapshot name:
`forward_20260929T070754_619609Z`. This backup is same-device, unsigned and unencrypted. It is not a production restoration, filled-paper-trade result or offsite backup.

**Immediate next optional command, WITHOUT broker credentials or data GET:**
```sh
PYTHONPATH=src python -m signal_vault.forward_snapshot --verify forward_20260929T070754_619609Z
```
Repeat the isolated read-only archive verification; expect 3 observations,
4 CSV/manifest pairs, 9 file hashes and `PASS_INTERNAL_CONSISTENCY_ONLY`.
Then proceed to Phase 2O offline scratch-folder failure/recovery validation;
never restore over or rewrite `data/forward/observations.sqlite3`.
No pull required for this verification if Phase 2N `--create` just ran
successfully on the same Mac. The old 2-observation and bootstrap notes
elsewhere are historical milestones, not the current observation count.

**Phase 2N REAL local repeat verification PASSED:** Owner executed
`PYTHONPATH=src python -m signal_vault.forward_snapshot --verify
forward_20260929T070754_619609Z`; local JSON reports
`PASS_INTERNAL_CONSISTENCY_ONLY`, 3 genuine forward observations,
4 source CSV/manifest pairs and 9 file hashes; original journal untouched;
zero network and no broker orders. No additional snapshot creation is
necessary for the next drill.

**New Phase 2O code now available on private GitHub main (offline only):**
`src/signal_vault/forward_recovery_drill.py` safely copies exactly the
already-verified original private snapshot into isolated scratch directories,
verifies the copied chain, then challenges both read-only verification
layers with four independently mutated DISPOSABLE clones. Finally it checks
that original backup fingerprints remain unchanged and removes scratch data.
It never attempts an active restore or opens the active original journal,
collects no new market bar and needs no credentials or provider calls.
CI passed 302 offline tests on Python 3.11 and 3.12 (run `36535242811`);
bootstrap-only no-source-write check also passed in subsequent CI.
**User's real Mac Phase 2O drill remains PENDING.**

**Exact next operator command, once latest GitHub main has been pulled:**

```sh
PYTHONPATH=src python -m signal_vault.forward_recovery_drill \
  --snapshot forward_20260929T070754_619609Z
```

Expect `PASS_ISOLATED_RECONSTRUCTION_AND_FAULT_REJECTION`,
`recovered_observations_verified=3`,
`recovered_capture_pairs_verified=4`, 10 original archive
file hashes including `snapshot.manifest.json`,
FOUR injected faults independently rejected by both verification layers,
scratch cleanup COMPLETE, original backup hashes unchanged, original active
journal untouched, no API calls, orders or scheduling. Send only the nonsecret
JSON output. Refer to `docs/FORWARD_RECOVERY_DRILL.md`; this is a
same-device unsigned/unencrypted scratch rehearsal and not production
disaster recovery or proof of strategy performance.

**Subsequent Phase 2O/2P path:** consolidate an operator coverage/incident
report that classifies continuous vs missed-hour segments; exercise the
separate PAPER ledger's interrupted-submission/UNKNOWN_RESULT and recovery
paths strictly with injected/fake providers and disposable databases;
separately confirm account-specific fees, spread and venue constraints by
owner-invoked approved read-only GET; then preregister a substantively
different research candidate without tuning against the reserved holdout.
Real PAPER POST and any unattended service require new explicit approvals.
Do not equate synthetic fault tests with an actual broker failover.

**Owner's FIRST REAL PHASE 2O DRILL — PASSED (2026-09-29):**
Owner independently reran `forward_snapshot --verify
forward_20260929T070754_619609Z` and then invoked
`PYTHONPATH=src python -m signal_vault.forward_recovery_drill --snapshot
forward_20260929T070754_619609Z` on the local Mac. Shared result:
`PASS_ISOLATED_RECONSTRUCTION_AND_FAULT_REJECTION`, 3 independently
reconstructed forward observations, 4 source capture pairs, 10 snapshot
files checked including the snapshot manifest; four disposable faults
(`altered_csv`, `altered_source_manifest`, `altered_journal_metric`,
`missing_capture_manifest`) **each rejected by BOTH verification layers**.
The saved original snapshot hashes remained unchanged, temporary evidence
cleanup completed, active journal not opened/modified, no network, broker
orders or automatic scheduling. This is real owner-side execution of a
same-device offline SCRATCH recovery DRILL, not a production restore or
encrypted offsite backup. The saved snapshot was successfully repeat-verified
before the drill; no need to rerun either command just to continue development.

**NEXT ENGINEERING MILESTONE — Phase 2P**: Create a strictly read-only
operator evidence-coverage/incident summary for the original and any separately
named future forward segments: verified source/data fingerprints; bootstrap vs
prospective counts and start/end times; next eligible contiguous UTC hour;
meaningful gaps/segment boundaries without hindsight relabeling; existing
verified snapshot name/status only if explicitly specified. No change to
journal/capture/backups; no network, strategy signals, provider paper POST,
live endpoint, account or scheduler. Build synthetic tests covering zero/one/
three-observation chains, post-missed-hour classification, separate segment
isolation and corrupt evidence. Then run on the owner's Mac using a single
operator command, if/when convenient. Do not create another mandatory
middle-of-the-night data collection window.

**NEXT PAPER SAFETY GATES after 2P:** on disposable databases and fake broker
transports exercise interrupted submission/UNKNOWN_RESULT, duplicate
submission prevention, delayed/partial fills and provider/ledger reconciliation.
Then separately verify actual account-specific fee, spread and venue rules
through an approved owner-invoked GET-only procedure before choosing a new
preregistered research candidate. v0.1/v0.2/v0.3 remain FAILED, not eligible
for broker-paper shadow promotion; the untouched reserved post-gap data must
not be used to rescue failed candidates.

**If the existing journal's next consecutive hour was already missed:** do not try to backfill, delete/reset or repeatedly retry the primary journal. Keep it. Begin a new explicitly named prospective journal in a fresh UTC hour with the original `forward_capture`, followed within that same hour by `forward_observer --bootstrap --db data/forward/observations-segment-02.sqlite3 --csv <EXACT_NEW_CAPTURE_PATH>`; that new segment begins with ZERO retrospective observations. In the NEXT consecutive hour, use `PYTHONPATH=src python -m signal_vault.manual_forward_cycle --db data/forward/observations-segment-02.sqlite3`. Full owner procedure and failure handling: `docs/FORWARD_OBSERVATIONS.md`. No scheduler, paper POST, funding or live permissions are enabled.

1. **Local PAPER authentication/readiness CLEARED for read-only research (owner-reported 2026-09-28).** Local authenticated `paper_smoke` returned READY with logical $100 limit and BTC/USD constraints; quote GET succeeded; no credentials were shared to chat/GitHub. Recheck account and venue readiness, fee/tick rules, actual quote/feed behavior before any future separately authorized paper POST. Keep paper-order acknowledgement OFF.
2. **Research status: v0.1, v0.2 and v0.3 NOT PROMOTED.** Owner verified four locally retained historical CSV fingerprints covering 6,647 genuine hourly BTC/USD observations with exactly one confirmed missing 2026-03-12 17:00Z candle. Never bridge the gap, upload credentials or overwrite original datasets. v0.1 failed both its fixed pre-holdout gate and final holdout, and its pre-gap development performance was negative with and without simulated fees/slippage. `docs/RESEARCH_V02.md` preregisters one two-closed-bar BUY entry confirmation while preserving immediate SELL, fixed costs/risk and default v0.1. Owner reported v0.2 pre-gap run (SHA-verified, 1,843 rows): -$4.9023 after modeled costs, -$1.6674 zero-cost, 62 fills, $2.3156 modeled fees; v0.1 was -$4.9129 after modeled costs, -$1.4142 zero-cost, 67 fills, $2.5036 fees. Neither variant merits promotion. See `docs/RESEARCH_V02.md`. Owner's descriptive `research_attribution` output reconciled: v0.1 21/21 completed exits under 24h lost and v0.2 20/20 lost; all seven winning completed trades in each version ran at least 24h. Duration is known only after the exit and MUST NOT be turned into a minimum holding rule. Owner completed `research_entry_context` on pre-gap only. Median prior-24h return for the seven profitable v0.1 completed trades was +80.289 bps vs +42.759 for its 26 losing trades; v0.2 +59.898 vs +43.583 bps (7 and 24 trades respectively). Under-24h subsequent exits entered with median prior-24h returns +8.611 bps (v0.1) / +27.137 bps (v0.2); descriptive hindsight labels only. **The single v0.3 hypothesis is now preregistered in `docs/RESEARCH_V03.md`:** preserve v0.1 timing and immediate sells but veto bullish-cross BUY unless 24-hour completed-close return is at least +50 bps. Threshold is based on already-explored development data, not a proven independent signal. Owner's first-and-only preregistered v0.3 development command completed on SHA-pinned pre-gap: -$2.2277733837 after costs, -$0.6614925183 with costs zeroed, 30 fills, $1.1208263825 modeled fees and eleven-fold aggregate -$2.0126983476 (four positive folds). The locked development gate returned FAILED because neither after-cost nor zero-cost aggregate P&L was positive. This compares with v0.1 -$4.9128961148 after costs, -$1.4141588344 zero-cost, 67 fills. v0.3 is FROZEN AS FAILED; do not tune its +50 bps threshold or run it on the reserved post-gap dataset. Detailed results in `docs/RESEARCH_V03.md`. **Phase 2J cost review and GET-only observation capture are now implemented**; owner-run economics output is recorded and the next uncompleted external milestone is optional owner-side fresh GET-only capture plus zero-observation bootstrap. Design a substantively different, preregistered lower-turnover strategy separately; do not treat already-inspected pre-gap data as unseen. No broker POST or funding. Previously examined v0.1 final holdout cannot be considered unseen. Optional logistic ML is for separately reviewed PAPER SHADOW only; no approved research artifact exists yet. Current bounded LLM advisory has NO configured/authorized transport and adds no API cost by default.
3. **Persistence:** Apply `db/migrations/0002_critical_paper.sql` only to an authorized isolated dev PostgreSQL. Complete Python critical ledger port (draft/reservations/order state, fill/fees/position reconciliation and halt/audit) and actual concurrent transaction/failure tests. The current single-host SQLite daemon cannot claim HA. The owner may instead explicitly authorize a monitored single-host PAPER pilot with this limitation, not a real-money shortcut.
4. **Operator / service gate:** read-only local HTML monitor port 8766 and separate Bearer owner-control API port 8765 have tests, not deployments. Resolve cloud account, pricing, backups, secret files, incident operator procedures, and remote access via SSH/TLS gateway; never expose direct HTTP ports. Reconfirm daemon accepts only literal paper host and explicit paper-only submission acknowledgement.
5. **Fault drills:** disk full/malformed ledger, stale or crossed quote, unknown POST/timeout, partial fill/fee delay, duplicate worker, missed activity, provider drift, post-crash same-ID reconciliation, secrets/log exposure, immutable DB audit.
6. **Seven-day genuine PAPER operation:** only after owner auth and tests, monitor logical $100 account, reconcile every provider receipt, fill, fee, position and cash. A week of paper profit is only an operational observation; insufficient trade sample means extend testing.
7. **Nov 1 live:** purely conditional, never automatically funded or enabled; separate explicit decision and reviewed live code/service. No live endpoint exists today.

**Resume prompt:** `Continue Signal Vault from private GitHub main. Read PROJECT_STATUS.md/NEXT_STEPS.md, run tests and implement the next PAPER-only milestone. Keep live and spending disabled.`
