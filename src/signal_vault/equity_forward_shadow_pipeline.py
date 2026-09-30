"""End-to-end offline stock prospective-shadow pipeline.

The pipeline joins two independently verified evidence sources:
1. long-horizon historical IEX/XNYS data used only for a fixed 60-core-hour
   indicator warmup;
2. the latest clean prospective equity forward segment.

The historical warmup must end immediately before the first prospective XNYS
core hour. It is never counted toward prospective evidence. No network request,
credential access, order submission, or live activation occurs here.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .ci_historical_equities import SYMBOLS
from .equity_forward_archive_audit import (
    load_current_equity_forward_segment,
)
from .equity_prospective_shadow_summary import (
    WARMUP_CORE_HOURS,
    build_equity_prospective_shadow_summary,
)
from .offline_equity_walk_forward import _reload_phase48_verified_source
from .offline_long_equity_validation import validate_long_equity_history


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware stock shadow pipeline timestamp required")
    return value.astimezone(timezone.utc)


def _xnys_core_grid(
    start_date: date,
    end_date_inclusive: date,
) -> tuple[datetime, ...]:
    if start_date > end_date_inclusive:
        raise ValueError("invalid XNYS grid range")
    try:
        import exchange_calendars as xc
    except ImportError as exc:
        raise RuntimeError(
            "stock shadow pipeline requires optional [equity-research]"
        ) from exc
    calendar = xc.get_calendar(
        "XNYS",
        start=start_date.isoformat(),
        end=(end_date_inclusive + timedelta(days=1)).isoformat(),
    )
    output: list[datetime] = []
    for session in calendar.sessions:
        trading_date = session.date()
        if not start_date <= trading_date <= end_date_inclusive:
            continue
        opened = calendar.session_open(session).to_pydatetime().astimezone(timezone.utc)
        closed = calendar.session_close(session).to_pydatetime().astimezone(timezone.utc)
        first = opened.replace(minute=0, second=0, microsecond=0)
        if first < opened:
            first += timedelta(hours=1)
        final = closed.replace(minute=0, second=0, microsecond=0)
        if final > closed:
            final -= timedelta(hours=1)
        cursor = first
        while cursor + timedelta(hours=1) <= final:
            output.append(cursor)
            cursor += timedelta(hours=1)
    return tuple(output)


def build_equity_forward_shadow_pipeline(
    *,
    historical_source_root: str | Path,
    forward_root: str | Path,
    historical_confirmation: Mapping[str, object],
    as_of: datetime,
) -> dict[str, object]:
    checked_at = _utc(as_of)
    historical_root = Path(historical_source_root)
    baseline = validate_long_equity_history(
        historical_root,
        as_of=checked_at,
    )
    confirmation_source_sha=historical_confirmation.get(
        "phase48_source_manifest_sha256"
    )
    if confirmation_source_sha != baseline["source_manifest_sha256"]:
        raise ValueError(
            "stock historical confirmation does not match verified warmup dataset"
        )
    historical_datasets, historical_grid = _reload_phase48_verified_source(
        historical_root,
        baseline=baseline,
        as_of=checked_at,
    )
    source_audit, forward_datasets, forward_grid = (
        load_current_equity_forward_segment(forward_root)
    )
    if len(forward_grid) < 60:
        raise ValueError("latest clean stock forward segment has fewer than 60 core hours")

    first_forward = forward_grid[0]
    eligible_indices = [
        idx for idx, opened in enumerate(historical_grid)
        if opened < first_forward
    ]
    if len(eligible_indices) < WARMUP_CORE_HOURS:
        raise ValueError("verified stock history lacks pre-forward warmup")
    last_history_index = eligible_indices[-1]
    warm_start_index = last_history_index - WARMUP_CORE_HOURS + 1
    warm_grid = tuple(
        historical_grid[warm_start_index:last_history_index + 1]
    )
    if len(warm_grid) != WARMUP_CORE_HOURS:
        raise AssertionError("fixed stock historical warmup length changed")

    expected_bridge = _xnys_core_grid(
        warm_grid[-1].date(),
        first_forward.date(),
    )
    try:
        position = expected_bridge.index(warm_grid[-1])
    except ValueError as exc:
        raise ValueError("historical warmup end is not a valid XNYS core hour") from exc
    if position + 1 >= len(expected_bridge):
        raise ValueError("cannot establish next XNYS core hour after historical warmup")
    if expected_bridge[position + 1] != first_forward:
        raise ValueError(
            "verified historical stock warmup is not adjacent to prospective segment"
        )

    warm_datasets = {
        symbol: tuple(
            historical_datasets[symbol][
                warm_start_index:last_history_index + 1
            ]
        )
        for symbol in SYMBOLS
    }
    summary = build_equity_prospective_shadow_summary(
        historical_confirmation,
        source_audit,
        warmup_datasets=warm_datasets,
        warmup_grid=warm_grid,
        prospective_datasets=forward_datasets,
        prospective_grid=forward_grid,
        as_of=checked_at,
    )
    summary["phase48_source_manifest_sha256"] = baseline[
        "source_manifest_sha256"
    ]
    summary["historical_source_replayed_before_shadow"] = True
    summary["forward_archive_audited_before_shadow"] = True
    summary["warmup_last_core_open_utc"] = warm_grid[-1].isoformat()
    summary["prospective_first_core_open_utc"] = first_forward.isoformat()
    summary["warmup_and_prospective_xnys_clock_adjacent"] = True
    summary["network_requests_during_pipeline"] = "NONE"
    summary["credentials_accessed_during_pipeline"] = "NONE"
    return summary


def _read_confirmation(path: Path) -> dict[str, object]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_mode & 0o077
        or not 0 < path.stat().st_size <= 2_000_000
    ):
        raise ValueError("historical confirmation receipt must be a private regular file")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("historical confirmation receipt must be an object")
    return value


def _write_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("stock shadow pipeline output must be a new file")
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


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline verified-history + prospective stock shadow pipeline"
    )
    parser.add_argument("--historical-source-root", type=Path, required=True)
    parser.add_argument("--forward-root", type=Path, required=True)
    parser.add_argument("--historical-confirmation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        confirmation = _read_confirmation(args.historical_confirmation)
        result = build_equity_forward_shadow_pipeline(
            historical_source_root=args.historical_source_root,
            forward_root=args.forward_root,
            historical_confirmation=confirmation,
            as_of=datetime.now(timezone.utc),
        )
        _write_exclusive(args.output, result)
        print(json.dumps({
            "status": "EQUITY_PROSPECTIVE_SHADOW_SUMMARY_COMPLETE",
            "prospective_core_hours_per_asset":
                result["prospective_core_hours_per_asset"],
            "distinct_xnys_sessions": result["distinct_xnys_sessions"],
            "paper_order_submission": "DISABLED",
            "live_order_submission": "DISABLED",
        }, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "network_requests": "NONE",
            "credentials_accessed": "NONE",
            "paper_order_submission": "DISABLED",
            "live_order_submission": "DISABLED",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
