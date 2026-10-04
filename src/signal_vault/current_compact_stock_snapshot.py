"""Offline current US-stock compact-model snapshot.

Reads only the latest clean six-stock prospective segment already stored by the
Railway sidecar. No network requests, credentials, order drafts, or execution.
"""
from __future__ import annotations

from datetime import timezone
from pathlib import Path

from .equity_forward_archive_audit import load_current_equity_forward_segment
from .equity_model_warmup import load_stock_model_warmup
from .stock_forward_compact_models import (
    MINIMUM_COMPLETED_CORE_HOURS,
    stock_cross_source_ensemble_snapshot,
)


def current_compact_stock_snapshot(*,root:Path)->dict[str,object]:
    audit,datasets,timeline=load_current_equity_forward_segment(root)
    hours=len(timeline)
    inference_datasets=datasets
    warmup_used=False
    warmup_hours_used=0
    if hours<MINIMUM_COMPLETED_CORE_HOURS:
        try:
            warmup_record,warmup=load_stock_model_warmup(
                stock_root=root,
                first_forward_open=timeline[0],
            )
        except Exception as exc:
            return {
                "kind":"PHASE162_CURRENT_STOCK_COMPACT_MODEL_SNAPSHOT_NO_ORDER",
                "status":"WAITING_FOR_HISTORICAL_MODEL_WARMUP",
                "verified_prospective_core_hours":hours,
                "required_total_feature_hours":MINIMUM_COMPLETED_CORE_HOURS,
                "warmup_failure_class":type(exc).__name__,
                "source_integrity_passed":audit.get("source_integrity_passed"),
                "broker_order_submission":"DISABLED",
                "paper_activation_permitted":False,
                "live_trading":"UNAVAILABLE",
            }
        needed=MINIMUM_COMPLETED_CORE_HOURS-hours
        if needed<=0:
            raise AssertionError("unreachable stock warmup requirement")
        if any(len(warmup[symbol])<needed for symbol in warmup):
            raise ValueError("stored stock model warmup is too short")
        inference_datasets={
            symbol:tuple(warmup[symbol][-needed:])+tuple(datasets[symbol])
            for symbol in datasets
        }
        warmup_used=True
        warmup_hours_used=needed

    latest_captures={
        rows[-1].captured_utc.astimezone(timezone.utc)
        for rows in datasets.values()
    }
    if len(latest_captures)!=1:
        raise ValueError("latest stock capture timestamps are not aligned")
    captured=next(iter(latest_captures))
    snapshot=stock_cross_source_ensemble_snapshot(
        inference_datasets,
        captured_utc=captured,
        allow_historical_warmup=warmup_used,
    )
    return {
        "kind":"PHASE162_CURRENT_STOCK_COMPACT_MODEL_SNAPSHOT_NO_ORDER",
        "status":"AVAILABLE",
        "verified_prospective_core_hours":hours,
        "historical_feature_warmup_used":warmup_used,
        "historical_feature_warmup_hours_used":warmup_hours_used,
        "historical_feature_warmup_counts_as_prospective":False,
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
