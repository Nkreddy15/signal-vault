"""Purely OFFLINE, READ-ONLY forensic check of prospective BTC/USD evidence.

Inspects the archived original 72h CSV/manifest and each subsequent capture
against the owner-local SQLite hashes and derived recorded features.
Does NOT connect to a provider, refresh timestamps, append observations,
make order suggestions or claim third-party cryptographic authentication.

This checks internal consistency. SHA manifests are not independently signed,
and a sufficiently privileged actor could rewrite both data and metadata.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from .forward_observer import SCHEMA_VERSION, _bar_sha256
from .market_data import Bar, parse_bar, utc_timestamp, validate_bars
from .research_economics import break_even_price_move_bps

WINDOW_HOURS = 72
MAX_CSV_BYTES = 1_000_000
MAX_MANIFEST_BYTES = 4096
HOUR = timedelta(hours=1)
CAPTURE_KEYS = {
    "schema_version", "symbol", "timeframe", "source", "start_utc",
    "end_utc", "row_count", "csv_sha256", "captured_utc",
}


def _private_regular(path: Path, name: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(name + " must be an existing nonsymlink regular file")
    if path.stat().st_mode & 0o077:
        raise PermissionError(name + " must be owner-only (0600)")


def _archive_path(root: Path, closed: datetime) -> Path:
    if closed.tzinfo != timezone.utc or closed.minute or closed.second or closed.microsecond:
        raise ValueError("archived capture boundary must align to UTC hour")
    return root / "captures" / f"btcusd_72h_end_{closed:%Y%m%dT%H%MZ}.csv"


def _archived_capture(root: Path, *, closed: datetime,
                      expected_sha: str) -> tuple[tuple[Bar, ...], datetime]:
    """Recheck immutable source-labelled archived evidence, WITHOUT freshness cutoff."""
    target = _archive_path(root, closed)
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    _private_regular(target, "archived CSV " + target.name)
    _private_regular(manifest_path, "archived manifest " + target.name)
    if target.stat().st_size > MAX_CSV_BYTES or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("unexpectedly large archived capture or manifest")
    raw = target.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != expected_sha:
        raise ValueError("archived CSV SHA mismatch: " + target.name)
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("archived capture manifest is invalid: " + target.name) from exc
    if (not isinstance(metadata, dict) or set(metadata) != CAPTURE_KEYS
            or type(metadata["schema_version"]) is not int
            or metadata["schema_version"] != 1
            or metadata["symbol"] != "BTC/USD"
            or metadata["timeframe"] != "1Hour"
            or metadata["source"] != "alpaca_crypto_us"
            or metadata["csv_sha256"] != digest
            or type(metadata["row_count"]) is not int
            or metadata["row_count"] != WINDOW_HOURS
            or metadata["start_utc"] != (closed-timedelta(hours=WINDOW_HOURS)).isoformat()
            or metadata["end_utc"] != closed.isoformat()):
        raise ValueError("archived manifest provenance or boundaries mismatch: " + target.name)
    captured = utc_timestamp(metadata["captured_utc"])
    if not closed + timedelta(minutes=3) <= captured < closed + HOUR:
        raise ValueError("archived capture timestamp outside original allowed UTC hour")
    try:
        stream = io.StringIO(raw.decode("utf-8"), newline="")
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["timestamp", "open", "high", "low", "close", "volume"]:
            raise ValueError("unexpected archival CSV header")
        rows = tuple(parse_bar(row, source="alpaca_crypto_us") for row in reader)
        bars = validate_bars(rows, as_of=closed, min_count=WINDOW_HOURS)
    except (UnicodeError, csv.Error, TypeError) as exc:
        raise ValueError("archived capture CSV cannot be parsed: " + target.name) from exc
    if (len(bars) != WINDOW_HOURS or bars[0].start != closed-timedelta(hours=WINDOW_HOURS)
            or bars[-1].close_time != closed):
        raise ValueError("archived hourly capture is incomplete: " + target.name)
    return bars, captured


def _closed_utc(stamp: str, *, name: str) -> datetime:
    parsed = utc_timestamp(stamp)
    if (parsed.minute or parsed.second or parsed.microsecond
            or stamp != parsed.isoformat()):
        raise ValueError(name + " is not a canonical UTC-hour timestamp")
    return parsed


def _utc_stamp(stamp: str, *, name: str) -> datetime:
    parsed = utc_timestamp(stamp)
    if stamp != parsed.isoformat():
        raise ValueError(name + " is not a canonical UTC timestamp")
    return parsed


def audit_forward_evidence(*, root: str | Path = "data/forward",
                           db: str | Path | None = None) -> dict:
    """Audit owner's existing captured files + original or named journal read-only.

    Intended for a local operator. Requires standard capture naming generated
    by forward_capture/manual_forward_cycle, so no research/holdout files can
    accidentally be silently treated as forward-source evidence.
    """
    base = Path(root).expanduser()
    if base.is_symlink() or not base.is_dir() or (base/"captures").is_symlink():
        raise ValueError("forward root and capture directory must not be symlinked")
    if not (base/"captures").is_dir():
        raise ValueError("forward capture directory is missing")
    chosen = base / "observations.sqlite3" if db is None else Path(db).expanduser()
    if not chosen.resolve().is_relative_to(base.resolve()):
        raise ValueError("journal path must remain within data/forward")
    _private_regular(chosen, "forward SQLite journal")

    # URI mode=ro plus query_only prevents accidentally creating/reseting the
    # operator's existing SQLite file. BEGIN holds a consistent read snapshot.
    connection = sqlite3.connect(chosen.resolve().as_uri()+"?mode=ro", uri=True,
                                 isolation_level=None, timeout=3)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        check = [r[0] for r in connection.execute("PRAGMA integrity_check")]
        if check != ["ok"]:
            raise ValueError("SQLite integrity_check failed")
        states = connection.execute(
            "SELECT schema_version,first_start,last_start,last_seen_utc,bootstrap_sha256 "
            "FROM forward_state").fetchall()
        if len(states) != 1:
            raise ValueError("forward state must have exactly one bootstrapped row")
        version, first_text, last_text, last_seen_text, bootstrap_sha = states[0]
        if version != SCHEMA_VERSION:
            raise ValueError("unsupported forward journal schema")
        first = _closed_utc(first_text, name="bootstrap first bar start")
        last = _closed_utc(last_text, name="latest anchored bar start")
        last_seen = _utc_stamp(last_seen_text, name="last journal observation clock")
        bootstrap_close = first + timedelta(hours=WINDOW_HOURS)
        bootstrap_bars, bootstrap_captured = _archived_capture(
            base, closed=bootstrap_close, expected_sha=bootstrap_sha)
        if bootstrap_bars[0].start != first:
            raise ValueError("bootstrap archive disagrees with journal first bar")
        if bootstrap_captured > last_seen:
            raise ValueError("bootstrap capture timestamp occurs after journal observation clock")

        anchored: dict[str, tuple[str, str]] = {
            bar.start.isoformat(): (bar.close_time.isoformat(), _bar_sha256(bar))
            for bar in bootstrap_bars
        }
        previous_start = bootstrap_bars[-1].start
        previous_clock = bootstrap_captured

        records = connection.execute(
            "SELECT start_utc,close_utc,observed_utc,captured_csv_sha256,close_usd,"
            "prior_6h_return_bps,prior_24h_return_bps,prior_24h_range_bps,"
            "modeled_round_trip_break_even_bps FROM forward_observations "
            "ORDER BY start_utc ASC").fetchall()
        if last != previous_start + len(records)*HOUR:
            raise ValueError("latest journal anchor and observation count disagree")
        for row in records:
            (start_text, close_text, observed_text, stored_sha, close_usd,
             six_bps, day_bps, range_bps, hurdle_bps) = row
            start = _closed_utc(start_text, name="observation start")
            closed = _closed_utc(close_text, name="observation close")
            observed = _utc_stamp(observed_text, name="observation timestamp")
            if start != previous_start + HOUR or closed != start + HOUR:
                raise ValueError("missing, reordered or incorrectly timed journal observation")
            if (observed < closed or observed.replace(minute=0, second=0, microsecond=0) != closed
                    or observed < previous_clock):
                raise ValueError("journal observation is retrospective, future or out of order")
            bars, captured = _archived_capture(base, closed=closed, expected_sha=stored_sha)
            if (not closed + timedelta(minutes=3) <= captured <= observed
                    or observed - captured > timedelta(minutes=30)):
                raise ValueError("captured/observed timestamps violate prospective freshness")
            older = [bar for bar in bars if bar.start <= previous_start]
            if len(older) < 29 or older[-1].start != previous_start:
                raise ValueError("archived rolling capture has inadequate anchor overlap")
            for bar in older:
                if anchored.get(bar.start.isoformat()) != (
                        bar.close_time.isoformat(), _bar_sha256(bar)):
                    raise ValueError("archived overlapping candle disagrees with initial evidence")
            new_bar = bars[-1]
            if new_bar.start != start:
                raise ValueError("last bar is not the newly observed hourly candle")
            close = new_bar.close
            computed = (
                close,
                ((close / bars[-7].close)-Decimal("1"))*Decimal("10000"),
                ((close / bars[-25].close)-Decimal("1"))*Decimal("10000"),
                (max(b.high for b in bars[-24:])-min(b.low for b in bars[-24:]))
                / close * Decimal("10000"),
                break_even_price_move_bps(),
            )
            try:
                saved = tuple(Decimal(str(v)) for v in (
                    close_usd, six_bps, day_bps, range_bps, hurdle_bps))
            except Exception as exc:
                raise ValueError("invalid stored numeric observation") from exc
            if saved != computed:
                raise ValueError("stored observation features differ from independently recomputed CSV")
            anchored[new_bar.start.isoformat()] = (
                new_bar.close_time.isoformat(), _bar_sha256(new_bar))
            previous_start = start
            previous_clock = observed

        if records and last_seen != previous_clock:
            raise ValueError("journal last_seen differs from newest observation timestamp")
        if not records and (
                last_seen.replace(minute=0, second=0, microsecond=0) != bootstrap_close
                or last_seen < bootstrap_captured
                or last_seen - bootstrap_captured > timedelta(minutes=30)):
            raise ValueError("bootstrap observation clock disagrees with original archive timing")
        sql_anchors = connection.execute(
            "SELECT start_utc,close_utc,bar_sha256 FROM captured_bar_hashes").fetchall()
        observed_anchors = {s: (c, h) for s, c, h in sql_anchors}
        if (len(sql_anchors) != len(observed_anchors)
                or observed_anchors != anchored or last != previous_start):
            raise ValueError("journal anchored candle hashes disagree with archived captures")
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return {
        "kind": "OFFLINE_READ_ONLY_FORWARD_EVIDENCE_AUDIT",
        "result": "PASS_INTERNAL_CONSISTENCY_ONLY",
        "bootstrap_anchored_bars": WINDOW_HOURS,
        "prospective_observations_verified": len(records),
        "archived_csv_manifest_pairs_verified": 1 + len(records),
        "last_anchored_bar_started_utc": previous_start.isoformat(),
        "last_journal_recorded_utc": last_seen.isoformat(),
        "journal_path": str(chosen),
        "journal_modified": False,
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
        "warning": "Unsigned local evidence only; a consistency pass does not independently authenticate provider data or prove trading performance.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline READ-ONLY verification of saved forward CSVs, SHA manifests and SQLite journal")
    parser.add_argument("--db", default=None,
                        help="Existing SQLite journal under data/forward/ (default: observations.sqlite3)")
    args = parser.parse_args()
    print(json.dumps(audit_forward_evidence(db=args.db), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
