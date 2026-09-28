"""Deterministic scheduling policy for the unattended paper daemon."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .paper_runtime import PaperCycleResult


def next_closed_hour_delay(now: datetime, *, settle_seconds: int = 8) -> float:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware scheduler time required")
    utc = now.astimezone(timezone.utc)
    nxt = utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1, seconds=settle_seconds)
    return max(1.0, (nxt - utc).total_seconds())


def next_delay_seconds(result: PaperCycleResult, *, now: datetime) -> float:
    state = result.state
    if state in {"PAPER_SUBMISSION_RECORDED", "BLOCKED_PROVIDER_ORDER"}:
        return 10.0
    if state in {"BLOCKED_RECONCILIATION", "BLOCKED_FEE_AUDIT"}:
        return 300.0
    if state in {"BLOCKED_PROVIDER_DRIFT"}:
        return 300.0
    if state in {"HOLD_BAD_MARKET_DATA"}:
        return 60.0
    if state in {"PAPER_DRAFT_READY"}:
        # A read-only worker should not spin on the same draft.
        return next_closed_hour_delay(now)
    if state == "OPERATOR_HALTED":
        return 60.0
    if state in {"HOLD", "HOLD_ADVISORY", "ALREADY_PROCESSED", "REJECTED"}:
        return next_closed_hour_delay(now)
    return 60.0
