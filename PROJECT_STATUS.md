# CURRENT CLOUD CHECKPOINT — 2026-10-01 (authoritative over older notes below)

**Recovery rule:** read `BUILD_CHECKPOINT.json` first after any retry, new chat, or interrupted run. It is the machine-readable authority for current phase, main SHA, CI, Railway deployment, lane blockers, and next actions.

Signal Vault remains on the existing Railway all-market GET-only cron, existing 500 MB persistent volume, and unchanged hourly `7 * * * *` UTC schedule. No new paid resource was created. Automatic PAPER/DEMO submission remains disabled and LIVE remains unavailable.

**Latest verified production tick (2026-10-01 09:09 UTC):** six-crypto reached **23 prospective source hours / 22 fully scored precommitted outcomes**, leaving **146/146** to the frozen 169-hour/168-outcome review gates. US equities have **1/10** prospectively precommitted XNYS session plans and **0/60** core-hour receipts; the October 1 session plan remains valid and receipts must be captured only when genuinely due. The persisted all-market dashboard snapshot reported AVAILABLE.

**Kalshi:** the last verified pre-Phase-126 tick still failed safely with `DISCOVERY_PAGE_LIMIT_EXCEEDED` and no plan. Phase 126 commit `eca669bc270589a5f51fb4fa3ebe3a402e4a6fc6` is deployed successfully as Railway deployment `5778f044-b5bc-42bc-a664-a53345ed6508`. Planning now prefers the public event endpoint with nested markets and stops when the predeclared 22-market / >=10-distinct-event structural sample is satisfied instead of requiring exhaustion of the full market catalog. The first post-Phase-126 cron is still required before claiming a Kalshi plan exists.

**PAPER execution engineering:** the supervised Alpaca PAPER smoke remains reconciled. Phases 118–127 now provide the durable approved draft, one-shot PAPER executor, fresh provider-account preflight, <=5-minute execution-boundary freshness requirement, auditable preflight refresh history, sanitized dashboard preflight state, and a preflight-first local pilot command. The command defaults to **GET-only preflight with no order submission**; one-shot PAPER execution still requires a separate explicit execute flag plus the exact crypto PAPER acknowledgement. Autonomous strategy PAPER remains disabled pending the real frozen forward gate and separate owner execution decision.

**Dashboard:** the all-market HTML/JSON monitor, persisted Railway snapshot, standalone private loopback viewer, PAPER pipeline state, and provider-preflight status are built. Public Internet exposure remains disabled. Railway volumes are tied to one service, so the current cron volume is not being exposed through a second service merely for convenience.

**Owner action:** none required for unattended cloud collection. Do not ask the owner to run hourly Terminal commands. Next engineering proof is the first post-Phase-126 Railway cron; next PAPER action remains preflight-only unless the real evidence gate clears and the owner explicitly chooses a one-shot PAPER execution.


---

# SIGNAL VAULT — current cloud checkpoint (2026-09-30)

**CURRENT AUTHORITATIVE STATE:** The owner explicitly approved and the existing Railway service `btcusd-hourly-get-cron` is active on the reviewed **BTC-FIRST six-crypto DATA-GET-only** command `python -m signal_vault.railway_btc_first_dual_cron --once`, unchanged UTC `:07` hourly cron and unchanged single 500 MB persistent volume at `/var/lib/signal-vault/forward`. The exact non-secret sidecar flag is active. No credential values were read or changed by ChatGPT.

**BTC STREAM VERIFIED HEALTHY THROUGH 08:07 UTC:** the original BTC collector continued independently from count 7 at the first dual tick to **12 genuine prospective BTC observations** by the 08:07 UTC runtime. Actual logs—not deployment status alone—showed `ONE_NEW_PROSPECTIVE_CANDLE_RECORDED` and `ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED`. Broker order submission and automatic PAPER trading remained disabled.

**SIX-CRYPTO SOURCE STATE:** at 03:08:20Z the sidecar created the exact 72-hour retrospective baseline with **ZERO prospective sidecar hours / ZERO prospective sidecar asset-bars**, source SHA-256 `565a0066157736ba9ddfd9cc44032ef3689e2acd1737980e8141f1faa5f97bfb`. The next five real sidecar attempts (04:08, 05:10, 06:10, 07:11, 08:07 UTC) failed safely with `PermissionError`. They did not backfill missed hours, did not reset/delete BTC evidence and did not enable orders.

**PERMISSION-INCIDENT HARDENING DEPLOYED:** Phase 21 adds exact sidecar execution stages plus narrowly scoped root-only restriction of only the known sidecar child directories `hourly-receipts` and `immutable-six-crypto-shadows` to mode 0700. It deliberately refuses to chmod an insecure sidecar root or follow a symlink. Phase 22 adds read-only failure forensics for only the exact sidecar root, persistent lock, receipts and shadows: existence, symlink/type, mode, process-UID equality and read/write/execute checks. It exposes no path contents or credentials and performs no repair outside the known child-directory mode restriction.

**CURRENT PRODUCTION IMAGE:** Railway deployment `a9af8775-9c13-4a95-b02b-32979e7e50a9` built successfully from main source `b88cdc5dd409fca04021b83b78f9c7ffcaa8354e`. The single 500 MB volume, service, cron and no-order configuration are unchanged. Current measured disk use remains only a small fraction of the volume, well below the sidecar's 32 MiB evidence cap and the protected 128 MiB BTC free-space reserve.

**NEXT PRODUCTION VERIFICATION:** inspect the first actual `:07` runtime after this image. BTC must advance beyond 12. If the sidecar succeeds, because the 03:08 baseline was followed by missed/failed hours it must create a **new 72-hour historical-only segment with zero prospective observations**, not retroactively claim the gap. Only the following contiguous hour may become the first genuine six-crypto prospective source hour (6 asset-bars = 1 clock hour). If it still fails, use the emitted `sidecar_stage` and bounded permission snapshot to fix only the proven sidecar-owned permission issue.

**FORWARD REVIEW POLICY IS FROZEN BEFORE SIDE-CAR OUTCOMES:** the merged v1 review gate requires 169 consecutive prospective source hours / 168 fully observed precommitted outcomes plus fixed fill, base/high-friction P&L, passive-comparator and drawdown criteria. Passing means only eligible for a separate owner PAPER execution-design review; it never selects/ranks a strategy or authorizes orders.

**PAPER FAILURE SEMANTICS DRILL COMPLETE OFFLINE:** the persistent synthetic restart/partial-fill fault drill proves durable pending → UNKNOWN_RESULT recovery, exact client-ID GET-only recovery, monotonic partial fills and immutable terminal state across restarts, with zero actual paper POSTs. It does not activate the PAPER worker.

**NO ORDER PERMISSION ADDED.** Automatic PAPER trading remains **DISABLED** and LIVE trading remains **UNAVAILABLE**. No new Railway resource, paid plan, account funding, SIP feed, deposit or order POST is authorized.

---

# SIGNAL VAULT — legacy durable/local engineering history

**The material below is retained for provenance, not as the current owner to-do list. The active collector is Railway cloud production above; do not Fetch/Pull or run Mac setup for current collection unless a future request explicitly requires it.**


# SIGNAL VAULT — durable engineering checkpoint

**Checkpoint:** UNATTENDED-GET-ONLY-MAC-BUILD-2026-09-29 (3 manual original forward observations + audit/archive/scratch recovery owner-verified; NEW explicit user-approved Mac hourly GET-only worker and Keychain-backed LaunchAgent build, activation NOT YET performed on owner Mac).
**Private repository:** https://github.com/Nkreddy15/signal-vault (`main`). Prior remote Phase 2H commit `338094301d368a7d5afe506ebcd47884bec330ed`, exact file tree `e17305a09eeda46465d825dd507eb8ca2e9c4347`. Phase 2I source must be separately exact-tree synced before stopping; do not force-push or overwrite others' work.
**Authorization/status update (owner-run, 2026-09-28):** Development and local/offline/PAPER-only implementation. The owner reports successful local authenticated Alpaca PAPER read-only account smoke and read-only BTC/USD quote/history capture. Keys were never supplied to ChatGPT or committed to GitHub. No broker paper POST, cash deposit, live order, live endpoint, cloud deployment, purchase or public publishing has occurred.
**Deadline:** November 1, 2026 is a *conditional* target for an owner-authorized $100 experiment, not a guaranteed profitable system or automatic live launch.

