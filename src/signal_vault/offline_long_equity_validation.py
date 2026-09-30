"""Offline verification and historical validation of long-horizon US-equity research.

Consumes only the immutable output produced by ci_long_equity_history. Every
chunk report and source archive SHA is rechecked, the full XNYS core-hour grid
is reconstructed from the stored independently derived session plan, and all
predeclared hypotheses are rerun under the three fixed equity-friction
scenarios.

Historical results remain retrospective. This module never reads credentials,
performs network access, selects a strategy from the untouched test fold, or
submits an order.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from .ci_historical_equities import (
    EQUITY_ESTIMATED_COST_SCENARIOS,
    SYMBOLS,
)
from .multi_asset_simulation import ExplicitRoundTripCosts
from .offline_multimarket_pipeline import (
    combine_historical_archives,
    describe_multi_asset_research,
    read_historical_archive,
)

MAX_MANIFEST_BYTES = 2_000_000
MAX_REPORT_BYTES = 20_000_000
MAX_CHUNKS = 20


def _read_object(path: Path, *, max_bytes: int) -> tuple[dict[str, object], bytes]:
    if (
        path.is_symlink()
        or not path.is_file()
        or not 0 < path.stat().st_size <= max_bytes
    ):
        raise ValueError("historical validation input missing, unsafe, or oversized")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("historical validation JSON must be an object")
    return value, raw


def _stamp(raw: object) -> datetime:
    if not isinstance(raw, str) or len(raw) > 64:
        raise ValueError("invalid stored exchange timestamp")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("stored exchange timestamp lacks timezone")
    return value.astimezone(timezone.utc)


def validate_long_equity_history(
    source_root: str | Path,
    *,
    as_of: datetime,
) -> dict[str, object]:
    root = Path(source_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("long-equity source root must be a real directory")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("historical validation as_of must be timezone-aware")
    checked_at = as_of.astimezone(timezone.utc)

    manifest, manifest_raw = _read_object(
        root / "long_horizon_manifest.json",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    if (
        manifest.get("kind")
        != "MANUAL_LONG_HORIZON_XNYS_IEX_RESEARCH_MANIFEST"
        or manifest.get("symbols") != list(SYMBOLS)
        or manifest.get("feed") != "iex"
        or manifest.get("broker_order_submission") != "DISABLED"
        or manifest.get("live_trading") != "UNAVAILABLE"
    ):
        raise ValueError("invalid long-equity manifest contract")

    chunks = manifest.get("chunks")
    if (
        not isinstance(chunks, list)
        or not 1 <= len(chunks) <= MAX_CHUNKS
        or manifest.get("chunk_count") != len(chunks)
    ):
        raise ValueError("invalid long-equity chunk manifest")

    batches = []
    all_session_opens: list[datetime] = []
    chunk_receipts = []
    archive_count = 0
    last_session_open: datetime | None = None

    for expected_index, item in enumerate(chunks, 1):
        if not isinstance(item, Mapping):
            raise ValueError("malformed long-equity chunk receipt")
        if item.get("chunk_index") != expected_index:
            raise ValueError("long-equity chunk indices must be consecutive")
        start_date = item.get("start_date")
        end_date = item.get("end_date_exclusive")
        report_sha = item.get("report_sha256")
        if (
            not isinstance(start_date, str)
            or not isinstance(end_date, str)
            or not isinstance(report_sha, str)
            or len(report_sha) != 64
        ):
            raise ValueError("invalid long-equity chunk metadata")

        folder = root / f"chunk-{expected_index:03d}"
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("missing or unsafe long-equity chunk folder")
        report, report_raw = _read_object(
            folder / "offline_equity_research.json",
            max_bytes=MAX_REPORT_BYTES,
        )
        if hashlib.sha256(report_raw).hexdigest() != report_sha:
            raise ValueError("long-equity chunk report SHA mismatch")
        if (
            report.get("kind")
            != "MANUAL_HISTORICAL_XNYS_IEX_CORE_HOUR_MULTIMARKET_RESEARCH"
            or report.get("symbols") != list(SYMBOLS)
            or report.get("market") != "us_equity"
            or report.get("feed") != "alpaca_equity_iex"
            or report.get("stock_adjustment") != "all"
            or report.get("historical_no_prospective_forward_observations") is not True
            or report.get("strategy_validated") is not False
            or report.get("broker_order_submission") != "DISABLED"
            or report.get("live_trading") != "UNAVAILABLE"
        ):
            raise ValueError("invalid long-equity chunk report contract")

        plan = report.get("exchange_calendar_session_plan")
        sources = report.get("source_sha256")
        if not isinstance(plan, Mapping) or not isinstance(sources, list) or not sources:
            raise ValueError("chunk is missing exchange/source provenance")
        sessions = plan.get("sessions")
        if not isinstance(sessions, list) or len(sessions) != len(sources):
            raise ValueError("chunk exchange sessions and archives differ")

        expected_hours = 0
        for session in sessions:
            if not isinstance(session, Mapping):
                raise ValueError("malformed stored XNYS session")
            opens = session.get("expected_core_bucket_opens_utc")
            if not isinstance(opens, list) or not opens:
                raise ValueError("stored XNYS session lacks core-hour opens")
            for raw_open in opens:
                opened = _stamp(raw_open)
                if last_session_open is not None and opened <= last_session_open:
                    raise ValueError("long-equity session clock is duplicated or out of order")
                all_session_opens.append(opened)
                last_session_open = opened
                expected_hours += 1

        if (
            item.get("completed_exchange_sessions") != len(sessions)
            or item.get("historical_bars_per_asset") != expected_hours
            or report.get("expected_hourly_regular_core_buckets_per_asset")
            != expected_hours
        ):
            raise ValueError("long-equity chunk counts do not match stored exchange grid")

        for source in sources:
            if not isinstance(source, Mapping):
                raise ValueError("malformed long-equity source receipt")
            name = source.get("filename")
            digest = source.get("sha256")
            if (
                not isinstance(name, str)
                or "/" in name
                or "\\" in name
                or not isinstance(digest, str)
                or len(digest) != 64
            ):
                raise ValueError("unsafe long-equity archive reference")
            path = folder / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("long-equity archive SHA mismatch")
            batch = read_historical_archive(path)
            if datetime.fromisoformat(batch.downloaded_utc).astimezone(timezone.utc) > checked_at:
                raise ValueError("historical archive was captured after validation as_of")
            batches.append(batch)
            archive_count += 1

        chunk_receipts.append({
            "chunk_index": expected_index,
            "report_sha256": report_sha,
            "session_count": len(sessions),
            "core_hours_per_asset": expected_hours,
        })

    if not all_session_opens:
        raise ValueError("no verified stock core hours found")

    grid = tuple(all_session_opens)
    datasets, reviews = combine_historical_archives(
        tuple(batches),
        as_of=checked_at,
        equity_calendars={symbol: grid for symbol in SYMBOLS},
    )
    if set(datasets) != set(SYMBOLS):
        raise ValueError("combined long-equity dataset lost a required symbol")
    if any(len(rows) != len(grid) for rows in datasets.values()):
        raise ValueError("combined long-equity symbols do not share the verified XNYS grid")

    scenarios = {}
    for scenario, raw_costs in EQUITY_ESTIMATED_COST_SCENARIOS.items():
        cost = ExplicitRoundTripCosts(
            Decimal(raw_costs["taker_fee_bps"]),
            Decimal(raw_costs["full_spread_bps"]),
            Decimal(raw_costs["slippage_per_side_bps"]),
        )
        report = describe_multi_asset_research(
            datasets,
            as_of=checked_at,
            costs={symbol: cost for symbol in SYMBOLS},
            equity_calendars={symbol: grid for symbol in SYMBOLS},
        )
        if (
            report.get("broker_order_submission") != "DISABLED"
            or report.get("live_trading") != "UNAVAILABLE"
            or report.get("untouched_test_used_for_model_selection") is not False
            or report.get("portfolio_hypothesis_selection_performed") is not False
        ):
            raise ValueError("historical validation attempted strategy promotion")
        scenarios[scenario] = report

    return {
        "kind": "OFFLINE_LONG_HORIZON_US_EQUITY_HISTORICAL_VALIDATION",
        "source_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "symbols": list(SYMBOLS),
        "feed": "alpaca_equity_iex",
        "chunk_count": len(chunks),
        "source_archive_count": archive_count,
        "verified_core_hours_per_asset": len(grid),
        "first_core_open_utc": grid[0].isoformat(),
        "last_core_open_utc": grid[-1].isoformat(),
        "chunk_receipts": chunk_receipts,
        "dataset_reviews": reviews,
        "three_fixed_friction_scenarios": scenarios,
        "chronological_development_validation_untouched_test_complete": True,
        "untouched_test_used_for_strategy_selection": False,
        "historical_results_are_not_prospective_validation": True,
        "historical_walk_forward_complete": False,
        "prospective_observations_verified": 0,
        "automatic_strategy_promotion": "DISABLED",
        "credentials_accessed": "NONE",
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }


def _write_exclusive(path: Path, payload: dict[str, object]) -> str:
    if path.exists() or path.is_symlink():
        raise ValueError("historical validation output must be a new file")
    raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline long-horizon US-equity source replay and historical validation"
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = validate_long_equity_history(
            args.source_root,
            as_of=datetime.now(timezone.utc),
        )
        digest = _write_exclusive(args.output, result)
        print(json.dumps({
            "status": "LONG_EQUITY_HISTORICAL_VALIDATION_COMPLETE",
            "symbols": result["symbols"],
            "core_hours_per_asset": result["verified_core_hours_per_asset"],
            "source_archive_count": result["source_archive_count"],
            "output_sha256": digest,
            "historical_walk_forward_complete": False,
            "prospective_observations_verified": 0,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "credentials_accessed": "NONE",
            "network_requests": "NONE",
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
