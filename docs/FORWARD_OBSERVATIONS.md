# Read-only forward observation — local manual MVP

**Status: IMPLEMENTED AND OFF BY DEFAULT. No scheduler, model promotion,
broker paper order, live order, deposits, hosting or payments.**

This phase follows the failed fixed v0.1/v0.2/v0.3 research gates in
`docs/RESEARCH_V02.md`, `docs/RESEARCH_V03.md`. The March 12 missing hour and
reserved post-gap historic data remain untouched. The new tool begins from a
**fresh UTC-hour local market-data capture**, not from any historical backtest
file. It does not choose BUY/SELL, calculate gains from hypothetical positions,
or record provider trade fills.

## First: exact $15 economic sensitivity, entirely offline

```sh
PYTHONPATH=src python -m signal_vault.research_economics
```

It computes the hypothetical BUY/SELL price-change hurdle using the exact
existing backtest order arithmetic, with modeled 25 bps fee **per side** and
10 bps adverse slippage **per side**; it also reports fixed reference-price
move scenarios with and without costs. The account's true fee tier, bid/ask
spread, real order-book execution and liquidity are **not verified** by this
calculator. Do not change the assumed notional or implement a new strategy just
because one sensitivity cell is positive.

## Owner's first exact cost-audit result (2026-09-28 US Eastern / September 29 UTC)

The owner ran `PYTHONPATH=src python -m signal_vault.research_economics` after syncing GitHub head `3ad835ecfcf80a0d4acb8ca3cf04bea3e2ead373`. It returned the expected `OFFLINE_HYPOTHETICAL_SMALL_NOTIONAL_COST_AUDIT` with `broker_order_submission=DISABLED` and the fixed existing assumptions:

| Reference-price rise during $15 BTC hypothetical buy/sell cycle | Net modeled P&L after costs |
|---|---:|
| 0 bps (flat BTC price) | -$0.1047266171 |
| +25 bps (+0.25%) | -$0.0674884337 |
| +50 bps (+0.50%) | -$0.0302502502 |
| +75 bps (+0.75%) | +$0.0069879332 |
| +100 bps (+1.00%) | +$0.0442261167 |
| +150 bps (+1.50%) | +$0.1187024836 |
| +200 bps (+2.00%) | +$0.1931788505 |

The exact model break-even **reference-to-reference** price move is `70.30862370967018550890511000` bps, or approximately **+0.7031%**. A flat-price round trip loses approximately $0.1047 because of the assumed two-sided costs, versus exactly $0 in the hypothetical zero-cost control. The arithmetic matches `backtest.py`; it does NOT verify the user's actual Alpaca fee tier, bid/ask spread, order-book depth or future slippage. `v0.3` also lost money at zero cost; fewer trades is not, by itself, proof of a predictive edge. Do not create a guessed profitability target, threshold sweep or automatic BUY instruction from this report.

## Manual fresh-data procedure (only when explicitly requested by the owner)

Run `forward_capture` **after at least three minutes past an exact UTC
hour**. It prompts invisibly in local Terminal for Alpaca PAPER data keys
(never paste them into Git, a screenshot or chat). The only network action is
an allowlisted fixed HTTPS BTC/USD historical-data **GET**, with redirects
refused; it reads the preceding **72 completed hourly candles**. The underlying
`capture_dataset` requires exact full hourly coverage, writes source-labelled
CSV and SHA-256 manifest with 0600 permissions, and fails rather than repairing
missing provider observations. Captures are saved to distinct, never-overwritten
`data/forward/captures/btcusd_72h_end_YYYYMMDDTHHMMZ.csv` paths. These data,
manifests and the SQLite journal are all ignored by Git.

```sh
PYTHONPATH=src python -m signal_vault.forward_capture
```

Copy the exact `csv` path printed by that command. On **first use only**:

```sh
PYTHONPATH=src python -m signal_vault.forward_observer --bootstrap --csv data/forward/captures/<EXACT_PRINTED_FILENAME>.csv
```

Bootstrap requires a valid, fresh manifest and at least 30 continuous closed
candles. It anchors their hashes and latest timestamp but records **ZERO**
retrospective observations; it cannot relabel known history as forward results.
The first SQLite journal is `data/forward/observations.sqlite3`, mode 0600.

After the **next** UTC-hour close (again wait at least three minutes), run
`forward_capture` a second time. It produces a new never-overwritten CSV and
manifest. Use that new path with:

```sh
PYTHONPATH=src python -m signal_vault.forward_observer --observe --csv data/forward/captures/<NEW_EXACT_PRINTED_FILENAME>.csv
PYTHONPATH=src python -m signal_vault.forward_observer --status
```