## Verified completed engineering work

- Modular single platform with market-adapter contracts; enabled candidate market is BTC/USD PAPER, not stocks/Kalshi. Deterministic closed-hour EMA crossover baseline, versioned evidence/HOLD; chronological research fold/backtester with hypothetical cost assumptions, research protocol and guarded promotion criteria. No verified alpha claimed.
- Market data strict validation, injectable READ-only provider adapters, authenticated read-only dataset-capture code with fingerprints (not called with real account), bounded read retry; stale/missing data fail closed.
- Deterministic Guardian for a logical $100 portfolio, example $15 single order/$30 combined exposure, $3 daily pause/$10 drawdown, no leverage; strong NaN/inconsistent-equity/invalid-policy checks. These are demo defaults, not an owner-approved live mandate.
- Durable local SQLite draft/idempotency/UNKNOWN_RESULT state, one unresolved order at a time, fill/fee/order/position audit, logical portfolio marks and cash, restart recovery and operator HALT. Fake-provider integration tests only; accepted provider order never mislabelled filled.
- Optional bounded LLM advisory code (`ai_advisory.py`) accepts an allowlisted public feature frame only; default paper worker/daemon does NOT load an AI transport. It may veto a new-money BUY but cannot place any order, override Guardian, alter limits, or veto the risk-reducing SELL path. Bad schema/transport fail closed.
- Separate optional logistic ML confirmation feature research, offline trainer, immutable JSON artifact and provenance/paper-shadow receipt gate. Model has not been trained on genuine broker data or promoted to live trading. Research modules and tests do not prove predictive ability.
- Paper-only one-cycle worker and unattended scheduling shell, owner-only single-process lock, bounded read retries, durable stop, classified safe local alerts, health report, source-labelled performance report and backup scheduling hooks. Never deployed.
- Local read-only HTML/JSON monitor `operator_server.py` defaults to 127.0.0.1:8766 with Basic token and cannot control orders. Separate Bearer-auth owner JSON control API defaults to 127.0.0.1:8765 with status/health/operator halt/resume ONLY. Status and resume now refuse a missing journal rather than silently creating a clean $100 account. These ports must never be exposed publicly.
- Local ledger preflight, private journal mode 0600, explicit init, consistent exclusive SQLite snapshot and integrity checks, optional daily local backups; restore never authorizes trading without provider reconciliation.
- systemd single-host paper/owner service **templates only** (including distinct monitor example). PostgreSQL isolated PAPER-only migration and transactional requirements are an **UNAPPLIED design**: no Python PG port, DB deployment or real PG tests yet.
- Earlier owner/assistant engineering checkpoint: local `make test` 225/225, `make compile` and `make demo` PASS, demo returns `DRY_RUN_RECORDED_NOT_FILLED`. The v0.3 research checkpoint passed 243 offline GitHub Actions tests; Phase 2J forward/economics additions have **261/261 offline tests passing** on Python 3.11 and 3.12 at GitHub Actions run `36518576175` (source head `6bd134aa059e82225486cb717d4707957ac812f5`). Tests use synthetic/fake provider data and check live-mode refusal. No genuine paper fills or claimed profit.

## Local empirical evidence and v0.2 development checkpoint (2026-09-28)

The owner reports four local BTC/USD hourly datasets, each with a matching independently checked SHA-256:
- Pre-gap 1,843 bars, 2025-12-25 22:00Z to 2026-03-12 17:00Z exclusive; `0f31fa3e6226a504db4b60185ae7388ae8979c14e3ccef1fc1b98e2b809071cc`.
- Confirmed missing source candle at 2026-03-12 17:00Z (the targeted Alpaca API GET also omitted it). The gap remains unfabricated.
- Post-gap older 2,476 bars, 2026-03-12 18:00Z to 2026-06-23 22:00Z exclusive; `56ce999182c0537b99ef9b7eff71ab9e6842e211ece7fcdfdff6c7dca90ca076`.
- 90-day research 2,160 bars; `131e6959c6e8f512238767fb3cb005de2cd3d378e9cefa8b774891d2773188bf`.
- Following seven-day 168 bars; `c6b96f1116f4a7ed7306a7b5ac2f2ce12225eaf8ad6d02a8327ad600689000b1`.

These CSVs and their manifests are retained locally on the owner's Mac, not checked into this source repository. The owner ran v0.1 on the 90-day research set (pre-holdout gate FAILED; final holdout negative), seven-day sample (negative) and pre-gap development set (67 simulated fills; -$4.9129 with modeled costs, -$1.4142 with zero costs; 7 of 33 completed trades profitable). v0.1 is not eligible for provider-paper shadow promotion. The previous 90-day final holdout is already examined, and must not be called unseen again.

New **v0.2 research-only candidate**, `docs/RESEARCH_V02.md`: unchanged 12/26 EMA and immediate SELL; an upward crossover BUY requires a second consecutive positive fully closed bar. Default v0.1 remains unchanged. `python -m signal_vault.research_v02` strictly permits only the verified pre-gap development dataset and reports v0.1 versus the candidate with and without modeled costs. **First owner-reported development result:** v0.2 net P&L -$4.9023 with costs and -$1.6674 without costs, 62 simulated fills, estimated fees $2.3156; v0.1 -$4.9129 with costs and -$1.4142 without costs, 67 fills, fees $2.5036. Neither has positive P&L; v0.2's approximately $0.011 costed difference is not evidence of edge, and its raw zero-cost result was worse. **v0.2 NOT PROMOTED** to broker-paper shadow/execution. See `docs/RESEARCH_V02.md` for predeclared hypothesis and full result. Preserve existing evaluation sets and keep paper POST off.

## Most recent research and next local run (owner reports, September 28)

Owner ran SHA-locked pre-gap `research_entry_context` with reconciled trade evidence for v0.1 and v0.2. Median *prior-to-BUY* 24-hour BTC returns were +80.289 bps for v0.1's seven subsequently profitable completed trades vs +42.759 bps for its 26 losing completed trades; v0.2 +59.898 bps (seven profitable) vs +43.583 bps (24 losing). Trades subsequently exited in under 24 hours had median prior-day return +8.611 bps (v0.1, 21 trades) and +27.137 bps (v0.2, 20 trades). These small, heavily correlated retrospective cohorts are hypothesis-generating only; 24-hour holding duration is hindsight and must never be forced as a safety policy.

`docs/RESEARCH_V03.md` **preregistered a single new research hypothesis before candidate implementation and before any v0.3 empirical result**. An opt-in, independently versioned v0.3 preserves v0.1's original immediate SELL and one-hour BUY crossover, but vetoes a BUY unless the prior two completed hourly closes 24 hours apart imply at least **+50 bps** of BTC price gain over the preceding 24 hours. This threshold was deliberately informed by the observed development data, so only independent reserved/prospective evaluation could support generalization; no grid search or tuning is authorized. The research runner `PYTHONPATH=src python -m signal_vault.research_v03` uses only the pre-gap SHA-pinned CSV, reports v0.1/v0.3 costs/zero-cost and disjoint 168-hour fold summaries, and enforces the fixed development gate. **First and only owner-reported v0.3 development run is complete and failed its fixed gate:** v0.3 after-cost P&L -$2.2277733837, zero-cost P&L -$0.6614925183, 30 fills, modeled fees $1.1208263825, eleven disjoint fold aggregate -$2.0126983476 (4 positive folds); baseline v0.1 after-cost P&L -$4.9128961148, zero-cost -$1.4141588344, 67 fills. The failed criteria were positive after-cost P&L and positive zero-cost P&L. v0.3 is now **frozen as FAILED / NOT PROMOTED**. The reserved post-gap dataset was not opened for v0.3. See `docs/RESEARCH_V03.md` for exact owner-reported evidence and research disposition. Paper-order submission remains disabled.

## Phase 2J — local read-only evidence engineering (September 28 US Eastern / September 29 UTC)

