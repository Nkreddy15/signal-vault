"""One read-only operator report for the BTC-first six-crypto collector.

This module composes the independently tested evidence-integrity, prospective
shadow-scorecard and storage-capacity audits. It performs no repair, no DATA
GET, no credential read, no Railway API call, no evidence deletion and no
broker action. Its purpose is to make incident state explicit without turning
an alert into an automatic mutation.

Classification is intentionally conservative:
- INFO: source chains are valid; wait/continue scheduled collection.
- WARNING: evidence is valid but sidecar is behind, capacity projection is
  concerning, or a source has not yet reached its next evidence milestone.
- HALT_REVIEW: integrity failure, source/shadow divergence, BTC durable pause
  or a hard storage guard would block the next sidecar tick.

A warning/halt never authorizes backfill, pruning, pause clearing, spending,
credential changes or order submission.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cloud_forward_service import CLOUD_ROOT
from .crypto_universe_forward import SHARED_VOLUME_SIDECAR_ROOT
from .dual_forward_integrity import dual_forward_integrity_status
from .six_crypto_forward_scorecard import prospective_shadow_scorecard
from .six_crypto_storage_audit import sidecar_storage_audit


def _safe_component(name:str,callable_,**kwargs) -> dict[str,object]:
    try:
        value=callable_(**kwargs)
        if not isinstance(value,dict):
            raise ValueError("component did not return mapping")
        return value
    except Exception as exc:
        return {
            "component":name,
            "status":"BLOCKED",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "credentials_accessed":"NONE",
            "broker_order_submission":"DISABLED",
        }


def forward_operator_report(
    *,
    btc_root:Path=CLOUD_ROOT,
    sidecar_root:Path=SHARED_VOLUME_SIDECAR_ROOT,
) -> dict[str,object]:
    btc_root=Path(btc_root)
    sidecar_root=Path(sidecar_root)
    integrity=_safe_component(
        "dual_forward_integrity",
        dual_forward_integrity_status,
        btc_root=btc_root,sidecar_root=sidecar_root)
    storage=_safe_component(
        "six_crypto_storage",
        sidecar_storage_audit,
        btc_root=btc_root,sidecar_root=sidecar_root)

    if sidecar_root.exists() and sidecar_root.is_dir() and not sidecar_root.is_symlink():
        scorecard=_safe_component(
            "six_crypto_forward_scorecard",
            prospective_shadow_scorecard,
            root=sidecar_root)
    else:
        scorecard={
            "component":"six_crypto_forward_scorecard",
            "status":"NOT_AVAILABLE_BEFORE_SIDECAR_SOURCE_EXISTS",
            "network_requests":"NONE",
            "credentials_accessed":"NONE",
            "broker_order_submission":"DISABLED",
            "strategy_promoted":False,
        }

    severity="INFO"
    state="HEALTHY_WAITING_OR_COLLECTING"
    response="NO_MUTATION_CONTINUE_OR_WAIT_FOR_NEXT_SCHEDULED_TICK"
    reasons=[]

    integrity_status=integrity.get("status")
    storage_status=storage.get("status")
    score_status=scorecard.get("status")

    hard_integrity={
        "BLOCKED",
        "BTC_PAUSED_SIDE_EVIDENCE_PRESERVED",
    }
    if integrity_status in hard_integrity or score_status in {
        "BLOCKED","BLOCKED_EVIDENCE_OR_SHADOW_AUDIT_FAILED",
    }:
        severity="HALT_REVIEW"
        state="EVIDENCE_INTEGRITY_OR_BTC_PAUSE_REQUIRES_REVIEW"
        response="PRESERVE_ALL_EVIDENCE_REVIEW_ONLY_NO_AUTOMATIC_RECOVERY"
        reasons.append("INTEGRITY_OR_PAUSE")
    if storage_status in {
        "BLOCKED","HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK",
    }:
        severity="HALT_REVIEW"
        state="STORAGE_HARD_GUARD_REQUIRES_REVIEW"
        response="PRESERVE_ALL_EVIDENCE_REVIEW_CAPACITY_NO_AUTOMATIC_PRUNING"
        reasons.append("STORAGE_HARD_GUARD")

    if severity!="HALT_REVIEW":
        if integrity_status=="BTC_HEALTHY_SIX_CRYPTO_BEHIND":
            severity="WARNING"
            state="SIX_CRYPTO_BEHIND_BTC_FIRST_STREAM"
            response="WAIT_NEXT_SCHEDULED_TICK_AND_REVIEW_IF_LAG_PERSISTS"
            reasons.append("SIDECAR_LAG")
        if storage_status=="CAPACITY_PROJECTION_WARNING_PRESERVE_ALL_EVIDENCE":
            severity="WARNING"
            state="CAPACITY_PROJECTION_WARNING"
            response="REVIEW_CAPACITY_BEFORE_HARD_GUARD_NO_AUTOMATIC_SPEND_OR_DELETE"
            reasons.append("CAPACITY_PROJECTION")
        if severity=="INFO":
            if integrity_status in {
                "BTC_ONLY_HEALTHY_WAITING_FOR_FIRST_SIX_CRYPTO_TICK",
                "BTC_HEALTHY_SIX_CRYPTO_EMPTY_NAMESPACE",
                "BTC_HEALTHY_SIX_CRYPTO_BASELINE_ONLY",
            }:
                state="HEALTHY_EARLY_COLLECTION_STAGE"
                response="NO_MUTATION_WAIT_FOR_NEXT_SCHEDULED_EVIDENCE"
            elif integrity_status in {
                "BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED",
                "SIX_CRYPTO_168_HOUR_CONTIGUOUS_EVIDENCE_READY",
            }:
                state="HEALTHY_ALIGNED_FORWARD_COLLECTION"
                response="NO_MUTATION_CONTINUE_SCHEDULED_COLLECTION"

    source_hours=integrity.get(
        "six_crypto_current_segment_independent_prospective_hours",0)
    scored=scorecard.get("fully_observed_precommitted_decision_intervals",0)
    if type(source_hours) is not int or source_hours<0:
        source_hours=0
    if type(scored) is not int or scored<0:
        scored=0

    return {
        "kind":"OFFLINE_BTC_FIRST_SIX_CRYPTO_OPERATOR_INCIDENT_REPORT",
        "severity":severity,
        "state":state,
        "reason_codes":reasons,
        "operator_response":response,
        "btc_prospective_observations_verified":
            integrity.get("btc_prospective_observations_verified"),
        "six_crypto_current_segment_prospective_source_hours":source_hours,
        "six_crypto_fully_observed_precommitted_decision_intervals":scored,
        "six_crypto_source_168_hour_collection_ready":
            bool(integrity.get("six_crypto_ready_for_168_hour_audit",False)),
        "six_crypto_168_scored_decisions_ready":
            bool(scorecard.get(
                "full_168_precommitted_decision_outcomes_ready",False)),
        "components":{
            "integrity":integrity,
            "storage":storage,
            "scorecard":scorecard,
        },
        "automatic_actions_forbidden":[
            "DELETE_OR_PRUNE_EVIDENCE",
            "BACKFILL_MISSED_PROSPECTIVE_HOURS",
            "CLEAR_DURABLE_BTC_PAUSE",
            "CHANGE_CREDENTIALS",
            "CREATE_PAID_RESOURCES",
            "ENABLE_PAPER_ORDER_SUBMISSION",
            "ENABLE_LIVE_TRADING",
        ],
        "report_itself_modified_evidence":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="Offline combined forward operator report; no recovery/actions.")
    parser.add_argument("--btc-root",type=Path,default=CLOUD_ROOT)
    parser.add_argument("--sidecar-root",type=Path,default=SHARED_VOLUME_SIDECAR_ROOT)
    args=parser.parse_args(argv)
    report=forward_operator_report(
        btc_root=args.btc_root,sidecar_root=args.sidecar_root)
    print(json.dumps(report,indent=2,sort_keys=True))
    return 2 if report["severity"]=="HALT_REVIEW" else 0


if __name__=="__main__":
    raise SystemExit(main())