A successful observation adds **exactly one** fully closed, fresh new hour to
a transactional journal, with last close, prior 6h/24h return, prior 24h
range and the unchanged hypothetical break-even cost. It is labelled
`ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE`; no order intent is created. Replaying
the same current capture produces an idempotent no-op. A captured candle must
have closed at the **start of the current UTC clock hour** (so run the capture
and immediately bootstrap/observe during that same hour, after minute 03),
must not be open/future, and must be backed by a manifest less than 30
minutes old. This prevents late historical candles from being relabelled as
prospective observations. The incoming rolling capture must contain at least 29
previously hashed overlapping candles and include the exact latest anchored
bar. Any historical mutation, reordering, missing hour, multiple hours of
unobserved catch-up, symlink/path escape, invalid manifest, CSV fingerprint
change or clock rollback blocks the append without advancing state.

**If an observation hour is missed, the software refuses hindsight catch-up.**
Keep the existing journal and all raw evidence unchanged; review the incident.
If the owner explicitly wants a new prospective segment, after capturing a
fresh 72-hour window, start it using `--bootstrap --db
data/forward/observations-segment-02.sqlite3 --csv <NEW_FILE>`. Do not delete
or reset the earlier journal.

This is **exploratory prospective data**, not an independently sealed
unobserved holdout once its features are inspected to develop a new model.
Before independently validating a future strategy, preregister a separate,
time-bounded period and freeze the candidate/code/cost assumptions first.

## Phase 2K: safer ONE-command manual continuation (no scheduling)

The owner verified the first real hourly journal append: 72-hour GET-only capture
`btcusd_72h_end_20260929T0500Z.csv` (SHA-256
`af181756673f49c40e827b488ae79cdb7920abe8b1963ac724a80014b1ff3850`),
followed by `--observe` at `2026-09-29T05:05:56.858452Z`. Two status
responses agreed: exactly **ONE new forward observation**, bar 04:00–05:00Z,
close $83,171.445, no broker order.

A former manual attempt called `--observe` *before* creating its new CSV,
which correctly failed with `regular captured CSV and nonsymlink manifest
required` and did not alter the journal. To eliminate that ordering mistake,
the newly added command below does BOTH actions in one invocation, using the
already-bootstrapped `data/forward/observations.sqlite3` journal:

```sh
# Only during the NEXT consecutive UTC hour, between minute :03 and :24:
PYTHONPATH=src python -m signal_vault.manual_forward_cycle
```

**Do not run this at arbitrary times:** it preflights the existing journal
**before asking for credentials**, and refuses if the next hourly candle
hasn't closed, if a consecutive capture hour was missed, if a capture for the
hour already exists, or if the journal is missing. It prints the eligible
closed-hour boundary and target path. It then uses the local hidden PAPER DATA
keys for the same allowlisted BTC/USD historical-data **GET only**, creates
the unique non-overwritten 72h CSV + manifest, validates the new capture
and 29+ immutable previous candles, and commits **exactly one** new
observation atomically. It uses the actual time AFTER fetching (not the
pre-fetch time) for final freshness validation; if the fetch is slow or
crosses the hour, the journal cannot mislabel the result.

This command has a local nonblocking file lock to refuse simultaneous
instances of the *manual cycle*. It does not replace the main journal's
SQLite transaction checks if a separate manual operator is active. If an
append fails after data capture, the existing raw CSV and manifest remain
on disk. Do **not** rerun the capture or delete the journal; inspect
`forward_observer --status`, and only if the existing captured file is
still fresh/current may you use the original two-step
`forward_observer --observe --csv <EXACT_OLD_CAPTURE_PATH>` for recovery.

**If a consecutive hour is missed**, this one-command tool deliberately
stops; it never backfills or silently resets the main database. An operator
can explicitly begin a separate future segment without altering the old one:

```sh
# At minute :03 or later in a fresh UTC hour, first create a new real capture:
PYTHONPATH=src python -m signal_vault.forward_capture

# Substitute the EXACT new CSV printed, not an earlier existing capture:
PYTHONPATH=src python -m signal_vault.forward_observer --bootstrap \
  --db data/forward/observations-segment-02.sqlite3 \
  --csv data/forward/captures/<EXACT_NEW_FILE>.csv

# In the following consecutive UTC hour (minute :03 through :24):
PYTHONPATH=src python -m signal_vault.manual_forward_cycle \
  --db data/forward/observations-segment-02.sqlite3
```

A new segment's bootstrap always has ZERO newly forward-observed bars. The
`--db` argument must identify an **existing, privately permissioned,
explicitly bootstrapped** SQLite file *within* `data/forward/`; the one-command
tool does not create or reset it. Retain the old segment and every old raw
capture. Neither a reopened segment nor an inspected forward record is an
unseen model holdout. No daemon, cron, hosted endpoint or broker account order
action is introduced by this usability improvement.

## Security and scope

- No background scheduler/daemon is installed or launched. The operator runs
  explicit commands manually; closing ChatGPT does not leave a recorder active.
- `forward_observer` has no network/credentials and does not import the
  execution modules. It only reads fresh local source-attributed captures and
  writes a dedicated observational SQLite file under `data/forward/`.
- Paper and live order submission remain **DISABLED**. The fixed `/v2/orders`
  provider host is never used in this workflow.
- Actual account-specific cost/venue rules require separately reviewed
  authenticated GET verification before interpreting any eventual performance.