Built `src/signal_vault/research_economics.py` plus regression tests: a fixed, fully offline $15 buy-then-sell sensitivity report uses the **same arithmetic** as `backtest.py`, with assumed 0.25% fee/side and 0.10% adverse slippage/side. It exposes the exact estimated reference-price break-even hurdle, not an account-tier fee quote or strategy improvement. Run `PYTHONPATH=src python -m signal_vault.research_economics` after pulling.

Built a separate opt-in, **manual GET-only forward observation MVP**:
- `forward_capture.py` prompts for locally hidden PAPER data credentials and allows only the hardcoded Alpaca BTC/USD **historical DATA GET** with redirects refused. It captures the preceding 72 completed UTC hours at least 3 minutes after the hour and creates a unique, non-overwritten CSV and matching SHA-256/source/UTC manifest in ignored `data/forward/captures/`. The function is tested using fake providers; it has **not been run against the owner's real Alpaca data account by the assistant**.
- `forward_observer.py` itself contains no network request, credential or broker-order executor. It checks the CSV/manifest fingerprint and capture freshness. The first explicit `--bootstrap` anchors the past candles in a local owner-only SQLite journal with **ZERO retrospective forward observations**; one subsequent `--observe` transaction may record exactly one genuinely new, recent closed-hour BTC candle with past 6h/24h return, 24h range and hypothetical break-even hurdle, not a BUY/SELL recommendation. It rejects changed overlapping historical bars, gaps, missing source overlap, stale/future candles, multiple missed hours, journal reset, repeat duplicates (idempotent no-op), and clock rollback.
- Distinct captured CSV/manifests are preserved rather than overwritten; both `data/forward/` and the previously verified `data/research/` remain Git-ignored. Raw evidence is not copied to the repository. **No recorder is automatically running; no new owner observations have yet been reported.** `docs/FORWARD_OBSERVATIONS.md` gives the exact manual run and missed-hour rules. Observations used in strategy design become development evidence, not a magically sealed independent holdout.
- No new strategy version, no provider PAPER POST, no live or spending has been enabled; v0.1/v0.2/v0.3 remain rejected. The reserved post-gap research file is not accessed by Phase 2J.

## Owner-reported Phase 2J economics + current-hour forward safeguard

On GitHub checkout `3ad835ecfcf80a0d4acb8ca3cf04bea3e2ead373`, the owner successfully ran `PYTHONPATH=src python -m signal_vault.research_economics`. Its offline JSON reported:
- Fixed model assumptions: $15 BUY budget, 25bps fee **per side**, 10bps modeled adverse slippage **per side**.
- Exact modeled reference-to-reference break-even rise: **70.30862370967018550890511000bps** (about +0.7031%).
- Modeled cash result if price does not move: **-$0.1047266171328671**; +50bps: **-$0.0302502502185315**; +75bps: **+$0.0069879332386364**; +100bps: **+$0.0442261166958042**. The zero-cost flat-price control returned $0. Real actual fee tier/spread and execution were not checked by this run. This sensitivity cannot be converted into a profitable trading claim and does not rescue the v0.3 negative zero-cost results.
- Written evidence and full fixed scenario summary: `docs/FORWARD_OBSERVATIONS.md`.

Additional safety improvement: `forward_observer._fresh_closed_sequence` now requires the capture's last fully closed bar to close **exactly at the beginning of the current UTC clock hour**, not as much as 90 minutes earlier. This prevents delayed bootstrap or observation from treating an already-observable past bar as a prospective new observation. The owner must run `forward_capture` after minute 03 UTC and immediately use the printed CSV for `--bootstrap` (first time only) or `--observe` during the **same UTC clock hour**. File/manifest, overlap, single-bar append and existing permission checks still apply. This was validated in CI with explicit late-capture regression tests; no owner real-data forward capture is yet reported.

## First authenticated forward capture and zero-observation bootstrap (owner-reported September 29 UTC)

On local checkout `13e646325632be984a3af96001cb183b16da7955`, the owner performed two explicit **Alpaca BTC/USD historical DATA GET-only** captures using hidden local PAPER-data credentials; no credentials were sent to chat, and no trading/account/order API action occurred:

- Earlier raw 72h capture: `data/forward/captures/btcusd_72h_end_20260929T0300Z.csv`, SHA-256 `46fc7ea3a4596eded8ea9cee041892144c11126b19c010707d9dbab285f2c146`; preserved locally, not used for bootstrap.
- Current-hour capture: `data/forward/captures/btcusd_72h_end_20260929T0400Z.csv`; first candle start `2026-09-26T04:00:00+00:00`, exclusive last close `2026-09-29T04:00:00+00:00`, **72 actual hourly bars**, SHA-256 `6e95c45d803d8ef5b575f9b40460ee80994526a3d44d37d47bb373b8ec034ab6`. Source manifest is `.csv.manifest.json` alongside the locally ignored CSV.
- Owner executed one `forward_observer --bootstrap --csv ...0400Z.csv` at `2026-09-29T04:09:24.607905+00:00` and then `forward_observer --status`. Both returned matching `LOCAL_FORWARD_OBSERVATION_ONLY_NO_BROKER_ORDER` schema v1, first anchored candle start `2026-09-26T04:00:00+00:00`, latest anchored candle **start** `2026-09-29T03:00:00+00:00`, bootstrap SHA as above, `new_forward_observation_count: 0`, `latest_forward_observation: null`, `paper_order_submission: DISABLED`. Bootstrap outcome `BOOTSTRAPPED_HISTORY_ONLY_NO_RETROSPECTIVE_SIGNALS` confirms no past candle was claimed as an independently forward-observed result.
- The dedicated local SQLite journal is now bootstrapped. **DO NOT repeat `--bootstrap` for this database, overwrite previously captured CSVs, delete its journal, or run a retroactive catch-up.** No first new observation has yet been reported.

**Next owner action:** After the **next** UTC hour starts (for this journal: after `2026-09-29T05:03:00Z`, ideally before `05:20Z`), manually run `PYTHONPATH=src python -m signal_vault.forward_capture`. Confirm newly printed filename is `data/forward/captures/btcusd_72h_end_20260929T0500Z.csv` with latest fully closed bar at `05:00Z`. Immediately, within the **same UTC hour and 30 minutes of capture**, run `PYTHONPATH=src python -m signal_vault.forward_observer --observe --csv <EXACT_NEW_PRINTED_PATH>`, followed by `--status`. Expected first valid journal append: `ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE`, exactly **one** forward observation, newly observed candle start `04:00Z` and close `05:00Z`. If missed or freshness/overlap check fails, retain raw evidence and seek manual review; no backfilling. The command may not be replayed as a new observation. No scheduler has been installed.

## First real forward observation — owner-reported 2026-09-29 05:05:56 UTC

The operator ran the explicit GET-only `forward_capture` on the following UTC hour and locally retained its separate non-overwritten evidence pair:

- Fresh capture: `data/forward/captures/btcusd_72h_end_20260929T0500Z.csv` and `.csv.manifest.json`; owner-reported SHA-256 `af181756673f49c40e827b488ae79cdb7920abe8b1963ac724a80014b1ff3850`, 72 observed consecutive hourly candles spanning `2026-09-26T05:00Z` to exclusive close `2026-09-29T05:00Z`.
- The first attempted `--observe` before this capture existed failed with `regular captured CSV and nonsymlink manifest required`. The separate `--status` confirmed journal stayed safely at zero observations, with the original bootstrap anchor unchanged. The operator then correctly ran the capture **before** retrying observation.
- Successful owner-side command: `PYTHONPATH=src python -m signal_vault.forward_observer --observe --csv data/forward/captures/btcusd_72h_end_20260929T0500Z.csv`; immediately followed by `--status`. Both outputs agree: `outcome: ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE`, `new_forward_observation_count: 1`, latest anchored candle start `2026-09-29T04:00:00Z`, observed timestamp `2026-09-29T05:05:56.858452Z`, new candle `04:00–05:00Z`. Its recorded close was `83171.445` USD, past-only 6h return `-40.66337154102124642722340300` bps, 24h return `-34.99791226229893168934223400` bps, past-24h range `222.3368849729615735304346341` bps, and unchanged hypothetical round-trip break-even `70.30862370967018550890511000` bps.
- Output explicitly states `paper_order_submission: DISABLED`. This is real owner-captured **market observation**, not a broker fill, a demonstrated edge, a sealed independent validation outcome, a hypothetical trade, or an executed position. Raw CSVs, manifests and SQLite journal stay on the owner's Mac, Git-ignored. Never re-bootstrap or overwrite them.

