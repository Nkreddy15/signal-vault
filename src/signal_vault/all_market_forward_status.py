"""Credential-free, network-free forward evidence status for every research lane.

This module reports only what is already persisted on the existing volume.
It never creates a sidecar directory, never reads API credentials, never makes
provider requests, and never submits orders.

BTC/six-crypto uses the existing audited offline status. Stocks and Kalshi expose
artifact progress conservatively; their counts are not promoted to a passing
prospective gate until the corresponding offline integrity/scoring stages pass.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .cloud_forward_service import CLOUD_ROOT
from .equity_cloud_sidecar import CHILD as EQUITY_CHILD
from .kalshi_cloud_sidecar import CHILD as KALSHI_CHILD
from .kalshi_prospective_collector import HORIZONS, validate_prospective_kalshi_plan
from .railway_btc_first_dual_cron import combined_offline_status

EQUITY_TARGET_CORE_HOURS=60
EQUITY_TARGET_SESSIONS=10
KALSHI_TARGET_MARKETS=20
KALSHI_TARGET_DISTINCT_EVENTS=10
KALSHI_TARGET_DECISION_SNAPSHOTS=KALSHI_TARGET_MARKETS*len(HORIZONS)


def _private_child(base:Path,name:str)->Path|None:
    path=base/name
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode&0o077:
        raise ValueError(f"unsafe {name} research child")
    return path


def _private_files(root:Path, pattern:str)->tuple[Path,...]:
    files=tuple(sorted(root.glob(pattern),key=lambda p:p.name))
    for path in files:
        if (
            path.is_symlink() or not path.is_file()
            or path.stat().st_mode&0o077
        ):
            raise ValueError("research evidence file must be private regular file")
    return files


def _equity_status(base:Path)->dict[str,object]:
    root=_private_child(base,EQUITY_CHILD)
    if root is None:
        return {
            "status":"NOT_STARTED",
            "session_plan_files":0,
            "prospective_core_hour_receipts":0,
            "target_core_hours":EQUITY_TARGET_CORE_HOURS,
            "target_sessions":EQUITY_TARGET_SESSIONS,
            "offline_integrity_audit_required":True,
        }
    plans=_private_files(root,"equity-forward-plan-*.json")
    receipts=_private_files(root,"equity-forward-*.json")
    # Plan names also start equity-forward-, so exclude them explicitly.
    receipts=tuple(x for x in receipts if not x.name.startswith("equity-forward-plan-"))
    return {
        "status":"EVIDENCE_PRESENT",
        "session_plan_files":len(plans),
        "prospective_core_hour_receipts":len(receipts),
        "target_core_hours":EQUITY_TARGET_CORE_HOURS,
        "target_sessions":EQUITY_TARGET_SESSIONS,
        "raw_core_hour_receipts_remaining_to_60":max(
            0,EQUITY_TARGET_CORE_HOURS-len(receipts)
        ),
        "raw_session_plans_remaining_to_10":max(
            0,EQUITY_TARGET_SESSIONS-len(plans)
        ),
        "artifact_counts_are_not_gate_pass":True,
        "offline_integrity_audit_required":True,
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


def _read_json(path:Path)->dict[str,object]:
    if not 0<path.stat().st_size<=2_000_000:
        raise ValueError("research evidence JSON size invalid")
    value=json.loads(path.read_text())
    if not isinstance(value,dict):
        raise ValueError("research evidence JSON must be an object")
    return value


def _kalshi_status(base:Path)->dict[str,object]:
    root=_private_child(base,KALSHI_CHILD)
    if root is None:
        return {
            "status":"NOT_STARTED",
            "plan_present":False,
            "prospective_decision_snapshots":0,
            "settlement_receipts":0,
            "target_markets":KALSHI_TARGET_MARKETS,
            "target_distinct_events":KALSHI_TARGET_DISTINCT_EVENTS,
            "target_decision_snapshots":KALSHI_TARGET_DECISION_SNAPSHOTS,
            "offline_integrity_audit_required":True,
        }
    plans=_private_files(root,"kalshi-prospective-plan-*.json")
    if len(plans)>1:
        raise ValueError("multiple Kalshi prospective plans found")
    snapshots=_private_files(root,"kalshi-forward-*.json")
    settlements=_private_files(root,"kalshi-settlement-*.json")
    planned_markets=None
    planned_events=None
    plan_sha=None
    if plans:
        plan=_read_json(plans[0])
        markets=validate_prospective_kalshi_plan(plan)
        planned_markets=len(markets)
        planned_events=len({str(x["event_ticker"]) for x in markets})
        plan_sha=plan["plan_sha256"]
    return {
        "status":"EVIDENCE_PRESENT" if plans else "SIDE_CAR_PRESENT_NO_PLAN",
        "plan_present":bool(plans),
        "plan_sha256":plan_sha,
        "planned_market_count":planned_markets,
        "planned_distinct_event_count":planned_events,
        "prospective_decision_snapshots":len(snapshots),
        "settlement_receipts":len(settlements),
        "target_markets":KALSHI_TARGET_MARKETS,
        "target_distinct_events":KALSHI_TARGET_DISTINCT_EVENTS,
        "target_decision_snapshots":KALSHI_TARGET_DECISION_SNAPSHOTS,
        "raw_decision_snapshots_remaining":max(
            0,KALSHI_TARGET_DECISION_SNAPSHOTS-len(snapshots)
        ),
        "raw_settlement_receipts_remaining":max(
            0,KALSHI_TARGET_MARKETS-len(settlements)
        ),
        "artifact_counts_are_not_gate_pass":True,
        "offline_integrity_audit_required":True,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


def all_market_forward_status(
    *,
    environ:Mapping[str,str]|None=None,
    root:Path=CLOUD_ROOT,
)->dict[str,object]:
    env=os.environ if environ is None else environ
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode&0o077:
        raise ValueError("shared forward evidence root must be private")
    crypto=combined_offline_status(
        environ=env,
        btc_root=root,
        sidecar_root=root/"isolated-six-crypto-prospective",
    )
    return {
        "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
        "checked_at_utc":datetime.now(timezone.utc).isoformat(),
        "btc_and_six_crypto":crypto,
        "us_equity":_equity_status(root),
        "kalshi":_kalshi_status(root),
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Read-only all-market forward evidence status"
    )
    parser.parse_args(argv)
    try:
        result=all_market_forward_status()
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "credential_access":"NONE",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
