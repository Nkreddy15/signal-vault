"""Long-horizon crypto candidate review for research-only strategy freezing.

Consumes an offline six-crypto historical report covering exactly 90 days that
ends before the later six-day bootstrap/confirmation period. Candidate support
must exist in BOTH development and validation folds across all three fixed cost
scenarios. The untouched test can only veto the one validation-supported
candidate; it never selects or ranks alternatives.

No network, credentials, PAPER execution, or LIVE path exists here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

INPUT_KIND="HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS"
OUTPUT_KIND="CRYPTO_LONG_HORIZON_CANDIDATE_RESEARCH_RECEIPT"
BLOCKED_KIND="CRYPTO_LONG_HORIZON_CANDIDATE_RESEARCH_BLOCKED"
CANDIDATES=(
    "generic-ema12x26-v1-predeclared",
    "generic-ema12x26-confirm2-v2-predeclared",
    "generic-momentum24bar50bps-v1-predeclared",
    "generic-ema24x72-v1-predeclared",
    "generic-ema24x72-confirm2-v1-predeclared",
    "generic-momentum72bar150bps-v1-predeclared",
    "generic-momentum168bar250bps-v1-predeclared",
)
SCENARIOS=(
    "illustrative_low_friction",
    "illustrative_base_friction",
    "illustrative_high_friction",
)
SYMBOLS=("AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD")
EXPECTED_HOURS=2160
MIN_AGGREGATE_FILLS=6
MAX_PER_ASSET_DRAWDOWN=Decimal("10")
MAX_BYTES=5_000_000


def _decimal(raw:object,name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite():
        raise ValueError(f"nonfinite {name}")
    return value


def _read(path:Path)->dict[str,object]:
    src=Path(path)
    if src.is_symlink() or not src.is_file() or not 0<src.stat().st_size<=MAX_BYTES:
        raise ValueError("bounded historical analysis file required")
    value=json.loads(src.read_text())
    if not isinstance(value,dict):
        raise ValueError("historical analysis must be object")
    return value


def _hours(analysis:Mapping[str,object])->int:
    windows=analysis.get("predeclared_request_windows")
    if not isinstance(windows,list) or not windows:
        raise ValueError("historical request windows required")
    from datetime import datetime, timezone
    def stamp(raw:object):
        if not isinstance(raw,str):
            raise ValueError("timestamp required")
        v=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("timezone-aware timestamp required")
        return v.astimezone(timezone.utc)
    starts=[stamp(x["start_utc"]) for x in windows if isinstance(x,Mapping)]
    ends=[stamp(x["end_utc"]) for x in windows if isinstance(x,Mapping)]
    if len(starts)!=len(windows) or any(a>=b for a,b in zip(starts,ends)):
        raise ValueError("invalid historical windows")
    start=min(starts); end=max(ends)
    if any(b!=c for b,c in zip(ends[:-1],starts[1:])):
        raise ValueError("long-horizon windows must be contiguous")
    return int((end-start).total_seconds()//3600)


def _metric(report:Mapping[str,object],strategy:str,fold:str)->dict[str,object]:
    per_asset=report.get("per_asset_disjoint_chronological_folds")
    if not isinstance(per_asset,Mapping) or set(per_asset)!=set(SYMBOLS):
        raise ValueError("exact six-crypto fold map required")
    pnl=Decimal("0"); passive=Decimal("0"); fills=0; maxdd=Decimal("0")
    for symbol in SYMBOLS:
        by=per_asset[symbol]
        if not isinstance(by,Mapping) or strategy not in by:
            raise ValueError("candidate missing from long-horizon report")
        folds=by[strategy]
        if not isinstance(folds,Mapping) or fold not in folds:
            raise ValueError("required fold missing")
        item=folds[fold]
        if not isinstance(item,Mapping):
            raise ValueError("fold must be object")
        pnl+=_decimal(item.get("net_marked_pnl_usd"),"net pnl")
        passive+=_decimal(item.get("passive_same_allocation_marked_pnl_usd"),"passive pnl")
        dd=_decimal(item.get("max_marked_drawdown_usd"),"drawdown")
        if dd<0:
            raise ValueError("drawdown cannot be negative")
        maxdd=max(maxdd,dd)
        count=item.get("fill_count")
        if type(count) is not int or count<0:
            raise ValueError("fill count invalid")
        fills+=count
    return {
        "aggregate_net_pnl_usd":str(pnl),
        "aggregate_passive_pnl_usd":str(passive),
        "aggregate_fill_count":fills,
        "max_per_asset_drawdown_usd":str(maxdd),
    }


def _passes(metric:Mapping[str,object])->bool:
    return (
        _decimal(metric["aggregate_net_pnl_usd"],"aggregate pnl")>0
        and _decimal(metric["aggregate_net_pnl_usd"],"aggregate pnl")
            >=_decimal(metric["aggregate_passive_pnl_usd"],"passive")
        and type(metric.get("aggregate_fill_count")) is int
        and metric["aggregate_fill_count"]>=MIN_AGGREGATE_FILLS
        and _decimal(metric["max_per_asset_drawdown_usd"],"drawdown")
            <=MAX_PER_ASSET_DRAWDOWN
    )


def build_long_horizon_candidate_review(analysis:Mapping[str,object])->dict[str,object]:
    if (
        not isinstance(analysis,Mapping)
        or analysis.get("kind")!=INPUT_KIND
        or analysis.get("market")!="crypto"
        or tuple(sorted(analysis.get("symbols") or ()))!=SYMBOLS
        or analysis.get("data_is_historical_not_new_prospective_observations") is not True
        or analysis.get("candidate_selection_from_untouched_test") is not False
        or analysis.get("strategy_promoted") is not False
        or analysis.get("network_requests_during_analysis")!="NONE"
        or analysis.get("credential_access_during_analysis")!="NONE"
        or analysis.get("broker_order_submission")!="DISABLED"
        or analysis.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible historical-only analysis required")
    hours=_hours(analysis)
    if hours!=EXPECTED_HOURS:
        return {
            "kind":BLOCKED_KIND,
            "status":"BLOCKED_LONG_HORIZON_NOT_EXACTLY_90_DAYS",
            "historical_hours":hours,
            "selected_strategy":None,
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
    scenarios=analysis.get("scenarios")
    if not isinstance(scenarios,Mapping) or set(scenarios)!=set(SCENARIOS):
        raise ValueError("exact three cost scenarios required")

    metrics={}
    support={s:{} for s in CANDIDATES}
    for scenario in SCENARIOS:
        wrapper=scenarios[scenario]
        report=wrapper.get("offline_report") if isinstance(wrapper,Mapping) else None
        if not isinstance(report,Mapping):
            raise ValueError("scenario report required")
        metrics[scenario]={}
        for strategy in CANDIDATES:
            dev=_metric(report,strategy,"development")
            val=_metric(report,strategy,"validation")
            metrics[scenario][strategy]={"development":dev,"validation":val}
            support[strategy][scenario]={
                "development":_passes(dev),
                "validation":_passes(val),
            }

    eligible=[
        strategy for strategy in CANDIDATES
        if all(
            support[strategy][scenario]["development"]
            and support[strategy][scenario]["validation"]
            for scenario in SCENARIOS
        )
    ]
    if len(eligible)!=1:
        return {
            "kind":BLOCKED_KIND,
            "status":(
                "BLOCKED_NO_LONG_HORIZON_CANDIDATE"
                if not eligible else
                "BLOCKED_MULTIPLE_LONG_HORIZON_CANDIDATES_NO_RANKING"
            ),
            "historical_hours":hours,
            "candidate_support":support,
            "selected_strategy":None,
            "automatic_strategy_ranking":"DISABLED",
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }

    selected=eligible[0]
    test_metrics={}; test_pass={}
    for scenario in SCENARIOS:
        report=scenarios[scenario]["offline_report"]
        metric=_metric(report,selected,"untouched_test")
        test_metrics[scenario]=metric
        test_pass[scenario]=_passes(metric)
    if not all(test_pass.values()):
        return {
            "kind":BLOCKED_KIND,
            "status":"BLOCKED_LONG_HORIZON_UNTOUCHED_TEST_VETO",
            "historical_hours":hours,
            "selected_strategy":selected,
            "untouched_test_used_only_as_veto":True,
            "untouched_test_passes":test_pass,
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }

    base={
        "kind":OUTPUT_KIND,
        "status":"ONE_LONG_HORIZON_CANDIDATE_FROZEN_FOR_LATER_CONFIRMATION",
        "historical_hours":hours,
        "selected_strategy":selected,
        "candidate_support":support,
        "untouched_test_metrics":test_metrics,
        "untouched_test_passes":test_pass,
        "selection_used_development_and_validation_only":True,
        "untouched_test_used_only_as_veto":True,
        "six_day_confirmation_still_required":True,
        "paper_activation_permitted":False,
        "paper_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    raw=json.dumps(base,sort_keys=True,separators=(",",":")).encode()
    return {**base,"receipt_sha256":hashlib.sha256(raw).hexdigest()}


def _write_once(path:Path,obj:Mapping[str,object])->None:
    target=Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("output already exists")
    raw=(json.dumps(dict(obj),sort_keys=True,indent=2)+"\n").encode()
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(target,flags,0o600)
    with os.fdopen(fd,"wb") as handle:
        os.fchmod(handle.fileno(),0o600)
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="90-day crypto candidate research review; no orders")
    p.add_argument("analysis",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=build_long_horizon_candidate_review(_read(args.analysis))
        _write_once(args.output,result)
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0 if result.get("kind")==OUTPUT_KIND else 3
    except Exception as exc:
        print(json.dumps({
            "kind":BLOCKED_KIND,
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
