"""Read the latest verified six-crypto evidence into the compact ML ensemble.

Offline only: this module reads existing evidence and returns a research
snapshot. It has no network client and no order path.
"""
from __future__ import annotations

from datetime import datetime,timezone
from pathlib import Path

from .crypto_forward_compact_models import compact_crypto_ensemble_snapshot
from .crypto_universe_forward import _audit_chain,_safe_root
from .six_crypto_forward_scorecard import _active_datasets


def current_compact_crypto_snapshot(*,root:Path)->dict[str,object]:
    base=_safe_root(Path(root))
    chain=_audit_chain(base)
    if not chain:
        return {
            "kind":"PHASE162_CURRENT_COMPACT_CRYPTO_RESEARCH_SNAPSHOT",
            "status":"NO_VERIFIED_SOURCE_CHAIN",
            "network_requests":"NONE",
            "order_submission":"DISABLED",
        }
    segment=chain[-1]["segment_index"]
    active=[row for row in chain if row["segment_index"]==segment]
    if len(active)<2:
        return {
            "kind":"PHASE162_CURRENT_COMPACT_CRYPTO_RESEARCH_SNAPSHOT",
            "status":"WAITING_FOR_73RD_COMPLETED_BAR",
            "segment_index":segment,
            "source_receipt_count":len(active),
            "network_requests":"NONE",
            "order_submission":"DISABLED",
        }
    if active[0]["event"]!="HISTORICAL_72H_BOOTSTRAP":
        raise ValueError("source segment lacks 72h bootstrap")
    if any(
        row["event"]!="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR"
        for row in active[1:]
    ):
        raise ValueError("source segment is not contiguous")
    latest=active[-1]
    captured=datetime.fromisoformat(
        latest["captured_utc"]
    ).astimezone(timezone.utc)
    snapshot=compact_crypto_ensemble_snapshot(
        _active_datasets(active),
        source_receipt_sha256=latest["receipt_sha256"],
        captured_utc=captured,
    )
    return {
        "kind":"PHASE162_CURRENT_COMPACT_CRYPTO_RESEARCH_SNAPSHOT",
        "status":"AVAILABLE",
        "segment_index":segment,
        "source_receipt_count":len(active),
        "latest_closed_hour_utc":latest["closed_hour_utc"],
        "captured_utc":latest["captured_utc"],
        "source_receipt_sha256":latest["receipt_sha256"],
        "model_snapshot":snapshot,
        "network_requests":"NONE",
        "order_submission":"DISABLED",
    }
