"""Unattended public-GET-only Kalshi prospective cloud sidecar.

One existing Railway hourly process may call this sidecar. It requires no API
credentials and has no portfolio/order imports.

First activated run:
- discovers structurally eligible public open markets;
- freezes and archives a deterministic 20-market / >=10-event plan.

Later runs:
- collect any due 24h/6h public decision snapshots;
- collect public settlement results only after markets settle;
- never backfill a missed decision horizon.

No demo/live order submission is available.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .kalshi_prospective_collector import (
    archive_prospective_kalshi_plan,
    build_prospective_kalshi_plan,
    collect_due_kalshi_snapshots,
    validate_prospective_kalshi_plan,
)
from .kalshi_prospective_settlement import collect_due_kalshi_settlements
from .kalshi_public_research import KalshiPublicResearchClient

ACTIVATION_ENV="SIGNAL_VAULT_KALSHI_SIDECAR"
ACTIVATION_VALUE="KALSHI_PUBLIC_GET_ONLY_NO_ORDERS_V1"
ROOT_ENV="SIGNAL_VAULT_FORWARD_ROOT"
DEFAULT_ROOT=Path("/var/lib/signal-vault/forward")
CHILD="isolated-kalshi-prospective"


def _utc(value:datetime)->datetime:
    if (
        not isinstance(value,datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware Kalshi cloud timestamp required")
    return value.astimezone(timezone.utc)


def _root(env:Mapping[str,str])->Path:
    raw=env.get(ROOT_ENV,str(DEFAULT_ROOT))
    if not isinstance(raw,str) or not raw.startswith("/"):
        raise ValueError("absolute forward evidence root required")
    base=Path(raw)
    if base.is_symlink() or not base.is_dir() or base.stat().st_mode&0o077:
        raise ValueError("shared forward evidence root must be private")
    child=base/CHILD
    if child.exists() or child.is_symlink():
        if child.is_symlink() or not child.is_dir():
            raise ValueError("Kalshi sidecar child must be a real directory")
    else:
        child.mkdir(mode=0o700)
    child.chmod(0o700)
    if child.stat().st_mode&0o077:
        raise PermissionError("Kalshi sidecar child must remain private")
    return child


def _plan_file(root:Path)->Path|None:
    matches=tuple(root.glob("kalshi-prospective-plan-*.json"))
    if len(matches)>1:
        raise ValueError("multiple Kalshi prospective plans in one sidecar root")
    return matches[0] if matches else None


def _load_plan(path:Path)->dict[str,object]:
    if (
        path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077
        or not 0<path.stat().st_size<=2_000_000
    ):
        raise ValueError("unsafe Kalshi prospective plan file")
    try:
        value=json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("Kalshi prospective plan is not valid JSON") from exc
    if not isinstance(value,dict):
        raise ValueError("Kalshi prospective plan must be an object")
    validate_prospective_kalshi_plan(value)
    return value


def _result(status:str, **extra:object)->dict[str,object]:
    return {
        "kind":"RAILWAY_KALSHI_PUBLIC_GET_ONLY_PROSPECTIVE_SIDECAR",
        "status":status,
        **extra,
        "network_method_allowlist":["GET"],
        "credentials_accessed":"NONE",
        "authenticated_portfolio_access":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def run_kalshi_sidecar_once(
    *,
    env:Mapping[str,str]=os.environ,
    now:datetime|None=None,
    client_factory:Callable[[],object]=KalshiPublicResearchClient,
)->dict[str,object]:
    moment=_utc(now or datetime.now(timezone.utc))
    if env.get(ACTIVATION_ENV)!=(ACTIVATION_VALUE):
        return _result(
            "INACTIVE",
            filesystem_writes=False,
            network_requests=0,
        )

    root=_root(env)
    plan_path=_plan_file(root)
    client=client_factory()

    if plan_path is None:
        plan=build_prospective_kalshi_plan(
            client=client,
            planned_at=moment,
        )
        path=archive_prospective_kalshi_plan(
            plan,
            output_root=root,
        )
        return _result(
            "PRECOMMITTED_KALSHI_MARKET_PLAN",
            plan_file=path.name,
            plan_sha256=plan["plan_sha256"],
            planned_market_count=plan["planned_market_count"],
            minimum_distinct_events=plan["minimum_distinct_events"],
            filesystem_writes=True,
            network_requests=int(plan["discovery_pages"]),
        )

    plan=_load_plan(plan_path)
    snapshots=collect_due_kalshi_snapshots(
        plan=plan,
        now=moment,
        output_root=root,
        client=client,
    )
    settlements=collect_due_kalshi_settlements(
        plan=plan,
        now=moment,
        output_root=root,
        client=client,
    )
    return _result(
        "COLLECTION_TICK_COMPLETE",
        plan_sha256=plan["plan_sha256"],
        prospective_snapshots_captured=snapshots["captured_count"],
        prospective_snapshots_missed=snapshots["missed_count"],
        settlement_receipts_captured=settlements["captured_count"],
        settlements_pending=settlements["pending_count"],
        historical_backfill_count=0,
        post_settlement_decision_count=0,
        filesystem_writes=bool(
            snapshots["captured_count"] or settlements["captured_count"]
        ),
        network_requests=(
            snapshots["captured_count"]
            + settlements["network_request_count"]
        ),
    )


def main()->int:
    try:
        result=run_kalshi_sidecar_once()
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"RAILWAY_KALSHI_PUBLIC_GET_ONLY_PROSPECTIVE_SIDECAR",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "network_method_allowlist":["GET"],
            "credentials_accessed":"NONE",
            "authenticated_portfolio_access":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "automatic_live_trading":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
