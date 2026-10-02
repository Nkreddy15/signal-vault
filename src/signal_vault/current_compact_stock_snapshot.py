"""Offline current US-stock compact-model snapshot.

Reads only the latest clean six-stock prospective segment already stored by the
Railway sidecar. No network requests, credentials, order drafts, or execution.
"""
from __future__ import annotations

from datetime import timezone
from pathlib import Path

from .equity_forward_archive_audit import load_current_equity_forward_segment
from .stock_forward_compact_models import (
    MINIMUM_COMPLETED_CORE_HOURS,
    stock_cross_source_ensemble_snapshot,
)


def current_compact_stock_snapshot(*,root:Path)->dict[str,object]:
    audit,datasets,timeline=load_current_equity_forward_segment(root)
    hours=len(timeline)
    if hours<MINIMUM_COMPLETED_CORE_HOURS:
        return {
            "kind":"PHASE162_CURRENT_STOCK_COMPACT_MODEL_SNAPSHOT_NO_ORDER",
            "status":"WAITING_FOR_49_VERIFIED_CORE_HOURS",
            "verified_core_hours":hours,
            "required_core_hours":MINIMUM_COMPLETED_CORE_HOURS,
            "source_integrity_passed":audit.get("source_integrity_passed"),
            "broker_order_submission":"DISABLED",
            "paper_activation_permitted":False,
            "live_trading":"UNAVAILABLE",
        }

    latest_captures={
        rows[-1].captured_utc.astimezone(timezone.utc)
        for rows in datasets.values()
    }
    if len(latest_captures)!=1:
        raise ValueError("latest stock capture timestamps are not aligned")
    captured=next(iter(latest_captures))
    snapshot=stock_cross_source_ensemble_snapshot(
        datasets,captured_utc=captured
    )
    return {
        "kind":"PHASE162_CURRENT_STOCK_COMPACT_MODEL_SNAPSHOT_NO_ORDER",
        "status":"AVAILABLE",
        "verified_core_hours":hours,
        "verified_sessions":
            audit.get("current_segment_distinct_xnys_sessions"),
        "latest_core_open_utc":timeline[-1].isoformat(),
        "latest_capture_utc":captured.isoformat(),
        "source_integrity_passed":audit.get("source_integrity_passed"),
        "model_snapshot":snapshot,
        "broker_order_submission":"DISABLED",
        "paper_activation_permitted":False,
        "live_trading":"UNAVAILABLE",
    }
