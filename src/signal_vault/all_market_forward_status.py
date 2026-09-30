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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .cloud_forward_service import CLOUD_ROOT
from .equity_cloud_sidecar import CHILD as EQUITY_CHILD
from .equity_forward_collector import (
    CAPTURE_EARLIEST_AFTER_CLOSE,
    CAPTURE_LATEST_AFTER_CLOSE,
    _validate_plan as _validate_equity_plan,
)
from .kalshi_cloud_sidecar import CHILD as KALSHI_CHILD
from .kalshi_prospective_collector import (
    CAPTURE_WINDOW as KALSHI_CAPTURE_WINDOW,
    HORIZONS,
    validate_prospective_kalshi_plan,
)
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


def _equity_status(
    base:Path,
    *,
    as_of:datetime|None=None,
)->dict[str,object]:
    checked=(as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    root=_private_child(base,EQUITY_CHILD)
    if root is None:
        return {
            "status":"NOT_STARTED",
            "session_plan_files":0,
            "prospective_core_hour_receipts":0,
            "target_core_hours":EQUITY_TARGET_CORE_HOURS,
            "target_sessions":EQUITY_TARGET_SESSIONS,
            "decision_hours_not_due_yet":0,
            "decision_hours_capture_window_open":0,
            "decision_hours_missing_after_window":0,
            "offline_integrity_audit_required":True,
        }
    plans=_private_files(root,"equity-forward-plan-*.json")
    receipts=_private_files(root,"equity-forward-*.json")
    receipts=tuple(x for x in receipts if not x.name.startswith("equity-forward-plan-"))
    receipt_names={x.name for x in receipts}
    not_due=0
    due_open=0
    missing_expired=0
    planned_hours=0
    for path in plans:
        plan=_read_json(path)
        _validate_equity_plan(plan)
        opens=plan.get("expected_core_opens_utc")
        if not isinstance(opens,list):
            raise ValueError("equity session plan lacks expected core hours")
        for raw in opens:
            opened=datetime.fromisoformat(str(raw)).astimezone(timezone.utc)
            planned_hours+=1
            prefix=f"equity-forward-{opened.strftime('%Y%m%dT%H%MZ')}-"
            captured=any(name.startswith(prefix) for name in receipt_names)
            if captured:
                continue
            closed=opened+timedelta(hours=1)
            if checked<closed+CAPTURE_EARLIEST_AFTER_CLOSE:
                not_due+=1
            elif checked<closed+CAPTURE_LATEST_AFTER_CLOSE:
                due_open+=1
            else:
                missing_expired+=1
    return {
        "status":"EVIDENCE_PRESENT",
        "session_plan_files":len(plans),
        "planned_core_hours":planned_hours,
        "prospective_core_hour_receipts":len(receipts),
        "decision_hours_not_due_yet":not_due,
        "decision_hours_capture_window_open":due_open,
        "decision_hours_missing_after_window":missing_expired,
        "target_core_hours":EQUITY_TARGET_CORE_HOURS,
        "target_sessions":EQUITY_TARGET_SESSIONS,
        "raw_core_hour_receipts_remaining_to_60":max(
            0,EQUITY_TARGET_CORE_HOURS-len(receipts)
        ),
        "raw_session_plans_remaining_to_10":max(
            0,EQUITY_TARGET_SESSIONS-len(plans)
        ),
        "artifact_counts_are_not_gate_pass":True,
        "time_aware_progress_is_not_integrity_audit":True,
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


def _kalshi_status(
    base:Path,
    *,
    as_of:datetime|None=None,
)->dict[str,object]:
    checked=(as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
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
            "decision_snapshots_not_due_yet":0,
            "decision_snapshot_windows_open":0,
            "decision_snapshots_missing_after_window":0,
            "settlements_not_due_yet":0,
            "settlements_pending_after_planned_close":0,
            "offline_integrity_audit_required":True,
        }
    plans=_private_files(root,"kalshi-prospective-plan-*.json")
    if len(plans)>1:
        raise ValueError("multiple Kalshi prospective plans found")
    snapshots=_private_files(root,"kalshi-forward-*.json")
    settlements=_private_files(root,"kalshi-settlement-*.json")
    snapshot_names={x.name for x in snapshots}
    settlement_names={x.name for x in settlements}
    planned_markets=None
    planned_events=None
    plan_sha=None
    not_due=0
    window_open=0
    missing_expired=0
    settlement_not_due=0
    settlement_pending=0
    if plans:
        plan=_read_json(plans[0])
        markets=validate_prospective_kalshi_plan(plan)
        planned_markets=len(markets)
        planned_events=len({str(x["event_ticker"]) for x in markets})
        plan_sha=plan["plan_sha256"]
        for item in markets:
            ticker=str(item["ticker"])
            close=datetime.fromisoformat(str(item["close_time"])).astimezone(timezone.utc)
            for horizon in HORIZONS:
                name=f"kalshi-forward-{ticker}-{horizon}s.json"
                if name in snapshot_names:
                    continue
                target=close-timedelta(seconds=horizon)
                if checked<target:
                    not_due+=1
                elif checked<target+KALSHI_CAPTURE_WINDOW:
                    window_open+=1
                else:
                    missing_expired+=1
            settlement_name=f"kalshi-settlement-{ticker}.json"
            if settlement_name not in settlement_names:
                if checked<close:
                    settlement_not_due+=1
                else:
                    settlement_pending+=1
    return {
        "status":"EVIDENCE_PRESENT" if plans else "SIDE_CAR_PRESENT_NO_PLAN",
        "plan_present":bool(plans),
        "plan_sha256":plan_sha,
        "planned_market_count":planned_markets,
        "planned_distinct_event_count":planned_events,
        "prospective_decision_snapshots":len(snapshots),
        "settlement_receipts":len(settlements),
        "decision_snapshots_not_due_yet":not_due,
        "decision_snapshot_windows_open":window_open,
        "decision_snapshots_missing_after_window":missing_expired,
        "settlements_not_due_yet":settlement_not_due,
        "settlements_pending_after_planned_close":settlement_pending,
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
        "time_aware_progress_is_not_integrity_audit":True,
        "offline_integrity_audit_required":True,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }

def all_market_forward_status(
    *,
    environ:Mapping[str,str]|None=None,
    root:Path=CLOUD_ROOT,
    as_of:datetime|None=None,
)->dict[str,object]:
    env=os.environ if environ is None else environ
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode&0o077:
        raise ValueError("shared forward evidence root must be private")
    checked=(as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    crypto=combined_offline_status(
        environ=env,
        btc_root=root,
        sidecar_root=root/"isolated-six-crypto-prospective",
    )
    return {
        "kind":"ALL_MARKET_FORWARD_READINESS_STATUS_NO_ORDERS",
        "checked_at_utc":checked.isoformat(),
        "btc_and_six_crypto":crypto,
        "us_equity":_equity_status(root,as_of=checked),
        "kalshi":_kalshi_status(root,as_of=checked),
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
