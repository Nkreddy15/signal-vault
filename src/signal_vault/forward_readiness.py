"""Entirely offline, READ-ONLY next-hour readiness report for Signal Vault.

Answers the practical operator question 'is my existing evidence sound and is
THIS the correct next collection hour?' It never captures data, prompts for
credentials, opens a broker client, bootstraps, schedules a job, or writes SQLite.
This is advisory about recording DATA only, not a trading signal or readiness
to submit paper/live orders.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .forward_evidence_audit import _archive_path, audit_forward_evidence
from .forward_observer import read_verified_capture
from .market_data import utc_timestamp

HOUR = timedelta(hours=1)
EARLIEST_CAPTURE = timedelta(minutes=3)
LATEST_MANUAL_START = timedelta(minutes=25)


def _clock(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("readiness requires timezone-aware operator clock")
    return now.astimezone(timezone.utc)


def forward_readiness(*, root: str | Path = "data/forward",
                      db: str | Path | None = None,
                      now: datetime) -> dict:
    """Verify archived chain first; plan one FUTURE consecutive hour with no writes.

    now is dependency-injected only for deterministic unit tests. The terminal
    CLI always supplies datetime.now(timezone.utc), never a backdating flag.
    """
    current = _clock(now)
    root = Path(root).expanduser()
    audit = audit_forward_evidence(root=root, db=db)
    latest = utc_timestamp(audit["last_anchored_bar_started_utc"])
    recorded = utc_timestamp(audit["last_journal_recorded_utc"])
    next_close = latest + 2*HOUR  # the next new bar STARTS one hour after latest START
    window_start = next_close + EARLIEST_CAPTURE
    window_end = next_close + LATEST_MANUAL_START
    hour_end = next_close + HOUR
    capture = _archive_path(root, next_close)
    manifest = capture.with_suffix(capture.suffix+".manifest.json")
    journal_arg = audit["journal_path"]
    journal_flag = "" if db is None else " --db "+journal_arg

    result = {
        "kind": "OFFLINE_READ_ONLY_FORWARD_COLLECTION_READINESS",
        "checked_utc": current.isoformat(),
        "evidence": audit["result"],
        "existing_prospective_observations": audit["prospective_observations_verified"],
        "last_anchored_bar_started_utc": latest.isoformat(),
        "next_new_bar_started_utc": (latest+HOUR).isoformat(),
        "next_new_bar_closed_utc": next_close.isoformat(),
        "next_manual_capture_window_start_utc": window_start.isoformat(),
        "next_manual_capture_window_end_exclusive_utc": window_end.isoformat(),
        "expected_capture_csv": str(capture),
        "journal_path": journal_arg,
        "network_requests": "NONE",
        "journal_modified": False,
        "credentials_requested": False,
        "automatic_scheduling": "DISABLED",
        "broker_order_submission": "DISABLED",
        "warning": "Checks internal unsigned evidence and collection timing only; NOT a trade or independent provider attestation.",
    }
    if current < recorded:
        decision = "HALT_LOCAL_CLOCK_BEHIND_JOURNAL"
        action = "Inspect local UTC clock; never backdate or rewrite prior evidence."
    elif current >= hour_end:
        decision = "MISSED_CONSECUTIVE_HOUR_PRESERVE_SEGMENT"
        action = "No hindsight catch-up. Preserve this journal; bootstrap a distinct future segment only after a new real capture."
    elif capture.is_symlink() or manifest.is_symlink():
        decision = "HALT_EXISTING_CAPTURE_SYMLINK"
        action = "Preserve evidence and investigate unexpected capture path; do not overwrite it."
    elif capture.exists() or manifest.exists():
        if current < window_start:
            decision = "HALT_CAPTURE_EXISTS_BEFORE_SAFE_COLLECTION_WINDOW"
            action = "Do not change or overwrite future/premature raw evidence."
        elif not capture.is_file() or not manifest.is_file():
            decision = "HALT_INCOMPLETE_CAPTURE_PAIR"
            action = "Do not recapture under an existing filename; preserve and investigate."
        else:
            try:
                bars, _ = read_verified_capture(capture, observed_at=current)
                if len(bars) != 72 or bars[-1].close_time != next_close:
                    raise ValueError("existing capture does not cover the required 72-hour period")
            except (ValueError, PermissionError, OSError) as exc:
                decision = "HALT_EXISTING_CAPTURE_NOT_CURRENT_OR_NOT_VERIFIED"
                action = "Preserve raw capture and journal for review; no overwriting or retrospective append."
                result["validation_error"] = str(exc)
            else:
                decision = "CURRENT_CAPTURE_EXISTS_REVIEW_MANUAL_APPEND"
                action = (
                    "An already-recorded current-hour CSV exists. Do NOT call manual_forward_cycle "
                    "or recapture. If original evidence is genuinely fresh, the separate observer "
                    "may process it after checking overlap: "
                    "PYTHONPATH=src python -m signal_vault.forward_observer --observe"
                    " --csv "+str(capture)+journal_flag
                )
    elif current < next_close:
        decision = "WAIT_NEXT_HOURLY_CANDLE_TO_CLOSE"
        action = "Do not fetch or observe until the next closed-hour collection window begins."
    elif current < window_start:
        decision = "WAIT_THREE_MINUTES_FOR_CANDLE_PUBLICATION"
        action = "Do not fetch or observe until UTC minute 03."
    elif current >= window_end:
        decision = "MANUAL_CAPTURE_START_WINDOW_CLOSED"
        action = (
            "Do not invoke the one-command collector late. Preserve the journal; "
            "a later UTC hour would require a new prospective segment, not backfill."
        )
    else:
        decision = "READY_FOR_ONE_EXPLICIT_READ_ONLY_MANUAL_CYCLE"
        action = "PYTHONPATH=src python -m signal_vault.manual_forward_cycle"+journal_flag
    result["decision"] = decision
    result["operator_instruction"] = action
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline/READ-ONLY chain audit + exact next-hour collection readiness; no broker access")
    parser.add_argument("--db", default=None,
                        help="Existing journal under data/forward/; default is observations.sqlite3")
    args = parser.parse_args()
    print(json.dumps(forward_readiness(db=args.db, now=datetime.now(timezone.utc)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
