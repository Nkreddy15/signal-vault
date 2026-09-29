"""Audit-linked offline shadow signals on newest REAL prospective collector candle.

The existing GET-only hourly Mac collector stays unchanged. This standalone,
operator-run read-only report requires a verified automatic segment, retrieves
its latest prospective candle's archived 72-hour CSV by the exact SHA recorded
in the SQLite observation, reruns manifest/bar checks and evaluates three
predeclared EMA research candidates on THAT recorded closed hour only.

No retrospective bar is relabelled as prospective. No broker/data HTTP, secrets,
Keychain, live quote, paper account, draft, state mutation, trading worker or
LaunchAgent write exists in this module. BUY is always research HOLD absent
independently validated prospective expected-return evidence. SELL is just an
unexecuted diagnostic signal and needs a separate position/risk decision.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping

from .forward_evidence_audit import _archived_capture, _private_regular
from .market_data import utc_timestamp
from .shadow_cost_gate import estimate_round_trip, review_shadow_signal
from .strategy import StrategyConfig, generate_signal
from .unattended_forward_cycle import (
    ROOT, SEGMENT_NAME, status_unattended,
)


def _default_candidates() -> tuple[StrategyConfig, ...]:
    return (
        StrategyConfig(),
        StrategyConfig(
            strategy_version="btc-hourly-ema-cross-confirm2-v0.2-RESEARCH-ONLY",
            entry_confirmation_bars=2,
        ),
        StrategyConfig(
            strategy_version="btc-hourly-ema-cross-momentum50bps-v0.3-RESEARCH-ONLY",
            entry_minimum_prior_24h_return_bps=Decimal("50"),
        ),
    )


def _read_one_latest_archived_window(root: Path, status: Mapping[str, object]):
    """Bind one validated capture to latest immutable prospective observation."""
    name = status["active_auto_journal"]
    if not isinstance(name, str) or SEGMENT_NAME.fullmatch(name) is None:
        raise ValueError("not an automatic collector segment")
    db = root / name
    _private_regular(db, "automatic observation journal")
    anchored_start = utc_timestamp(status["last_anchored_bar_started_utc"])
    recorded = utc_timestamp(status["last_journal_recorded_utc"])
    if (anchored_start.utcoffset() != timedelta(0)
            or anchored_start.minute or anchored_start.second
            or anchored_start.microsecond):
        raise ValueError("invalid anchored observation boundary")

    # Read-only connection: never initialize, migrate, delete or update data.
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True,
                                 isolation_level=None, timeout=3)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        row = connection.execute(
            "SELECT start_utc,close_utc,observed_utc,captured_csv_sha256 "
            "FROM forward_observations ORDER BY start_utc DESC LIMIT 1"
        ).fetchone()
        if (row is None
                or row[0] != anchored_start.isoformat()
                or row[1] != (anchored_start + timedelta(hours=1)).isoformat()
                or row[2] != recorded.isoformat()
                or not isinstance(row[3], str)
                or len(row[3]) != 64
                or any(c not in "0123456789abcdef" for c in row[3])):
            raise ValueError("newest prospective observation does not match archived pointer")
        bars, captured = _archived_capture(
            root, closed=anchored_start + timedelta(hours=1),
            expected_sha=row[3],
        )
        if (bars[-1].start != anchored_start or
                captured > recorded or recorded - captured > timedelta(minutes=30)):
            raise ValueError("latest archived candle does not match journal event")
        connection.execute("COMMIT")
        return bars, {
            "bar_started_utc": anchored_start.isoformat(),
            "bar_closed_utc": row[1],
            "observed_utc": row[2],
            "capture_sha256": row[3],
        }
    finally:
        connection.close()


def _same_evidence(a: Mapping[str, object], b: Mapping[str, object]) -> bool:
    fields = ("kind", "state", "active_auto_journal",
              "prospective_observations_verified",
              "last_anchored_bar_started_utc", "last_journal_recorded_utc",
              "broker_order_submission", "network_requests")
    return all(a.get(k) == b.get(k) for k in fields)


def inspect_latest_shadow_signal(
    *,
    forward_root: str | Path = ROOT,
    assumed_spread_bps: Decimal = Decimal("3"),
    collector_reader: Callable[..., object] = status_unattended,
) -> dict[str, object]:
    """Read verified owner-local prospective evidence and emit no-order signals."""
    report: dict[str, object] = {
        "kind": "LATEST_AUDITED_AUTOMATIC_SHADOW_SIGNAL_RESEARCH_ONLY",
        "status": "BLOCKED",
        "reason_code": "NOT_CHECKED",
        "failure_class": None,
        "source": "EXISTING_LOCAL_AUTOMATIC_FORWARD_ARCHIVE_NOT_LIVE_DATA",
        "strategy_promoted": False,
        "strategy_execution": "DISABLED",
        "automatic_paper_trading": "DISABLED",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "market_data_requests": "NONE",
        "keychain_access": "NONE",
        "paper_account_access": "NONE",
        "journal_modified": False,
        "collector_modified": False,
        "warning": (
            "EMA directional signals and assumed cost hurdles do NOT demonstrate "
            "after-cost edge. This is an observed historical closed candle, NOT "
            "a real-time actionable quote, sell instruction or trade permission."
        ),
    }
    try:
        cost = estimate_round_trip(spread_bps=assumed_spread_bps)
    except Exception as exc:
        report["reason_code"] = "INVALID_EXPLICIT_COST_SCENARIO"
        report["failure_class"] = type(exc).__name__
        return report
    report["research_cost_assumptions"] = cost.to_dict()
    root = Path(forward_root).expanduser()
    try:
        status = collector_reader(root=root)
        if (not isinstance(status, Mapping)
                or status.get("kind") != "UNATTENDED_FORWARD_LOCAL_STATUS"
                or status.get("broker_order_submission") != "DISABLED"):
            report["reason_code"] = "COLLECTOR_STATUS_NOT_VERIFIED"
            return report
        tick = status.get("latest_tick")
        if (isinstance(tick, Mapping) and
                tick.get("decision") == "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE"):
            report["reason_code"] = "HALTED_COLLECTOR_PRESERVE_EVIDENCE"
            return report
        if status.get("state") != "ARCHIVED_INTERNAL_EVIDENCE_VERIFIED":
            report["reason_code"] = "NO_AUDITED_AUTO_SEGMENT"
            return report
        count = status.get("prospective_observations_verified")
        if (type(count) is not int or count < 0 or
                status.get("network_requests") != "NONE"):
            report["reason_code"] = "INVALID_ARCHIVE_COUNT_OR_READ_SCOPE"
            return report
        report["prospective_observations_verified"] = count
        if count < 1:
            report["reason_code"] = "BOOTSTRAP_ONLY_NOT_PROSPECTIVE"
            return report

        bars, evidence = _read_one_latest_archived_window(root, status)
        # Fail closed if the archive pointer/segment/count changed mid-read.
        after = collector_reader(root=root)
        if not isinstance(after, Mapping) or not _same_evidence(status, after):
            report["reason_code"] = "ARCHIVE_ADVANCED_DURING_READ_RETRY_LATER"
            return report
        report["evidence"] = {
            **evidence, "research_history_hours": len(bars),
            "latest_closed_bar_close_usd": str(bars[-1].close),
            "read_only_archive_audit": "PASS_INTERNAL_CONSISTENCY_ONLY",
        }
        decisions = []
        for config in _default_candidates():
            signal = generate_signal(bars, config)
            if signal.bar_closed_at != evidence["bar_closed_utc"]:
                raise ValueError("EMA signal candle does not match prospective observation")
            shadow = review_shadow_signal(signal=signal, costs=cost)
            decisions.append({
                "strategy_version": signal.strategy_version,
                "observed_signal": signal.action.value,
                "observed_signal_evidence_id": signal.evidence_id,
                "signal_explanation": signal.explanation,
                "fast_ema": str(signal.fast_ema),
                "slow_ema": str(signal.slow_ema),
                "cost_aware_research_decision": shadow["decision"],
                "reason_code": shadow["reason_code"],
                "broker_order_submission": "DISABLED",
            })
        report["research_decisions"] = decisions
        report["status"] = "AUDITED_ONE_CANDLE_SHADOW_SIGNALS_RESEARCH_ONLY"
        report["reason_code"] = "NONE"
        return report
    except Exception as exc:
        # No file paths, raw receipt/CSV text, provider payloads or exception
        # messages are included in the public report.
        report["reason_code"] = "ARCHIVED_AUTOMATIC_EVIDENCE_OR_SIGNAL_AUDIT_FAILED"
        report["failure_class"] = type(exc).__name__
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OFFLINE latest verified auto-candle shadow signal; NEVER a trading worker.")
    parser.add_argument("--forward-root", default=str(ROOT))
    parser.add_argument(
        "--assumed-spread-bps", default="3",
        help="Hypothetical spread on each trading leg. NOT a live quote.")
    args = parser.parse_args(argv)
    try:
        spread = Decimal(args.assumed_spread_bps)
    except Exception:
        spread = Decimal("NaN")
    result = inspect_latest_shadow_signal(
        forward_root=args.forward_root, assumed_spread_bps=spread)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "AUDITED_ONE_CANDLE_SHADOW_SIGNALS_RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
