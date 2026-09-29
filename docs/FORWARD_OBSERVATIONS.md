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
the same current capture produces an idempotent no-op. A captured candle may
not be open/future, stale by more than 90 minutes, or obtained from a manifest
over 30 minutes old. The incoming rolling capture must contain at least 29
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
