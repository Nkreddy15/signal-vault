"""Operator-facing, strictly OFFLINE incident/status report for forward evidence.

Combines the already strict BTC+six-crypto evidence integrity view with the
sidecar storage projection. It never loads provider credentials, never calls
Railway/Alpaca, never modifies evidence and never submits an order.

This report classifies operational evidence health only. A healthy result is
NOT a trading recommendation, strategy promotion, statistical validation or
permission to enable PAPER/LIVE execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cloud_forward_service import CLOUD_ROOT
from .crypto_universe_forward import SHARED_VOLUME_SIDECAR_ROOT
from .dual_forward_integrity import dual_forward_integrity_status
from .six_crypto_storage_audit import sidecar_storage_audit


BLOCKED_DUAL={
    "BLOCKED",
    "BTC_PAUSED_SIDE_EVIDENCE_PRESERVED",
}
WARNING_DUAL={
    "BTC_HEALTHY_SIX_CRYPTO_BEHIND",
    "SIX_CRYPTO_SOURCE_VALID_SHADOW_NOT_CURRENT",
    "SIX_CRYPTO_SOURCE_VALID_SHADOW_ARCHIVE_INCOMPLETE",
}
HEALTHY_DUAL={
    "BTC_ONLY_HEALTHY_WAITING_FOR_FIRST_SIX_CRYPTO_TICK",
    "BTC_HEALTHY_SIX_CRYPTO_EMPTY_NAMESPACE",
    "BTC_HEALTHY_SIX_CRYPTO_BASELINE_ONLY",
    "BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED",
    "SIX_CRYPTO_168_SOURCE_HOURS_READY_WAITING_ONE_MORE_OUTCOME",
    "SIX_CRYPTO_168_PRECOMMITTED_OUTCOMES_READY",
}


def forward_incident_report(
    *,
    btc_root:Path=CLOUD_ROOT,
    sidecar_root:Path=SHARED_VOLUME_SIDECAR_ROOT,
) -> dict[str,object]:
    """Read-only combined operational classification. Zero repair side effects."""
    btc_root=Path(btc_root)
    sidecar_root=Path(sidecar_root)
    dual=dual_forward_integrity_status(
        btc_root=btc_root,sidecar_root=sidecar_root)
    storage=sidecar_storage_audit(
        btc_root=btc_root,sidecar_root=sidecar_root)

    dual_status=dual.get("status")
    storage_status=storage.get("status")
    if not isinstance(dual_status,str) or not isinstance(storage_status,str):
        raise ValueError("underlying read-only auditors returned invalid status")

    reasons=[]
    if dual_status in BLOCKED_DUAL:
        overall="BLOCKED_PRESERVE_EVIDENCE"
        severity="critical"
        reasons.append(dual.get("reason_code","DUAL_EVIDENCE_BLOCKED"))
    elif storage_status=="HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK":
        overall="WARNING_PRESERVE_BTC_STORAGE_RESERVE"
        severity="warning"
        reasons.append("SIX_MARKET_HARD_STORAGE_GUARD_WOULD_SKIP_NEXT_TICK")
    elif (dual_status in WARNING_DUAL or
          storage_status=="CAPACITY_PROJECTION_WARNING_PRESERVE_ALL_EVIDENCE"):
        overall="WARNING_EVIDENCE_NEEDS_ENGINEERING_REVIEW"
        severity="warning"
        reasons.append(dual.get("reason_code","FORWARD_EVIDENCE_WARNING"))
        if storage_status=="CAPACITY_PROJECTION_WARNING_PRESERVE_ALL_EVIDENCE":
            reasons.append("SIX_MARKET_CAPACITY_PROJECTION_WARNING")
    elif dual_status in HEALTHY_DUAL:
        overall=(
            "MILESTONE_168_PRECOMMITTED_OUTCOMES_AVAILABLE"
            if dual_status=="SIX_CRYPTO_168_PRECOMMITTED_OUTCOMES_READY"
            else "MILESTONE_168_SOURCE_HOURS_AVAILABLE"
            if dual_status=="SIX_CRYPTO_168_SOURCE_HOURS_READY_WAITING_ONE_MORE_OUTCOME"
            else "HEALTHY_FORWARD_EVIDENCE_ACCUMULATING"
        )
        severity="info"
        reasons.append(dual.get("reason_code","NONE"))
    else:
        overall="BLOCKED_UNKNOWN_INTEGRITY_CLASSIFICATION"
        severity="critical"
        reasons.append("UNRECOGNIZED_DUAL_FORWARD_STATUS")

    requires_owner_access=False
    # This report itself never assumes a user action is required. Evidence
    # corruption/pauses are engineering incidents first; paid resources or
    # trading authority remain separate future owner decisions.
    engineering_review_required=severity in ("critical","warning")

    side_hours=dual.get(
        "six_crypto_current_segment_independent_prospective_hours",0)
    scored=dual.get(
        "six_crypto_fully_observed_precommitted_decision_intervals",0)
    return {
        "kind":"OFFLINE_FORWARD_OPERATOR_INCIDENT_REPORT_NO_ORDERS",
        "status":overall,
        "severity":severity,
        "reason_codes":[r for r in reasons if isinstance(r,str)],
        "btc_prospective_observations_verified":
            dual.get("btc_prospective_observations_verified"),
        "six_crypto_current_segment_independent_prospective_hours":side_hours,
        "six_crypto_current_segment_prospective_asset_bars":
            dual.get("six_crypto_current_segment_prospective_asset_bar_count",0),
        "six_crypto_fully_observed_precommitted_decision_intervals":scored,
        "six_crypto_source_168_hour_collection_ready":
            dual.get("six_crypto_source_168_hour_collection_ready",False),
        "six_crypto_fully_scored_168_decision_outcomes_ready":
            dual.get("six_crypto_fully_scored_168_decision_outcomes_ready",False),
        "dual_integrity_status":dual_status,
        "dual_integrity_reason_code":dual.get("reason_code"),
        "storage_status":storage_status,
        "sidecar_bytes":storage.get("sidecar_bytes"),
        "filesystem_available_bytes":storage.get("filesystem_available_bytes"),
        "btc_reserved_free_bytes":storage.get("btc_reserved_free_bytes"),
        "engineering_review_required":engineering_review_required,
        "owner_access_action_required_by_this_report":requires_owner_access,
        "automatic_repair_of_source_evidence":"DISABLED",
        "automatic_pruning":"DISABLED",
        "strategy_promoted":False,
        "future_edge_established":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "files_modified":False,
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="Offline forward evidence incident/status report; no keys/network/orders.")
    parser.add_argument("--btc-root",type=Path,default=CLOUD_ROOT)
    parser.add_argument("--sidecar-root",type=Path,default=SHARED_VOLUME_SIDECAR_ROOT)
    args=parser.parse_args(argv)
    try:
        report=forward_incident_report(
            btc_root=args.btc_root,sidecar_root=args.sidecar_root)
        okay=report["severity"]!="critical"
    except Exception as exc:
        report={
            "kind":"OFFLINE_FORWARD_OPERATOR_INCIDENT_REPORT_NO_ORDERS",
            "status":"BLOCKED_REPORT_GENERATION_FAILED",
            "severity":"critical",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "credentials_accessed":"NONE",
            "files_modified":False,
            "broker_order_submission":"DISABLED",
            "automatic_paper_trading":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        okay=False
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if okay else 2


if __name__=="__main__":
    raise SystemExit(main())
