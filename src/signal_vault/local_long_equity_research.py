"""One-command LOCAL long-horizon US-equity historical research collector.

This exists because the existing GitHub Actions historical workflow is currently
non-diagnostic before job steps start. The local path preserves the same strict
DATA-only boundary: it parses an env file as data (never sources shell code),
requires an explicit PAPER marker, uses only Alpaca historical DATA GETs through
BoundedAlpacaHistoricalBatch, and writes the same immutable long-horizon
evidence shape consumed by offline_long_equity_validation.

No account host, order endpoint, POST, position read, transfer, or live route is
imported or available here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from .ci_historical_equities import SYMBOLS
from .equity_session_grid import conservative_core_hour_plan
from .historical_equity_chunks import long_horizon_equity_plan
from .multi_asset_historical import (
    BoundedAlpacaHistoricalBatch,
    archive_historical_batch,
)
from .offline_multimarket_pipeline import (
    combine_historical_archives,
    read_historical_archive,
)
from .research_universe import candidate, validate_asset_dataset

APPROVAL = "LOCAL_PHASE162_LONG_EQUITY_DATA_GET_ONLY"


def _parse_dotenv(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("local env file must be a real file")
    if path.stat().st_size > 100_000:
        raise ValueError("local env file unexpectedly large")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError("malformed env line")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key.replace("_", "").isalnum():
            raise ValueError("invalid env key")
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ("'", '"')
        ):
            value = value[1:-1]
        if any(ch in value for ch in "\r\n\x00"):
            raise ValueError("invalid env value")
        values[key] = value
    return values


def _private_new_folder(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("research output must be a new path")
    path.mkdir(parents=True, mode=0o700)
    os.chmod(path, 0o700)
    if path.stat().st_mode & 0o077:
        raise PermissionError("research output must be private 0700")


def _write_once(path: Path, payload: dict[str, object]) -> str:
    if path.exists() or path.is_symlink():
        raise ValueError("research receipt must be create-only")
    raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
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


def _collect_chunk(
    *,
    provider: BoundedAlpacaHistoricalBatch,
    start_date: date,
    end_date_exclusive: date,
    as_of: datetime,
    folder: Path,
) -> dict[str, object]:
    _private_new_folder(folder)
    sessions = conservative_core_hour_plan(
        start_date=start_date,
        end_date_exclusive=end_date_exclusive,
        as_of=as_of,
    )
    if not sessions:
        raise ValueError("equity chunk contains no complete XNYS sessions")

    archived = []
    for session in sessions:
        expected = {symbol: session.expected_opens for symbol in SYMBOLS}
        batch = provider.fetch(
            specs=tuple(candidate(symbol) for symbol in SYMBOLS),
            start=session.query_start,
            end=session.query_end,
            as_of=as_of,
            equity_feed="iex",
            equity_expected_open_minutes=expected,
        )
        if (
            batch.asset_class != "us_equity"
            or batch.feed != "alpaca_equity_iex"
            or batch.adjustment != "all"
            or set(batch.bars) != set(SYMBOLS)
        ):
            raise ValueError("unexpected local long-equity provider provenance")
        for symbol in SYMBOLS:
            review = validate_asset_dataset(
                batch.bars[symbol],
                spec=candidate(symbol),
                as_of=as_of,
                expected_session_opens_utc=expected[symbol],
            )
            if (
                review.feed != "alpaca_equity_iex|adjustment=all"
                or review.bar_count != len(session.expected_opens)
            ):
                raise ValueError("local IEX session failed source/hour validation")
        archived.append(
            archive_historical_batch(batch, output_folder=folder)
        )

    grid = tuple(at for session in sessions for at in session.expected_opens)
    parts = tuple(read_historical_archive(path) for path in archived)
    datasets, reviews = combine_historical_archives(
        parts,
        as_of=as_of,
        equity_calendars={symbol: grid for symbol in SYMBOLS},
    )
    if any(len(datasets[symbol]) != len(grid) for symbol in SYMBOLS):
        raise ValueError("combined local equity chunk lost verified core bars")

    plan = {
        "kind": "OFFLINE_LOCAL_XNYS_CORE_HOURLY_IEX_DATA_ONLY_PLAN",
        "market": "us_equity",
        "feed": "iex",
        "symbols": list(SYMBOLS),
        "sessions": [session.as_dict() for session in sessions],
        "expected_complete_core_hours_per_symbol": len(grid),
        "session_count": len(sessions),
        "broker_order_submission": "DISABLED",
    }
    report = {
        "kind": "MANUAL_HISTORICAL_XNYS_IEX_CORE_HOUR_MULTIMARKET_RESEARCH",
        "schema_version": 1,
        "market": "us_equity",
        "feed": "alpaca_equity_iex",
        "stock_adjustment": "all",
        "symbols": list(SYMBOLS),
        "exchange_calendar_session_plan": plan,
        "expected_hourly_regular_core_buckets_per_asset": len(grid),
        "source_sha256": [
            {
                "filename": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in archived
        ],
        "quality_reviews": reviews,
        "historical_no_prospective_forward_observations": True,
        "strategy_validated": False,
        "credential_values_in_output": False,
        "network_calls_other_than_explicit_fixed_IEX_data_GET": "NONE",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }
    report_sha = _write_once(folder / "offline_equity_research.json", report)
    return {
        "completed_exchange_sessions": len(sessions),
        "historical_bars_per_asset": len(grid),
        "report_sha256": report_sha,
    }


def collect_local_long_equity_history(
    *,
    env_file: Path,
    start_date: date,
    end_date_exclusive: date,
    output_root: Path,
    as_of: datetime,
    approval: str,
) -> dict[str, object]:
    if approval != APPROVAL:
        raise PermissionError("explicit local historical DATA-GET approval required")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    checked = as_of.astimezone(timezone.utc)
    env = _parse_dotenv(env_file)
    if env.get("ALPACA_IS_PAPER", "").lower() != "true":
        raise PermissionError("local stock research requires PAPER-marked Alpaca env")
    key = env.get("ALPACA_API_KEY", "").strip()
    secret = env.get("ALPACA_API_SECRET", "").strip()
    if not key or not secret:
        raise PermissionError("PAPER Alpaca data credentials missing from env file")

    plan = long_horizon_equity_plan(
        start_date=start_date,
        end_date_exclusive=end_date_exclusive,
        as_of=checked,
    )
    _private_new_folder(output_root)
    provider = BoundedAlpacaHistoricalBatch(key, secret)
    receipts = []
    for index, chunk in enumerate(plan["chunks"], 1):
        result = _collect_chunk(
            provider=provider,
            start_date=date.fromisoformat(chunk["start_date"]),
            end_date_exclusive=date.fromisoformat(chunk["end_date_exclusive"]),
            as_of=checked,
            folder=output_root / f"chunk-{index:03d}",
        )
        receipts.append({
            "chunk_index": index,
            "start_date": chunk["start_date"],
            "end_date_exclusive": chunk["end_date_exclusive"],
            **result,
        })

    manifest = {
        "kind": "MANUAL_LONG_HORIZON_XNYS_IEX_RESEARCH_MANIFEST",
        "symbols": list(SYMBOLS),
        "feed": "iex",
        "chunk_count": len(receipts),
        "chunks": receipts,
        "prospective_observations_verified": 0,
        "credentials_in_manifest": False,
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "collection_origin": "LOCAL_PHASE162_DATA_GET_ONLY",
    }
    manifest_sha = _write_once(
        output_root / "long_horizon_manifest.json",
        manifest,
    )
    return {
        **manifest,
        "manifest_sha256": manifest_sha,
        "credential_values_in_output": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="LOCAL one-command long-horizon six-stock IEX DATA GET; no orders"
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date-exclusive", type=date.fromisoformat, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--approval", required=True)
    args = parser.parse_args(argv)
    try:
        result = collect_local_long_equity_history(
            env_file=args.env_file,
            start_date=args.start_date,
            end_date_exclusive=args.end_date_exclusive,
            output_root=args.output_root,
            as_of=datetime.now(timezone.utc),
            approval=args.approval,
        )
        print(json.dumps({
            "kind": result["kind"],
            "chunk_count": result["chunk_count"],
            "credential_values_in_output": False,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "LOCAL_PHASE162_LONG_EQUITY_DATA_GET_ONLY",
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "credential_values_in_output": False,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
