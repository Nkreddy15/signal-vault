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
MAX_PUBLIC_GETS_PER_TICK=25
# The frozen prospective gate requires >=20 valid markets and >=90% coverage.
# Planning 22 lets up to two markets fail prospectively while 20/22 still
# exceeds the coverage floor. The first 20 valid markets remain the scoring set.
CLOUD_PLANNED_MARKET_COUNT=22

_PLAN_FAILURE_CODES={
    "Kalshi discovery lacks ten distinct future events":
        "INSUFFICIENT_DISTINCT_FUTURE_EVENTS",
    "Kalshi discovery lacks requested prospective market count":
        "INSUFFICIENT_ELIGIBLE_FUTURE_MARKETS",
    "Kalshi public discovery exceeded bounded pages":
        "DISCOVERY_PAGE_LIMIT_EXCEEDED",
    "duplicate Kalshi market across discovery pages":
        "DUPLICATE_MARKET_ACROSS_DISCOVERY_PAGES",
    "Kalshi public market discovery lacks markets":
        "MALFORMED_PUBLIC_MARKET_DISCOVERY",
    "malformed Kalshi public market":
        "MALFORMED_PUBLIC_MARKET_OBJECT",
}


class _BudgetedPublicClient:
    def __init__(self,inner:object, *, maximum:int=MAX_PUBLIC_GETS_PER_TICK):
        if type(maximum) is not int or maximum<=0:
            raise ValueError("positive Kalshi public GET budget required")
        self._inner=inner
        self._maximum=maximum
        self.request_count=0
        self.supports_event_discovery=callable(
            getattr(inner,"live_public_events",None)
        )

    def _consume(self)->None:
        if self.request_count>=self._maximum:
            raise RuntimeError("Kalshi public GET per-tick budget exhausted")
        self.request_count+=1

    def live_public_markets(self, **kwargs:object)->dict[str,object]:
        self._consume()
        method=getattr(self._inner,"live_public_markets",None)
        if not callable(method):
            raise TypeError("Kalshi public client lacks market discovery")
        return method(**kwargs)

    def live_public_markets_close_window(self, **kwargs:object)->dict[str,object]:
        method=getattr(self._inner,"live_public_markets_close_window",None)
        if callable(method):
            self._consume()
            return method(**kwargs)
        # Backward-compatible fallback for deterministic test doubles and
        # older injected research clients. Production uses the bounded
        # close-window method on KalshiPublicResearchClient.
        self._consume()
        fallback=getattr(self._inner,"live_public_markets",None)
        if not callable(fallback):
            raise TypeError("Kalshi public client lacks market discovery")
        return fallback(
            status="open",
            limit=kwargs.get("limit",1000),
            cursor=kwargs.get("cursor"),
        )

    def live_public_events(self, **kwargs:object)->dict[str,object]:
        self._consume()
        method=getattr(self._inner,"live_public_events",None)
        if not callable(method):
            raise TypeError("Kalshi public client lacks event discovery")
        return method(**kwargs)

    def live_public_market(self,ticker:str)->dict[str,object]:
        self._consume()
        method=getattr(self._inner,"live_public_market",None)
        if not callable(method):
            raise TypeError("Kalshi public client lacks single-market lookup")
        return method(ticker)


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
    client=_BudgetedPublicClient(client_factory())

    if plan_path is None:
        try:
            plan=build_prospective_kalshi_plan(
                client=client,
                planned_at=moment,
                market_count=CLOUD_PLANNED_MARKET_COUNT,
            )
        except ValueError as exc:
            message=str(exc)
            return _result(
                "PLANNING_BLOCKED_FAIL_CLOSED",
                failure_class="ValueError",
                planning_failure_code=_PLAN_FAILURE_CODES.get(
                    message,"OTHER_STRUCTURAL_PLAN_VALIDATION_FAILURE"
                ),
                filesystem_writes=False,
                network_requests=client.request_count,
                public_get_budget=MAX_PUBLIC_GETS_PER_TICK,
                public_get_requests_used=client.request_count,
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
            planned_buffer_markets=(
                int(plan["planned_market_count"])-20
            ),
            filesystem_writes=True,
            network_requests=client.request_count,
            public_get_budget=MAX_PUBLIC_GETS_PER_TICK,
            public_get_requests_used=client.request_count,
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
        network_requests=client.request_count,
        public_get_budget=MAX_PUBLIC_GETS_PER_TICK,
        public_get_requests_used=client.request_count,
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
