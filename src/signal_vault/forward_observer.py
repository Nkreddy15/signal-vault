"""Fail-closed, local, prospective BTC/USD OBSERVATION journal.

This does NOT make a trade decision, call a broker or backfill missed hours.
Bootstrap anchors fresh, authentic-looking READ-only provider-capture evidence
without creating forward observations. Every subsequent invocation must supply
a new fully closed contiguous hourly provider capture; one bar is appended
transactionally only if it was observed while still fresh.

The journal is exploratory development data, NOT an untouched validation set.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Sequence

from .market_data import Bar, load_csv, utc_timestamp, validate_bars
from .research_economics import break_even_price_move_bps

SCHEMA_VERSION = 1
MIN_OVERLAP = 29
MAX_BAR_AGE = timedelta(minutes=90)
MAX_CAPTURE_AGE = timedelta(minutes=30)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observation timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_number(value: Decimal) -> str:
    # String-only normalization never rounds high-precision Decimal values.
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if value == 0 else rendered


def _bar_sha256(bar: Bar) -> str:
    # Canonicalize numerical values so harmless provider formatting (100/100.0)
    # does not invalidate an otherwise identical previously captured candle.
    fields = [bar.start.isoformat()] + [
        _canonical_number(getattr(bar, name))
        for name in ("open", "high", "low", "close", "volume")
    ]
    return sha256(json.dumps(fields, separators=(",", ":")).encode("utf-8")).hexdigest()


def read_verified_capture(csv_file: str | Path, *, observed_at: datetime
                          ) -> tuple[tuple[Bar, ...], str]:
    """Require the atomic CSV + SHA/UTC/source manifest from data_capture.py.

    This check establishes internal capture provenance and integrity; it cannot
    independently authenticate the provider or turn paper data into live fills.
    """
    now = _require_utc(observed_at)
    path = Path(csv_file)
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    if not path.is_file() or not manifest_path.is_file() or path.is_symlink() or manifest_path.is_symlink():
        raise ValueError("regular captured CSV and nonsymlink manifest required")
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("invalid read-only capture manifest") from exc
    if not isinstance(manifest, dict):
        raise ValueError("invalid capture manifest object")
    required = {
        "schema_version", "symbol", "timeframe", "source", "start_utc",
        "end_utc", "row_count", "csv_sha256", "captured_utc",
    }
    if (set(manifest) != required or type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1 or manifest["symbol"] != "BTC/USD"
            or manifest["timeframe"] != "1Hour" or manifest["source"] != "alpaca_crypto_us"
            or manifest["csv_sha256"] != digest or type(manifest["row_count"]) is not int
            or manifest["row_count"] < MIN_OVERLAP + 1):
        raise ValueError("capture provenance or SHA-256 mismatch")
    stamped = utc_timestamp(manifest["captured_utc"])
    bars = load_csv(path, as_of=now, min_count=MIN_OVERLAP + 1)
    if (manifest["row_count"] != len(bars)
            or manifest["start_utc"] != bars[0].start.isoformat()
            or manifest["end_utc"] != bars[-1].close_time.isoformat()):
        raise ValueError("capture manifest boundaries/row count mismatch")
    if (stamped < bars[-1].close_time or stamped > now + timedelta(seconds=2)
            or now - stamped > MAX_CAPTURE_AGE):
        raise ValueError("read-only capture manifest is stale, premature or future-dated")
    return bars, digest


def _fresh_closed_sequence(bars: Sequence[Bar], now: datetime) -> tuple[Bar, ...]:
    sequence = validate_bars(bars, as_of=now, min_count=MIN_OVERLAP + 1)
    age = now - sequence[-1].close_time
    if age < timedelta(0) or age > MAX_BAR_AGE:
        raise ValueError("latest fully closed hourly bar is stale or future-dated")
    return sequence


class ForwardObservationJournal:
    """Owner-only SQLite journal; bootstrap and observation commits are atomic.

    Only previously *captured* OHLCV hashes and inert feature observations can
    be stored. No order intents, paper portfolio, keys, network calls or POST.
    """

    def __init__(self, path: str | Path, *, initialize: bool = False):
        self.path = Path(path)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ValueError("forward database must be a regular nonsymlink file")
        if self.path.exists() and self.path.stat().st_mode & 0o077:
            raise PermissionError("forward journal must not be readable or writable by group/others (0600)")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            # No overwrite/reset: old prospective evidence must stay immutable.
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        elif not self.path.is_file():
            raise ValueError("forward journal missing: explicit --bootstrap required")
        self.connection = sqlite3.connect(str(self.path), isolation_level=None, timeout=3)
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS forward_state(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                schema_version INTEGER NOT NULL,
                first_start TEXT NOT NULL,
                last_start TEXT NOT NULL,
                last_seen_utc TEXT NOT NULL,
                bootstrap_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS captured_bar_hashes(
                start_utc TEXT PRIMARY KEY,
                close_utc TEXT NOT NULL,
                bar_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS forward_observations(
                start_utc TEXT PRIMARY KEY,
                close_utc TEXT NOT NULL,
                observed_utc TEXT NOT NULL,
                captured_csv_sha256 TEXT NOT NULL,
                close_usd TEXT NOT NULL,
                prior_6h_return_bps TEXT NOT NULL,
                prior_24h_return_bps TEXT NOT NULL,
                prior_24h_range_bps TEXT NOT NULL,
                modeled_round_trip_break_even_bps TEXT NOT NULL
            );
        """)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.connection.close()

    def status(self) -> dict:
        state = self.connection.execute(
            "SELECT schema_version,first_start,last_start,last_seen_utc,bootstrap_sha256 "
            "FROM forward_state WHERE singleton=1").fetchone()
        if state is None:
            raise ValueError("forward journal has not been bootstrapped")
        if state[0] != SCHEMA_VERSION:
            raise ValueError("unsupported forward journal schema")
        count = self.connection.execute(
            "SELECT COUNT(*) FROM forward_observations").fetchone()[0]
        last = self.connection.execute(
            "SELECT start_utc,close_utc,observed_utc,close_usd,prior_6h_return_bps,"
            "prior_24h_return_bps,prior_24h_range_bps,modeled_round_trip_break_even_bps "
            "FROM forward_observations ORDER BY start_utc DESC LIMIT 1").fetchone()
        keys = ("bar_started_utc", "bar_closed_utc", "observed_utc", "close_usd",
                "prior_6h_return_bps", "prior_24h_return_bps", "prior_24h_range_bps",
                "modeled_round_trip_break_even_bps")
        return {
            "kind": "LOCAL_FORWARD_OBSERVATION_ONLY_NO_BROKER_ORDER",
            "schema_version": state[0],
            "bootstrap_first_bar_utc": state[1],
            "latest_anchored_bar_start_utc": state[2],
            "last_seen_utc": state[3],
            "bootstrap_csv_sha256": state[4],
            "new_forward_observation_count": count,
            "latest_forward_observation": dict(zip(keys, last)) if last is not None else None,
            "paper_order_submission": "DISABLED",
            "warning": "Exploratory observational data, not sealed independent validation or broker performance.",
        }

    def process(self, bars: Sequence[Bar], *, csv_sha256: str,
                observed_at: datetime, bootstrap: bool = False) -> dict:
        now = _require_utc(observed_at)
        if (not isinstance(csv_sha256, str) or len(csv_sha256) != 64
                or any(char not in "0123456789abcdef" for char in csv_sha256)):
            raise ValueError("verified lowercase SHA-256 required")
        sequence = _fresh_closed_sequence(bars, now)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            state = self.connection.execute(
                "SELECT schema_version,last_start,last_seen_utc FROM forward_state "
                "WHERE singleton=1").fetchone()
            if bootstrap:
                if state is not None or self.connection.execute(
                        "SELECT COUNT(*) FROM captured_bar_hashes").fetchone()[0]:
                    raise ValueError("refusing to reset existing forward evidence")
                self.connection.executemany(
                    "INSERT INTO captured_bar_hashes(start_utc,close_utc,bar_sha256) "
                    "VALUES (?,?,?)",
                    ((b.start.isoformat(), b.close_time.isoformat(), _bar_sha256(b))
                     for b in sequence))
                self.connection.execute(
                    "INSERT INTO forward_state VALUES(1,?,?,?,?,?)",
                    (SCHEMA_VERSION, sequence[0].start.isoformat(),
                     sequence[-1].start.isoformat(), now.isoformat(), csv_sha256))
                outcome = "BOOTSTRAPPED_HISTORY_ONLY_NO_RETROSPECTIVE_SIGNALS"
            else:
                if state is None or state[0] != SCHEMA_VERSION:
                    raise ValueError("forward journal missing or schema invalid; explicit bootstrap required")
                latest = utc_timestamp(state[1])
                if now < utc_timestamp(state[2]):
                    raise ValueError("observation clock moved backwards")
                older = [b for b in sequence if b.start <= latest]
                if not older or older[-1].start != latest or len(older) < MIN_OVERLAP:
                    raise ValueError("capture lacks the required overlapping immutable history")
                for b in older:
                    known = self.connection.execute(
                        "SELECT close_utc,bar_sha256 FROM captured_bar_hashes "
                        "WHERE start_utc=?", (b.start.isoformat(),)).fetchone()
                    if known != (b.close_time.isoformat(), _bar_sha256(b)):
                        raise ValueError("previously anchored provider bar changed or disappeared")
                fresh = [b for b in sequence if b.start > latest]
                if len(fresh) > 1:
                    raise ValueError("missed forward observation; refusing hindsight catch-up")
                if not fresh:
                    outcome = "ALREADY_OBSERVED_NO_DUPLICATE"
                else:
                    current = fresh[0]
                    if current.start != latest + timedelta(hours=1):
                        raise ValueError("new forward observation is not the next contiguous hour")
                    close = current.close
                    six = ((close / sequence[-7].close) - Decimal("1")) * Decimal("10000")
                    day = ((close / sequence[-25].close) - Decimal("1")) * Decimal("10000")
                    block = sequence[-24:]
                    range_bps = (
                        max(b.high for b in block) - min(b.low for b in block)
                    ) / close * Decimal("10000")
                    self.connection.execute(
                        "INSERT INTO captured_bar_hashes(start_utc,close_utc,bar_sha256) "
                        "VALUES(?,?,?)",
                        (current.start.isoformat(), current.close_time.isoformat(),
                         _bar_sha256(current)))
                    self.connection.execute(
                        "INSERT INTO forward_observations VALUES(?,?,?,?,?,?,?,?,?)",
                        (current.start.isoformat(), current.close_time.isoformat(),
                         now.isoformat(), csv_sha256, str(close),
                         str(six), str(day), str(range_bps),
                         str(break_even_price_move_bps())))
                    self.connection.execute(
                        "UPDATE forward_state SET last_start=?,last_seen_utc=? WHERE singleton=1",
                        (current.start.isoformat(), now.isoformat()))
                    outcome = "ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE"
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        result = self.status()
        result["outcome"] = outcome
        return result