**Next optional manual step:** for consecutive collection, after the next UTC close `2026-09-29T06:00Z`, capture at or after `06:03Z` using `forward_capture` and immediately `forward_observer --observe --csv <EXACT_NEW_CAPTURE_PATH>` then `--status`, both in the `06:00–07:00Z` clock hour and capture manifest younger than 30 minutes. Expected one new bar start `05:00Z`, close `06:00Z`, and journal observation count `2`. If missed, stop and do not pretend later history was observed prospectively; retain old journal and review creating a new segment. No automated scheduling or any broker order POST has been enabled.

## Phase 2K engineering — one operator command for next consecutive capture + append

After the owner's first valid 05:05:56Z journal append, an earlier failed attempt
had illustrated an operator error: calling `forward_observer --observe` before
the new CSV/manifest existed. Added **`src/signal_vault/manual_forward_cycle.py`** to avoid that two-command ordering problem. This tool is NOT RUNNING, not a daemon and not an approved trading execution path.

- One explicit `PYTHONPATH=src python -m signal_vault.manual_forward_cycle` call first opens the existing local `data/forward/observations.sqlite3` journal and checks its latest anchored hour, private mode and the exact next UTC close **without network or credentials**. It runs only between minute **03–24 UTC** within that next consecutive hour. If too early, late, missed, already captured, unbootstrapped or out of sequence, it fails before asking for hidden credentials.
- On a valid call, it prompts for existing PAPER **DATA** keys in local Terminal, uses the same strictly allowlisted BTC/USD historical `data.alpaca.markets` **GET** reader, writes the unique non-overwritten 72h CSV and SHA manifest, reloads and verifies them, and uses the **actual after-fetch clock** to atomically append exactly ONE new current-hour observation to the existing journal. Even if the data GET takes too long, it refuses retrospective/hindsight append.
- A local, nonblocking `RuntimeFileLock` prevents concurrent instances of this new manual command. SQLite transactional overlap comparison remains active against other operators. Once raw data capture succeeds, its files remain preserved even if observation processing fails; do not delete/rewrite them. Capture/journal file paths remain under Git-ignored `data/forward/`.
- For an intentionally separately initialized future contiguous segment, `manual_forward_cycle --db data/forward/observations-segment-02.sqlite3` is supported; it **requires** that segment to have already been freshly bootstrapped manually with `forward_observer --bootstrap --db ...`. The new tool cannot initialize, reset, merge or silently repair historical/missed periods.
- New synthetic/fake-provider tests cover single success, preflight rejection before provider GET, missed hours, duplicate, overlapping-data change preserving evidence, stale post-fetch clock, lock contention, custom segment isolation, and path traversal/symlinks. This is software validation, NOT proof of owner-side operation for the new CLI. GitHub CI in Python 3.11/3.12 is the regression gate.
- Documentation: `docs/FORWARD_OBSERVATIONS.md` and README. **GitHub Actions run `36525359113` succeeded on both Python 3.11 and 3.12: 271/271 offline tests passed, source head `2a85d72543dcda9df5d4a75f4908bea647f647e8`.** Tests also compile sources, verify live-mode refusal and reject live Alpaca trading host usage. v0.1/v0.2/v0.3 still failed and remain OFF. No extra crypto markets, broker paper POST, live orders, deposits, paid services, hourly background tasks or outside deployments were enabled.

**Next operator action:** Pull the latest source when convenient and inspect `forward_observer --status`. If the very next consecutive hour has not been missed, at UTC minute 03–24, manually run `PYTHONPATH=src python -m signal_vault.manual_forward_cycle` (existing journal by default), and send the output with credentials excluded. If even ONE expected hour was missed, this command will correctly refuse to append; preserve that journal and explicitly bootstrap an independent future segment after a new GET-only capture, then use `--db` for that segment. There is no need to stay awake just to keep the existing segment continuous.

## Phase 2L engineering — archived evidence check without modifying active journal

While the owner waits for the next consecutive UTC candle, added
`src/signal_vault/forward_evidence_audit.py`. This is a new **operator-invoked,
entirely OFFLINE, read-only** validator; it deliberately does NOT change the
already-bootstrapped `data/forward/observations.sqlite3` file or the existing
collection/strategy logic.

- `PYTHONPATH=src python -m signal_vault.forward_evidence_audit` audits the
  existing segment at any time; `--db data/forward/observations-segment-02.sqlite3`
  audits an explicitly different future segment. Both enforce only paths inside
  `data/forward/`, require source captures/manifests and journal to be regular
  owner-only 0600 files (not symlinks), open SQLite `mode=ro`/`query_only`
  and check `PRAGMA integrity_check` within a consistent read transaction.
- Reconstruct the initial genuine 72h bootstrap file by first journal start
  timestamp and compare original raw CSV SHA-256, manifest/source/UTC window
  and all 72 saved candle hashes. For each stored new forward observation,
  independently reread the uniquely timestamped original 72h local CSV and
  source-labelled manifest; verify captured/observed original chronology,
  overlap with every earlier anchored candle, no missing/reordered hourly
  segment, new bar identity, and exact saved close/prior 6h/prior 24h/
  24h range/cost calculations. Reconstructed hashes must exactly match the
  journal table (no extra or missing row).
- Unlike an ordinary `--observe`, the auditor checks archived capture
  timestamps against THEIR ORIGINAL UTC clock hour. It does not require a file
  to be fresh today, and it **cannot** turn past evidence into new prospective
  observations. No secrets, network GET, broker POST, order state, scheduling,
  new data capture, writing or sqlite schema migration are present.
- Its `PASS_INTERNAL_CONSISTENCY_ONLY` is **not** a cryptographic provider
  signature, independent attestation or sealed unseen performance test; the
  SHA manifests are local and unsigned and a privileged adversary could
  rewrite them with the database. The actual owner's local raw files and DB
  have NOT been accessed by the assistant. Owner can run the auditor locally
  after pulling.
- Added fake-capture regression tests for zero/one/two observation chains,
  missing/changed source, wrong manifest timestamps, journal feature and
  candle hash tampering, observation-clock changes, insecure/missing SQLite,
  isolated segments and read-only DB byte equality. After adding one
  additional zero-observation bootstrap-clock regression, **280/280 offline
  GitHub CI tests passed on both Python 3.11 and 3.12** at source commit
  `50cf792ef8c9e91d87a4c7c4779fbd39cb1027f4`, Actions run
  `36526054470`. The README, NEXT_STEPS and
  `docs/FORWARD_OBSERVATIONS.md` describe operator usage and limitations.

**Immediate clock-specific operation remains UNCHANGED:** if the next
consecutive hour of the owner's existing segment is still available,
at UTC minute 03–24 run
`PYTHONPATH=src python -m signal_vault.manual_forward_cycle`
on the already-pulled Phase 2K code. Phase 2L needs NO pull to make that
already-installed command work. If a consecutive UTC hour was missed, do
not backfill; preserve the old segment and explicitly fresh-bootstrap a
separate named one. Offline `forward_evidence_audit` is available after
pulling this new code and can be run even if the journal is now old.

## Phase 2M engineering — zero-credential next-hour readiness and evidence protection

Added `src/signal_vault/forward_readiness.py` as a deliberately
**offline, read-only, owner-invoked** readiness calculator to simplify
operating the existing 2K manual forward collector. It imports the Phase 2L
offline forensic auditor and requires the ENTIRE original capture/journal
chain to pass internal consistency before reporting next capture timing.
It then derives the single immediately next chronological UTC candle from
the journal's persisted last anchored bar START, requires the local system
clock not to predate the journal's last recorded observation, and prints
the exact upcoming UTC capture interval (minute `:03` through before `:25`).
No CLI backdate override is available.

