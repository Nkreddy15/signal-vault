"""Explicit MANUAL, bounded US-equity historical IEX DATA GET, no orders.

Only complete core-session clock-hour buckets are requested so the API's
09:00-10:00 ET hourly bucket cannot mix 09:00-09:30 premarket trades with
regular-session data. One request per independently computed XNYS session,
up to 25 sessions, 1-6 liquid predeclared stocks/ETFs. Full coverage from
IEX is NOT assumed: missing or unexpected symbols/hour timestamps make the
entire session fail closed. NO SIP entitlement assumed or purchased.

The existing private dedicated PAPER historical DATA GitHub Actions secrets
are accessed ONLY in an explicitly manually dispatched main-branch workflow
step. No Railway, no Keychain, no account/broker host, no POST or auto orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping

from .ci_historical_crypto import KEY_ENV,SECRET_ENV,BLOCK_EXTRA
from .equity_session_grid import conservative_core_hour_plan
from .multi_asset_historical import (
    BoundedAlpacaHistoricalBatch, archive_historical_batch,
)
from .multi_asset_simulation import ExplicitRoundTripCosts
from .offline_multimarket_pipeline import (
    combine_historical_archives, describe_multi_asset_research,
    read_historical_archive,
)
from .research_universe import AssetClass,candidate,validate_asset_dataset

SYMBOLS=("AAPL","AMD","MSFT","NVDA","QQQ","SPY")
ROOT=Path("private-equity-artifacts")
APPROVAL="HISTORICAL_IEX_XNYS_FULL_CORE_HOURS_DATA_GET_ONLY"

EQUITY_ESTIMATED_COST_SCENARIOS={
    # Illustrations, not actual spreads/exchange fees/commissions or predictions.
    "illustrative_low_equity_friction":{
        "taker_fee_bps":"0","full_spread_bps":"1",
        "slippage_per_side_bps":"2",
    },
    "illustrative_base_equity_friction":{
        "taker_fee_bps":"0","full_spread_bps":"3",
        "slippage_per_side_bps":"5",
    },
    "illustrative_high_equity_friction":{
        "taker_fee_bps":"2","full_spread_bps":"10",
        "slippage_per_side_bps":"12",
    },
}


def _date(raw: str) -> date:
    if (not isinstance(raw,str) or len(raw)!=10 or
            raw[4:5]!="-" or raw[7:8]!="-"):
        raise ValueError("explicit ISO session date required")
    return date.fromisoformat(raw)


def resolve_manual_equity_plan(
    *, env:Mapping[str,str], as_of:datetime,
) -> dict[str,object]:
    if (env.get("GITHUB_ACTIONS")!="true" or
            env.get("GITHUB_EVENT_NAME")!="workflow_dispatch" or
            env.get("GITHUB_REPOSITORY")!="Nkreddy15/signal-vault" or
            env.get("GITHUB_REF")!="refs/heads/main" or
            env.get("SIGNAL_VAULT_EQUITY_READ_APPROVED")!=APPROVAL or
            env.get("SIGNAL_VAULT_EQUITY_FEED")!="iex" or
            any(str(env.get(name,"")).strip() for name in BLOCK_EXTRA)):
        raise PermissionError("explicit private main-only IEX research approval required")
    submitted=tuple(env.get("SIGNAL_VAULT_EQUITY_SYMBOLS","").split())
    if (submitted!=SYMBOLS or
            any(candidate(s).asset_class!=AssetClass.US_EQUITY
                for s in submitted)):
        raise ValueError("exact six predeclared equity research candidates required")
    sessions=conservative_core_hour_plan(
        start_date=_date(env.get("SIGNAL_VAULT_EQUITY_START_DATE","")),
        end_date_exclusive=_date(env.get("SIGNAL_VAULT_EQUITY_END_DATE_EXCLUSIVE","")),
        as_of=as_of)
    if sum(len(s.expected_opens) for s in sessions)<56:
        raise ValueError("stock plan needs >=56 complete core hours for chronological research")
    return {
        "kind":"OFFLINE_MANUAL_XNYS_CORE_HOURLY_IEX_DATA_ONLY_PLAN",
        "market":"us_equity",
        "feed":"iex",
        "symbols":list(submitted),
        "sessions":[s.as_dict() for s in sessions],
        "expected_complete_core_hours_per_symbol":
            sum(len(s.expected_opens) for s in sessions),
        "session_count":len(sessions),
        "preopen_0930_to_1000_intentionally_omitted":True,
        "weekends_holidays_early_closes_calendar_checked":True,
        "sip_entitlement_assumed":False,
        "credentials_accessed":"NONE",
        "network_requests":0,
        "broker_order_submission":"DISABLED",
    }


def _create_private_folder(root: Path) -> None:
    if root.exists() or root.is_symlink():
        raise ValueError("historical equity output must be NEW and separate")
    root.mkdir(mode=0o700)
    if root.stat().st_mode&0o077:
        raise PermissionError("equity research archive root must be private")


def _write_once(path:Path,raw:bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("immutable equity research file collision")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw);fh.flush();os.fsync(fh.fileno())


def execute_manual_equity_history(
    *,
    env:Mapping[str,str],
    as_of:datetime,
    provider_factory:Callable[...,BoundedAlpacaHistoricalBatch]=BoundedAlpacaHistoricalBatch,
    output_folder:Path=ROOT,
) -> dict[str,object]:
    """Fully historical, bounded, pure IEX GET; no unverified empty IEX buckets."""
    plan=resolve_manual_equity_plan(env=env,as_of=as_of)
    key,secret=env.get(KEY_ENV),env.get(SECRET_ENV)
    if (not isinstance(key,str) or not isinstance(secret,str) or
            not key.strip() or not secret.strip() or key!=key.strip() or
            secret!=secret.strip()):
        raise PermissionError("dedicated PRIVATE historical PAPER DATA keys absent")
    if not isinstance(as_of,datetime) or as_of.tzinfo is None:
        raise ValueError("explicit retrospective capture timestamp required")
    _create_private_folder(output_folder)
    # Reconstruct from the verified source (no human-edited source grid) so
    # the plan's independent calendar identity and version are not discarded.
    sessions=conservative_core_hour_plan(
        start_date=_date(env["SIGNAL_VAULT_EQUITY_START_DATE"]),
        end_date_exclusive=_date(env["SIGNAL_VAULT_EQUITY_END_DATE_EXCLUSIVE"]),
        as_of=as_of)
    provider=provider_factory(key,secret)
    archived=[]
    validated={}
    for spec in sessions:
        expected={sym:spec.expected_opens for sym in SYMBOLS}
        batch=provider.fetch(
            specs=tuple(candidate(sym) for sym in SYMBOLS),
            start=spec.query_start,end=spec.query_end,as_of=as_of,
            equity_feed="iex",equity_expected_open_minutes=expected)
        if (batch.asset_class!="us_equity" or
                batch.feed!="alpaca_equity_iex" or
                batch.adjustment!="all" or
                set(batch.bars)!=set(SYMBOLS)):
            raise ValueError("not an explicitly provenance-checked IEX equity bundle")
        # Independently recheck the returned bundle's source, OHLCV and each
        # exact XNYS regular-core bucket before writing an immutable archive.
        # This deliberately catches sparse IEX hours rather than interpolating
        # or mislabeling the provider as consolidated SIP.
        for symbol in SYMBOLS:
            review=validate_asset_dataset(
                batch.bars[symbol],spec=candidate(symbol),as_of=as_of,
                expected_session_opens_utc=expected[symbol])
            if (review.feed!="alpaca_equity_iex|adjustment=all" or
                    review.bar_count!=len(spec.expected_opens)):
                raise ValueError("IEX provider hour/count/provenance mismatch")
        filename=archive_historical_batch(batch,output_folder=output_folder)
        archived.append(filename)
    if len(archived)!=len(sessions):
        raise ValueError("not all bounded XNYS sessions were archived")
    parts=tuple(read_historical_archive(path) for path in archived)
    whole_grid=tuple(at for session in sessions for at in session.expected_opens)
    calendars={sym:whole_grid for sym in SYMBOLS}
    datasets,reviews=combine_historical_archives(
        parts,as_of=as_of,equity_calendars=calendars)
    expected=len(whole_grid)
    if (set(reviews)!=set(SYMBOLS) or
            any(review["bar_count"]!=expected or
                review["historical_bars"]!=expected or
                review["prospective_bars"]!=0 or
                review["feed"]!="alpaca_equity_iex|adjustment=all"
                for review in reviews.values())):
        raise ValueError("equity source/report bar provenance mismatch")
    scenarios={}
    for scenario,values in EQUITY_ESTIMATED_COST_SCENARIOS.items():
        explicit=ExplicitRoundTripCosts(
            Decimal(values["taker_fee_bps"]),
            Decimal(values["full_spread_bps"]),
            Decimal(values["slippage_per_side_bps"]))
        complete=describe_multi_asset_research(
            datasets,as_of=as_of,
            costs={sym:explicit for sym in SYMBOLS},
            equity_calendars=calendars)
        if complete["broker_order_submission"]!="DISABLED":
            raise ValueError("stock research reporting must remain offline")
        scenarios[scenario]={
            "explicit_assumptions_by_symbol":{
                sym:dict(values) for sym in SYMBOLS},
            "assumptions_are_illustrative_not_measured_IEX_quotes":True,
            "offline_report":complete,
        }
    record={
        "kind":"MANUAL_HISTORICAL_XNYS_IEX_CORE_HOUR_MULTIMARKET_RESEARCH",
        "schema_version":1,
        "market":"us_equity",
        "feed":"alpaca_equity_iex",
        "stock_adjustment":"all",
        "symbols":list(SYMBOLS),
        "exchange_calendar_session_plan":plan,
        "expected_hourly_regular_core_buckets_per_asset":expected,
        "source_sha256":[{
            "filename":path.name,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        } for path in archived],
        "quality_reviews":reviews,
        "three_estimated_cost_scenarios":scenarios,
        "regular_opening_partial_bucket_omitted":True,
        "sparse_IEX_data_cannot_be_auto_filled":True,
        "no_claim_to_consolidated_SIP_data":True,
        "provider_entitlement_inferred_only_from_successful_IEX_GET":True,
        "historical_no_prospective_forward_observations":True,
        "strategy_validated":False,
        "credential_values_in_output":False,
        "network_calls_other_than_explicit_fixed_IEX_data_GET":"NONE",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    result=(json.dumps(record,indent=2,sort_keys=True)+"\n").encode("utf-8")
    _write_once(output_folder/"offline_equity_research.json",result)
    return {
        "kind":"COMPLETED_IEX_ONLY_XNYS_CORE_FULL_HOUR_RESEARCH",
        "market":"us_equity",
        "symbols":list(SYMBOLS),
        "feed":"iex",
        "completed_exchange_sessions":len(archived),
        "historical_bars_per_asset":expected,
        "report_sha256":hashlib.sha256(result).hexdigest(),
        "archive_count":len(archived),
        "key_values_in_logs":False,
        "prospective_observations_verified":0,
        "broker_order_submission":"DISABLED",
    }


def main(argv:list[str]|None=None) -> int:
    p=argparse.ArgumentParser(
        description="MANUAL ONLY XNYS core-hour IEX historical DATA GET; no orders")
    flags=p.add_mutually_exclusive_group(required=True)
    flags.add_argument("--dry-run",action="store_true")
    flags.add_argument("--download-history",action="store_true")
    args=p.parse_args(argv)
    now=datetime.now(timezone.utc)
    try:
        if args.dry_run:
            result=resolve_manual_equity_plan(env=os.environ,as_of=now)
        else:
            result=execute_manual_equity_history(env=os.environ,as_of=now)
        print(json.dumps(result,indent=2,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"MANUAL_XNYS_IEX_HISTORICAL_ONLY",
            "status":"FAIL_CLOSED_NO_COMPLETE_EQUITY_DATASET_CLAIM",
            "failure_class":type(exc).__name__,
            "credential_values_in_output":False,
            "no_SIP_or_broker_order_calls":True,
            "broker_order_submission":"DISABLED",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