def _local_forward_path(value: str, *, root: Path) -> Path:
    """CLI refuses research/holdout data, symlink traversal and outside paths."""
    root = root.resolve()
    dest = Path(value).resolve()
    if not dest.is_relative_to(root):
        raise ValueError("forward CLI paths must stay within data/forward; no research/holdout inputs")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="LOCAL read-only provider-capture forward observation journal")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bootstrap", action="store_true", help="Anchor fresh history; zero forward observations")
    group.add_argument("--observe", action="store_true", help="Accept exactly one new, timely closed hourly bar")
    group.add_argument("--status", action="store_true", help="Show persisted observational summary only")
    parser.add_argument("--csv", help="Fresh capture CSV with its .manifest.json in data/forward/")
    parser.add_argument("--db", default="data/forward/observations.sqlite3")
    args = parser.parse_args()
    root = Path.cwd() / "data" / "forward"
    db = _local_forward_path(args.db, root=root)
    if args.status:
        if args.csv is not None:
            parser.error("--status does not take --csv")
        with ForwardObservationJournal(db) as journal:
            output = journal.status()
    else:
        if not args.csv:
            parser.error("--bootstrap/--observe requires --csv")
        source = _local_forward_path(args.csv, root=root)
        now = datetime.now(timezone.utc)  # no operator-supplied, backdated as-of override
        bars, digest = read_verified_capture(source, observed_at=now)
        with ForwardObservationJournal(db, initialize=args.bootstrap) as journal:
            output = journal.process(bars, csv_sha256=digest,
                                     observed_at=now, bootstrap=args.bootstrap)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