The output distinguishes `WAIT_NEXT_HOURLY_CANDLE_TO_CLOSE`,
`WAIT_THREE_MINUTES_FOR_CANDLE_PUBLICATION`,
`READY_FOR_ONE_EXPLICIT_READ_ONLY_MANUAL_CYCLE`,
`CURRENT_CAPTURE_EXISTS_REVIEW_MANUAL_APPEND` (when an existing capture
and its manifest still pass fresh source/SHA validation),
`MANUAL_CAPTURE_START_WINDOW_CLOSED` and
`MISSED_CONSECUTIVE_HOUR_PRESERVE_SEGMENT`; unexpected symlinks,
partial/expired capture pairs, clock rollback and invalid archival evidence
also fail closed. In particular, it will not advise blindly rerunning the
one-command collector if the proper UTC-hour CSV filename is already in use;
an operator may instead review a still-current original capture and the
original manual `forward_observer --observe --csv <EXACT_PATH>` procedure.
This is NOT an order/trade readiness gate or independent Alpaca attestation.

Usage (only after pulling latest GitHub main):
`PYTHONPATH=src python -m signal_vault.forward_readiness`, or with
`--db data/forward/observations-segment-02.sqlite3` for an expressly
bootstrapped alternative. **It makes NO network requests, does not prompt
for PAPER credentials, does not mutate the journal or create/delete any
CSV, and neither waits nor schedules a future action**. Its real Mac
owner-side output has not yet been reported.

Added six focused synthetic tests for timing bounds, fresh existing capture
vs stale/incomplete/symlink pair, original SHA tampering, naive/rollback
clocks, alternate journal isolation, and missing journal without creation.
Corrected two test fixture/assertion issues detected by the first CI attempt;
**final corrected source CI 286/286 tests PASSED** on Python 3.11 and 3.12
at GitHub Actions run `36526615489`, source head
`30465b69ee8826ecf4fd2d79b7f838dafeffda7b`. Both jobs also compile,
check explicit live-mode refusal and forbid live Alpaca host references.
Updated `.gitignore` to exclude `*.egg-info/` generated by local editable
package installs (matching a harmless untracked folder the owner reported).
Operator docs: `docs/FORWARD_OBSERVATIONS.md`, README and NEXT_STEPS.

**Next owner collection action is unchanged:** the original first observation
closed `2026-09-29T05:00Z` and was recorded 05:05:56Z. If no intervening hour
is missed, the next single manual collector command remains
`PYTHONPATH=src python -m signal_vault.manual_forward_cycle`, only during
`2026-09-29T06:03:00Z` through before `06:25:00Z` (US Eastern
02:03–02:24:59). The optional new readiness check can be run before it, even
while waiting, but it cannot capture/append by itself. Do NOT run
`--bootstrap` on existing primary SQLite or rewrite existing evidence.
If the window is missed, preserve the segment and use a new manually
bootstrapped prospective segment rather than fabricate a catch-up.

## Phase 2K first real one-command owner test — 2026-09-29 06:03:59 UTC

After verifying GitHub Phase 2M was available on the Mac (the offline `forward_readiness` CLI produced `PASS_INTERNAL_CONSISTENCY_ONLY` and `WAIT_NEXT_HOURLY_CANDLE_TO_CLOSE` at `2026-09-29T05:37:11.619903Z`), the owner ran the NEW Phase 2K `PYTHONPATH=src python -m signal_vault.manual_forward_cycle` once in the proper next UTC hour, with local hidden Alpaca PAPER DATA credentials. The owner-supplied JSON reports:

- kind `ONE_MANUAL_READ_ONLY_CAPTURE_AND_FORWARD_OBSERVATION`;
- `capture_csv=data/forward/captures/btcusd_72h_end_20260929T0600Z.csv`, matching unique `.csv.manifest.json`, SHA-256 `a3561b7f7cd64c5f2cd0bb3c7f5d098223f0d47896208a88799fb5d935c2b91f`, 72 rows of closed hourly BTC/USD bars, exclusive capture end `2026-09-29T06:00:00Z`;
- journal's original bootstrap untouched: first bar start `2026-09-26T04:00:00Z`, original SHA `6e95c45d803d8ef5b575f9b40460ee80994526a3d44d37d47bb373b8ec034ab6`;
- **new forward observation count now 2**, latest anchored new bar `2026-09-29T05:00:00Z` through close `06:00:00Z`, recorded at `2026-09-29T06:03:59.085819Z`, outcome `ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE`;
- new recorded close `83391.026` USD, prior 6h return `-7.574690033723870710463603000` bps, prior 24h return `28.22226182633819622171923000` bps, prior 24h range `221.7514388178891095547859071` bps, fixed hypothetical round-trip break-even `70.30862370967018550890511000` bps;
- both `paper_order_submission` and `automatic_scheduling` explicitly `DISABLED`. This is local provider market-data observation only, NOT independent sealed validation, an order, actual fill or profit.

This is the **first owner-real/provider test of the one-command helper**, distinct from CI's fake-provider tests. The assistant has not directly opened the owner's raw CSV, manifest or SQLite bytes. Run the separately written `PYTHONPATH=src python -m signal_vault.forward_evidence_audit` offline on the Mac and inspect its JSON next; expected internal chain is original bootstrap + TWO unique observation-capture files (3 required CSV/manifest pairs, 74 total anchored unique bars), but do not claim that audit has passed on owner data before seeing its output. The extra early exploratory 03:00Z capture is retained but is NOT part of this bootstrap journal.

If voluntarily collecting a third consecutive hour, the NEXT manual one-command interval is after 2026-09-29T07:03Z and strictly before 07:25Z (03:03–03:24:59 EDT). Missing that window MUST NOT trigger backfill; preserve the two-observation journal and begin a separate explicit new segment in a later fresh hour only if the owner wishes to continue.

## Phase 2N engineering — source-preserving offline forward backup and isolated proof

The owner reported a successful first real `manual_forward_cycle` at
`2026-09-29T06:03:59.085819Z`. It created new closed 72h provider DATA GET
capture ending `06:00Z`, SHA
`a3561b7f7cd64c5f2cd0bb3c7f5d098223f0d47896208a88799fb5d935c2b91f`,
and advanced the existing original SQLite journal to TWO real chronological
forward observations with PAPER POST and automatic scheduling DISABLED. The
owner's earlier standalone `forward_readiness` succeeded against the
one-observation state at 05:37Z; the independent post-second-observation source
audit has been requested but its owner-local real-data result is not yet
received. Never claim a real successful independent two-observation forensic
audit before inspecting the new owner output.

Implemented **`src/signal_vault/forward_snapshot.py`**, a dedicated separate
backup for the *observation* journal and every local CSV/manifest actually
referenced by its SQLite snapshot (not the unrelated PAPER order ledger).
It is entirely offline and operator-invoked, OFF by default.

- A read-only full `forward_evidence_audit` of the ORIGINAL owner-local
  journal and all original referenced CSVs/manifests must PASS before staging.
  The tool opens SQLite in read-only mode and uses SQLite's online backup API
  to get a consistent isolated private database copy. The list of captures
  comes from that COPIED journal, avoiding falsely claiming unobserved raw
  files or missing a concurrently appended observation.
- Every original source CSV and original matching SHA manifest is copied to a
  NEW (not hardlinked) file under a private owner-only staging directory in
  `data/forward/backups/`, which remains Git-ignored and Mac-local.
  The archive is checked independently with the existing complete forensic
  auditor; it additionally publishes a local unsigned SHA manifest of all
  its own files, and a verification command refuses extra/missing files,
  altered SHA, symlink, bad mode, wrong chain/counter or nonowner directory.
  Completed snapshot is given a unique non-overwriting folder name; on
  failure staged output is cleaned but the ACTIVE source journal/captures
  are not touched.
- Commands after owner pulls new main: at any time first run
  `PYTHONPATH=src python -m signal_vault.forward_evidence_audit`, and ONLY
  after PASS, run `PYTHONPATH=src python -m signal_vault.forward_snapshot --create`.
  `--create` prints the generated local snapshot folder; owner may rerun
  offline proof with `PYTHONPATH=src python -m signal_vault.forward_snapshot
  --verify <EXACT_SNAPSHOT_FOLDER_BASENAME>`. Existing explicitly separated
  journals can be selected with `--create --db data/forward/<SEGMENT>.sqlite3`.
- This is an **ISOLATED VERIFICATION DRILL, not a production restore**.
  The snapshot utility has no restore-over-original operation, broker API
  client, scheduler, credentials or POST. Its SHA manifest is local and
  UNSIGNED, and the backup is UNENCRYPTED and on the SAME MAC. This does not
  prove third-party Alpaca source authentication or offsite disaster
  resilience; never commit/archive raw user files into GitHub.
- New fake-provider offline tests cover zero/one/two observation evidence
  chains, extra unlinked raw capture exclusion, DB source preservation,
  private folder/modes, named segment, tampering, partial source, path
  traversal, existing snapshot and nested/dangling symlinks.
  `docs/FORWARD_SNAPSHOTS.md` describes exact commands and caveats.

**Next developer gates:** review actual Mac output from owner-side independent
source auditor (expected two forward records and 3 capture/manifest pairs);
then request one local Phase 2N archive+verify JSON after latest pull.
Only then mark owner-specific Phase 2N successful. Continue offline scratch
transaction/recovery fault drills, genuine approved GET-only provider venue
rule/fee verification, and strategy preregistration separate from the
unseen reserve. There is NO authorization for PAPER POST, real trades, or
background hourly schedule. Do not promise the two-hour empirical sample
supports predictive edge or profitability.

## Owner's first real two-observation offline evidence audit — PASS, September 29 06:03 UTC source

Owner supplied a successful real local run of `PYTHONPATH=src python -m signal_vault.forward_evidence_audit` after the second authenticated operator-initiated read-only capture + journal append. Reported exact JSON key fields: `kind=OFFLINE_READ_ONLY_FORWARD_EVIDENCE_AUDIT`, `result=PASS_INTERNAL_CONSISTENCY_ONLY`, `bootstrap_anchored_bars=72`, `prospective_observations_verified=2`, `archived_csv_manifest_pairs_verified=3`, `last_anchored_bar_started_utc=2026-09-29T05:00:00+00:00`, `last_journal_recorded_utc=2026-09-29T06:03:59.085819+00:00`, `journal_path=data/forward/observations.sqlite3`, `journal_modified=false`, `network_requests=NONE`, `broker_order_submission=DISABLED`. This completes the owner-side local Phase 2L **internal evidence** check for the original journal with 2 actual prospective market-data observations and 3 archived matching original CSV/manifest pairs.

This is **NOT** third-party Alpaca signature/authentication, actual paper orders, fill performance, independent unseen model validation, or evidence of economic edge. Source CSVs and private SQLite remain only on the owner's Mac; assistant did not access the raw bytes.

Next immediate clock-specific manual capture if owner voluntarily wants a third consecutive hour: UTC 2026-09-29 07:03 to before 07:25 (EDT 03:03–03:24:59), using unchanged `PYTHONPATH=src python -m signal_vault.manual_forward_cycle`. Expected new unique 72h CSV ending 07:00Z, observation from 06:00–07:00Z, count 3. Do not recapture older hours or bootstrap existing DB. If owner chooses to stop/misses window, preserve 2-record journal and begin a different future segment only explicitly.

The newly built Phase 2N isolated archival snapshot utility is a separate opt-in local operation. After GitHub `main` head `89d351de68cdd4db31a26e15eced6c11378d7379` is pulled and no manual capture is underway, command `PYTHONPATH=src python -m signal_vault.forward_snapshot --create` should first audit local original evidence and generate private copied SQLite and original referenced CSV/manifest pairs, then run independent audit on the **snapshot** before publication. Owner real-data Phase 2N snapshot/verify has NOT yet run; request printed nonsecret JSON only, then optional `--verify <EXACT_SNAPSHOT_FOLDER_BASENAME>`. Avoid a Git pull while a time-sensitive local capture is underway.

## Third consecutive owner-side manual forward observation — 2026-09-29 07:04:29 UTC

Owner ran `PYTHONPATH=src python -m signal_vault.manual_forward_cycle` again in the next consecutive permitted UTC collection window, entering PAPER DATA keys invisibly on the local Mac. The returned JSON reports one fixed Alpaca BTC/USD read-only DATA GET 72h capture ending `2026-09-29T07:00:00+00:00`, local unique evidence `data/forward/captures/btcusd_72h_end_20260929T0700Z.csv` and its separate manifest, SHA-256 `5221971d2df7a87195a55b0eb31e238368edd9505109a5fc0ee130a8b869b8a6`. The existing original local observation journal still has its initial unmodified bootstrap `2026-09-26T04:00Z`, original SHA `6e95c45d803d8ef5b575f9b40460ee80994526a3d44d37d47bb373b8ec034ab6`, and now **new_forward_observation_count=3**, latest anchored bar start `2026-09-29T06:00:00Z`, latest close `07:00Z`, recorded at `07:04:29.648511Z`, outcome `ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE`.

Latest descriptive market observation: close `83973.21` USD; past 6h return `99.68016496596133775656035000` bps, past 24h return `101.0675603510302556728221200` bps, prior 24h high-low range `220.2140420736565864279810192` bps; unchanged fixed hypothetical round-trip break-even `70.30862370967018550890511000` bps. `paper_order_submission=DISABLED`, `automatic_scheduling=DISABLED`. Owner data only; assistant has not opened actual private raw CSV/SQLite files.

At this checkpoint, Phase 2L full offline audit **PASSED owner-side at count 2** (3 original archive pairs). The third record has not yet independently passed that forensic audit until the next owner-provided result. Requested `PYTHONPATH=src python -m signal_vault.forward_evidence_audit` immediately; success should show `prospective_observations_verified=3`, `archived_csv_manifest_pairs_verified=4`, `journal_modified=false`. Once owner confirms this, optional next Phase 2N real local snapshot validation after pulling latest GitHub code: `PYTHONPATH=src python -m signal_vault.forward_snapshot --create`, then `--verify <EXACT_NEW_SNAPSHOT_BASENAME>`. The backup remains same-device, unsigned, unencrypted and no restore over original is implemented.

The next consecutive manual capture window, ONLY if the owner chooses to maintain this segment, is after `2026-09-29T08:03:00Z` and before `08:25:00Z` (EDT 04:03–04:24:59). Do not introduce an automatic recorder, mislabel retrospectively backfilled bars, or invoke `--bootstrap` against the original journal. Three exploratory market observations cannot establish predictive edge or profitability.

## Owner-verified THIRD-observation forensic audit — PASS (2026-09-29)

Owner ran `PYTHONPATH=src python -m signal_vault.forward_evidence_audit` on the original local journal after the previously reported 07:00Z read-only capture. Original JSON reports `OFFLINE_READ_ONLY_FORWARD_EVIDENCE_AUDIT`, `PASS_INTERNAL_CONSISTENCY_ONLY`, 72 bootstrap anchors, `prospective_observations_verified=3`, `archived_csv_manifest_pairs_verified=4`, last anchored candle start `2026-09-29T06:00:00+00:00`, last observation at `2026-09-29T07:04:29.648511+00:00`, `journal_modified=false`, `network_requests=NONE`, `broker_order_submission=DISABLED`. This **now completes the real owner-side Phase 2L audit for 3 consecutive observations**. The owner pasted the same successful 07:00Z capture again alongside the NEW 3-record audit; this is not an extra or fourth observation.

**NEXT independent Phase 2N owner test (not yet performed):** once GitHub Desktop pulls the latest `main`, run `PYTHONPATH=src python -m signal_vault.forward_snapshot --create` manually on Mac (after captures complete). This first re-audits original source, makes a consistent SQLite copy and copies exactly four referenced CSV/manifest pairs (one bootstrap plus 3 observations) to a unique private Git-ignored `data/forward/backups/` directory, verifies the copied chain, and reports a fresh snapshot path. Do not upload raw data or backup bytes. Then verify using `PYTHONPATH=src python -m signal_vault.forward_snapshot --verify <EXACT_PRINTED_SNAPSHOT_BASENAME>`. Expected if no further observations before snapshot: `prospective_observations_verified=3`, `csv_manifest_pairs_verified=4`, `file_hashes_verified=9` (one SQLite copy plus 8 raw/manifest files). No network or broker POST. If another hour is appended before snapshot, derive expected counts from that new journal rather than treating 3 as fixed.

## Phase 2N first owner-real local evidence snapshot — CREATED and isolated verification PASSED

After the third consecutive owner read-only BTC/USD capture (newest candle 06:00–07:00Z, recorded `2026-09-29T07:04:29.648511Z`), owner executed `PYTHONPATH=src python -m signal_vault.forward_evidence_audit`. Real Mac result `PASS_INTERNAL_CONSISTENCY_ONLY`, 72 original bootstrap anchors, **3 prospective forward observations**, **4 complete archived CSV/manifest pairs**, `journal_modified=false`, zero network, no broker POST.

The owner then successfully invoked the NEW real-data Phase 2N `PYTHONPATH=src python -m signal_vault.forward_snapshot --create`. Operator-shared JSON confirms `kind=OFFLINE_FORWARD_SNAPSHOT_CREATED_AND_ISOLATED_VERIFIED`, `result=PASS_INTERNAL_CONSISTENCY_ONLY`, **3 observations verified, 4 CSV/manifest pairs verified, 9 file SHA-256 values verified**, original journal unmodified, no network requests, no broker orders, `snapshot_overwrite=DISABLED`. Newly published owner-local, Git-ignored snapshot path:
`data/forward/backups/forward_20260929T070754_619609Z`, with original journal `data/forward/observations.sqlite3`. The snapshot creation itself already included isolated verification, so this is **owner-real Phase 2N create-and-verify success** (not merely fake-provider CI).

Optional repeat verification entry point was requested but has **not yet been reported**:
```sh
PYTHONPATH=src python -m signal_vault.forward_snapshot --verify forward_20260929T070754_619609Z
```
It must never modify/replace the original journal, capture new candles or call Alpaca. This snapshot is on the **same Mac, local SHA manifest unsigned and copies unencrypted**, NOT an independently authenticated provider attestation, encrypted offsite backup, formal production restoration, paper fill record, trade signal or validated profit. Raw CSVs/SQLite were not uploaded to GitHub and assistant did not directly inspect their bytes.

Next phase (2O) should focus on a **separate scratch-only recovery and fault-injection drill**, with an explicit no-restore-over-original rule, and a consolidated offline operator coverage/incident summary that distinguishes missed-hour segments from proven continuous data. The main runtime's paper-order lifecycle and provider reconciliation also need exact fault tests against fakes; do not introduce broker POST, daemon deployment or new live permissions without explicit owner approval.

## Phase 2O — owner repeat snapshot verification PASS; scratch recovery drill built

The owner independently ran:
`PYTHONPATH=src python -m signal_vault.forward_snapshot --verify forward_20260929T070754_619609Z`
on the original owner-local Phase 2N backup. Shared JSON confirms
`OFFLINE_ISOLATED_FORWARD_SNAPSHOT_VERIFICATION`,
`PASS_INTERNAL_CONSISTENCY_ONLY`, **3** prospective observations,
**4** archived CSV/manifest pairs and **9** SHA-verified copied files,
`active_journal_modified=false`, `network_requests=NONE` and
`broker_order_submission=DISABLED`.
This is a successful real second check of the already-created owner-local
archive. It does NOT mean provider-authenticated, encrypted/offsite or production
restore; source/backup bytes remain on the owner's Mac, not in GitHub.

Added `src/signal_vault/forward_recovery_drill.py` plus offline synthetic
regression tests and `docs/FORWARD_RECOVERY_DRILL.md`. This Phase 2O
operator-invoked command takes ONLY the exact existing snapshot name, verifies
its original file inventory and source evidence, clones its files onto
independent scratch inodes under Git-ignored private
`data/forward/drills/`, proves the copied chain is independently readable,
and injects four negative cases exclusively in separate disposable clones:
modified CSV, changed source manifest, modified copied SQLite feature/anchor,
and removed copied source manifest. BOTH the local forensic auditor and outer
snapshot-manifest verifier MUST refuse each case. It then re-verifies the
clean scratch clone, checks all original snapshot bytes retained the identical
SHA fingerprint, and deletes all temporary evidence even on failure.

The drill refuses path traversal/symlinks, group/world-open directories,
corrupt initial snapshot, insufficient disk and failures undetected by either
verification layer. It never opens or restores over original
`data/forward/observations.sqlite3`, original capture evidence or
`data/forward/backups/<NAME>/` for writing; cannot call a broker, record a
new candle, create any trading action, enable scheduler or connect to network.
A 0600 lock file under local drills may remain after cleanup.

**CI on first complete code and test implementation:** 302 offline tests
passed on Python 3.11 and 3.12 at run `36535242811`; an additional
bootstrap-only source-fingerprint assertion also passed at run
`36535306539`. Operator's REAL backup has NOT yet been used for Phase 2O
scratch drill; its result must not be claimed until owner shares it.

**Next requested operator action:** after pulling latest GitHub `main`, run
`PYTHONPATH=src python -m signal_vault.forward_recovery_drill --snapshot forward_20260929T070754_619609Z`.
Expected for this known backup: 3 recovered forward observations, 4 source
capture pairs, 10 source snapshot file hashes including the local snapshot
manifest, four distinct scratch-fault scenarios rejected by BOTH layers,
complete disposable cleanup, and no active-journal interaction, network
request or order. This is a rehearsal using copies, NOT a restore.

## First REAL Phase 2O recovery and four-fault drill — OWNER PASS

The owner completed the previously pending operator-invoked
`PYTHONPATH=src python -m signal_vault.forward_recovery_drill --snapshot forward_20260929T070754_619609Z`
using the existing verified local Phase 2N backup. Owner-pasted JSON reports:

- `kind=OFFLINE_DISPOSABLE_FORWARD_RECOVERY_AND_FAULT_DRILL`,
  `result=PASS_ISOLATED_RECONSTRUCTION_AND_FAULT_REJECTION`;
- Reconstructed **3 prospective observation records** and **4 capture pairs**
  in isolated disposable copies; **10 snapshot files checked** (the 9 hashed
  copied evidence files plus `snapshot.manifest.json`);
- All four negative cases — `altered_csv`, `altered_source_manifest`,
  `altered_journal_metric`, `missing_capture_manifest` — each returned
  `REJECTED_BY_BOTH_INDEPENDENT_CHECKS`;
- `original_snapshot_file_hashes_unchanged=true`,
  `disposable_evidence_cleanup=COMPLETE`,
  `active_journal_opened_or_modified=false`,
  `snapshot_overwritten=false`,
  `network_requests=NONE`,
  `broker_order_submission=DISABLED`,
  `automatic_scheduling=DISABLED`.

The operator also independently reran
`PYTHONPATH=src python -m signal_vault.forward_snapshot --verify forward_20260929T070754_619609Z`
immediately beforehand, receiving `PASS_INTERNAL_CONSISTENCY_ONLY`,
three observations, four source pairs, nine hashed copied files, and no
active journal changes/network/orders. Both Phase 2N and Phase 2O are NOW
OWNER-VALIDATED, separate from earlier 302 synthetic CI safety checks.
These checks demonstrate reconstruction/internal corruption detection only,
NOT a real restore over any active journal, encrypted off-device backup,
signed Alpaca evidence, trading execution or economic returns.

**Next engineering milestone:** Phase 2P offline read-only operator evidence
coverage and incident report (segment starts/ends, no retrospective catch-up,
expected vs actual observation and archive pairs, integrity, latest capture
age/clock, backup verification status and explicit halted/missed-hour state).
It must not quietly merge separate observation segments or infer trades from
market returns. After that, conduct isolated PAPER-ledger UNKNOWN_RESULT,
duplicate/partial-fill and broker reconciliation fault tests against fake
providers; provider cost/venue constraints need separately authorized
read-only GET verification. Old EMA research versions v0.1/v0.2/v0.3 remain
FAILED/NOT PROMOTED. Real PAPER POST/live/hosting/paid services remain OFF.

## New authorization: unattended GET-only forward observer build, one-time MAC activation prepared

After repeatedly running real manual captures at 05:05Z, 06:03Z, 07:04Z,
independently auditing 3 forward hours, constructing/verifying the 3-record
4-pair local snapshot `forward_20260929T070754_619609Z`, and running the
first fully passing four-fault scratch-only Phase 2O recovery drill, the
owner asked to stop personally attending each hour and explicitly selected:

> Yes — build the unattended collector and prepare one-time Mac activation.

This is authorization to develop unattended **read-only BTC/USD DATA GET
observation** collection and to PREPARE owner-local activation only. It is NOT
permission for the assistant to install processes on the Mac without owner
running the installer, connect to cloud, send SMS/email, use paid services,
submit paper orders, open live trading, fund accounts, access finance/holdout
privately, or log/share credentials.

New `src/signal_vault/unattended_forward_cycle.py`:
- A **short-lived one-hour tick**, not a trading/order/strategy daemon,
  scheduler itself, background cloud task or real-portfolio executor.
- Scheduled minute `:07` after opt-in macOS LaunchAgent installation.
  Guard 03:00–24:59 UTC minutes; a late sleep/wakeup skips rather than
  retroactively claims history. Timing, unique file paths and existing
  evidence preflight occur BEFORE asking the owner-login Keychain for two
  explicitly named Alpaca PAPER DATA credential items.
- GET-only existing fixed Alpaca BTC/USD hourly historical-data allowlist
  with redirects refused. No broker orders/POST, LIVE credentials/host or
  generic-environment variable fallback; no passwords in command argv,
  .plist, receipt or stdout. Keychain read uses `/usr/bin/security
  find-generic-password ... -w` with capture_output and discards stderr.
- Starts a **SEPARATE new prospectively labeled**
  `data/forward/observations-auto-YYYYMMDDTHHMMZ.sqlite3` zero-forward-
  observation bootstrap. It NEVER resets or modifies the original,
  separately owner-verified `data/forward/observations.sqlite3` or original
  `data/forward/backups/forward_20260929T070754_619609Z` archive.
  Every following consecutive scheduled cycle audits existing journal/raw
  evidence, writes one unique 72h capture pair, appends exactly one new
  fully closed bar, then independently audits entire chain again. Atomic
  private `data/forward/automation/active_segment.json` is only a pointer;
  if an observational append succeeded before a pointer update/crash, actual
  audited SQLite truth takes precedence over stale pointer.
- If a closed hour was missed due to Mac sleep, shutdown or failed first
  attempt, it never reuses prior source/capture, retroactively backfills or
  silently merges. The next eligible cycle (ONLY if preceding original
  auto-segment passes full archival audit) creates a NEW nonoverwriting
  auto-bootstrap with zero forward observations, records previous segment
  and missed expected close, and preserves all old evidence. Invalid old
  journal or occupied current raw capture HALTS rather than hides evidence.
  Private nonsecret unique tick receipts, owner-only locks and offline
  `--status` report latest tick decision/failure class; no hourly
  notification service was installed.

New `src/signal_vault/mac_forward_agent.py`:
- Explicit owner `--preview` (NO installation), `--install`,
  `--status` and `--uninstall`. `--install` demands the checked-out repo's
  exact `.venv/bin/python`, existing owner login Keychain items and
  filesystem-safe paths, writes 0600 plist under
  `~/Library/LaunchAgents/com.signalvault.forwardobserver.plist`, then
  calls `/bin/launchctl bootstrap gui/<UID> <PLIST>` once. If activation
  fails, output states unloaded; it never incorrectly claims active.
- Plist contains only absolute source/Python paths, no secrets, `--once`,
  `StartCalendarInterval={Minute:7}`, `RunAtLoad=false`,
  `KeepAlive=false`, `Umask=077`, and private local log paths.
  macOS Keychain must be accessible in the logged-in user's session;
  late wakeups are skipped. `--uninstall` stops this label and removes
  its verified plist, NOT data, journals/backups or Keychain items.
- Two Keychain fields are created by the owner with separate interactive
  `security add-generic-password ... -U -w` commands, with `-w` the last
  flag and secret entered at the hidden prompt, never shell-history/argv.
  Do not use blanket Keychain `-A` grants. Full exact nonsecret procedure
  in `docs/UNATTENDED_FORWARD_COLLECTION.md`.

CI test modules `test_unattended_forward_cycle.py` and
`test_mac_forward_agent.py` exercise fake-provider 0/1/2 forward ticks,
no original manual-journal mutation, per-hour idempotence, missed-hour
segmentation, stale pointer recovery, corrupted evidence/path refusal,
late/sleep/time rollback and file collision, redacted Keychain, no generic
LIVE fallbacks, private receipts and offline latest status, safe plist
composition and explicit guarded one-time install/stop (mocked on Linux).
**A successful GitHub CI run is NOT an owner-real unattended Mac/Keychain
integration run.** Owner must Fetch/Pull latest repo, preview, interactively
enter PAPER DATA credentials into Keychain once, locally invoke
`PYTHONPATH=src python -m signal_vault.mac_forward_agent --install`,
verify `--status`, then check the first bootstrap (count zero) and first
following consecutive positive observation from local offline
`unattended_forward_cycle --status`. Until owner reports this, mark
Mac automatic collector NOT DEPLOYED/NOT VERIFIED.

Mac must remain powered on, logged in, awake and connected at local
minute `:07`; the logged-in Keychain must be accessible. The original
Phase 2O backup currently remains unsigned, same-device and unencrypted;
no external transport or production restore is being installed.

## Still NOT completed / mandatory blockers

1. Alpaca PAPER account, local read-only smoke, BTC/USD quote and asset-rule checks have been reported successful by the owner; reconfirm broker/provider readiness and fee/quote behavior before any separately authorized paper POST. Preserve local secret storage; never send secrets through chat/GitHub.
2. Genuine historical BTC/USD data was captured locally (see above). v0.1/v0.2/v0.3 remain negative/not promoted; v0.3 failed its explicit development gate and must not be evaluated on reserved post-gap data. **Latest completed owner checkpoint:** three genuine hourly forward-data observations (latest 07:04:29Z), complete forensic audit, standalone Phase 2N archive, repeat archive proof and Phase 2O scratch recovery/four-fault drill ALL PASS. No additional data capture is required to proceed to the next offline engineering phase. NEVER bootstrap the existing journal again. Optional next manual operation uses `PYTHONPATH=src python -m signal_vault.manual_forward_cycle`, which checks the precise consecutive UTC hour and either captures+observes safely or refuses missed-time catch-up. For missed hours, deliberately start a separate fresh segment without resetting old evidence; see `docs/FORWARD_OBSERVATIONS.md`. Do not share keys, backfill missed hours or enable background scheduling. See `docs/FORWARD_OBSERVATIONS.md`. Review costs and preregister a materially different, lower-turnover hypothesis only after sufficient independent thinking/evidence. There is NO authorization for paper POST, live trading or ML shadow promotion.
3. Complete transaction-integrity and restoration drills, an actual PostgreSQL Python port + PG concurrency tests or a separately reviewed single-host SQLite pilot acceptance. No multi-host execution against SQLite.
4. Separately authorized hosting, hardened service configuration and notifications. No services have been installed.
5. Actual broker PAPER execution with provider-confirmed order/fill/fee/cash/position reconciliation, at least seven days uninterrupted operation and incident review. Simulation result is not evidence of sustainable gains.
6. Live connector requires NEW owner decision, separate reviewed service/credentials, no withdrawal permissions and no automatic additional funding. No live code path exists.

## Resume procedure

Read GitHub `PROJECT_STATUS.md`, `NEXT_STEPS.md`, `ARCHITECTURE.md`, `docs/POSTGRES_PAPER_LEDGER.md`, `docs/OPERATOR_MONITOR.md`. Verify current remote head/tree, run `make test`, `make compile`, `make demo`; continue only PAPER development. All transactions and results must remain classified by real provider-paper vs offline synthetic vs genuine live (none). Create and verify a GitHub/Library exact-tree checkpoint before a session ends. Nothing runs in the background merely because the ChatGPT conversation is idle.
