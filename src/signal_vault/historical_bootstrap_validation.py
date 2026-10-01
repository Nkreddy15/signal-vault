"""Produce a frozen historical-bootstrap validation receipt for supervised PAPER.

Consumes only the existing offline three-cost historical analysis. Strategy
selection uses the validation fold only. The untouched test may veto the
validation-selected candidate but can never choose or rank a candidate.

This module performs no network access and cannot submit orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping


INPUT_KIND="HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS"
OUTPUT_KIND="CRYPTO_HISTORICAL_BOOTSTRAP_VALIDATION_RECEIPT"
BLOCKED_KIND="CRYPTO_HISTORICAL_BOOTSTRAP_VALIDATION_BLOCKED"
ACTIVE=(
    "generic-ema12x26-v1-predeclared",
    "generic-ema12x26-confirm2-v2-predeclared",
    "generic-momentum24bar50bps-v1-predeclared",
)
SCENARIOS=(
    "illustrative_low_friction",
    "illustrative_base_friction",
    "illustrative_high_friction",
)
SYMBOLS=("AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD")
MAX_BYTES=4_000_000


def _decimal(raw:object,name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite():
        raise ValueError(f"nonfinite {name}")
    return value


def _stamp(raw:object)->datetime:
    if not isinstance(raw,str) or len(raw)>64:
        raise ValueError("invalid historical timestamp")
    value=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("historical timestamp missing offset")
    return value.astimezone(timezone.utc)


def _read(path:Path)->dict[str,object]:
    src=Path(path)
    if (
        src.is_symlink() or not src.is_file()
        or not 0<src.stat().st_size<=MAX_BYTES
    ):
        raise ValueError("bounded historical analysis file required")
    value=json.loads(src.read_text())
    if not isinstance(value,dict):
        raise ValueError("historical analysis must be JSON object")
    return value


def _fold_metric(
    report:Mapping[str,object],strategy:str,fold:str,
)->dict[str,object]:
    per_asset=report.get("per_asset_disjoint_chronological_folds")
    if not isinstance(per_asset,Mapping) or set(per_asset)!=set(SYMBOLS):
        raise ValueError("exact six-crypto chronological fold map required")
    total_pnl=Decimal("0")
    total_passive=Decimal("0")
    total_fills=0
    max_drawdown=Decimal("0")
    for symbol in SYMBOLS:
        by_strategy=per_asset[symbol]
        if not isinstance(by_strategy,Mapping) or strategy not in by_strategy:
            raise ValueError("historical strategy missing from one crypto asset")
        folds=by_strategy[strategy]
        if not isinstance(folds,Mapping) or fold not in folds:
            raise ValueError("required historical fold missing")
        item=folds[fold]
        if not isinstance(item,Mapping):
            raise ValueError("historical fold must be mapping")
        total_pnl+=_decimal(item.get("net_marked_pnl_usd"),"fold pnl")
        total_passive+=_decimal(
            item.get("passive_same_allocation_marked_pnl_usd"),
            "passive comparator pnl",
        )
        dd=_decimal(item.get("max_marked_drawdown_usd"),"fold drawdown")
        if dd<0:
            raise ValueError("drawdown cannot be negative")
        max_drawdown=max(max_drawdown,dd)
        fills=item.get("fill_count")
        if type(fills) is not int or fills<0:
            raise ValueError("historical fill count must be nonnegative integer")
        total_fills+=fills
    return {
        "aggregate_net_pnl_usd":str(total_pnl),
        "aggregate_passive_pnl_usd":str(total_passive),
        "aggregate_fill_count":total_fills,
        "max_per_asset_drawdown_usd":str(max_drawdown),
    }


def _passes(metric:Mapping[str,object])->bool:
    pnl=_decimal(metric["aggregate_net_pnl_usd"],"aggregate pnl")
    passive=_decimal(metric["aggregate_passive_pnl_usd"],"aggregate passive")
    dd=_decimal(metric["max_per_asset_drawdown_usd"],"aggregate drawdown")
    fills=metric["aggregate_fill_count"]
    return (
        pnl>0
        and pnl>=passive
        and type(fills) is int
        and fills>=2
        and dd<=Decimal("10")
    )


def build_historical_bootstrap_validation(
    analysis:Mapping[str,object],
)->dict[str,object]:
    if (
        not isinstance(analysis,Mapping)
        or analysis.get("kind")!=INPUT_KIND
        or analysis.get("market")!="crypto"
        or tuple(sorted(analysis.get("symbols") or ()))!=SYMBOLS
        or analysis.get("data_is_historical_not_new_prospective_observations") is not True
        or analysis.get("independent_forward_strategy_edge_established") is not False
        or analysis.get("candidate_selection_from_untouched_test") is not False
        or analysis.get("strategy_promoted") is not False
        or analysis.get("network_requests_during_analysis")!="NONE"
        or analysis.get("credential_access_during_analysis")!="NONE"
        or analysis.get("broker_order_submission")!="DISABLED"
        or analysis.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible immutable historical-only analysis required")

    windows=analysis.get("predeclared_request_windows")
    if not isinstance(windows,list) or not windows:
        raise ValueError("historical request windows required")
    starts=[]
    ends=[]
    for item in windows:
        if not isinstance(item,Mapping):
            raise ValueError("historical window mapping required")
        starts.append(_stamp(item.get("start_utc")))
        ends.append(_stamp(item.get("end_utc")))
    start=min(starts)
    end=max(ends)
    if any(a>=b for a,b in zip(starts,ends)):
        raise ValueError("invalid historical window bounds")
    hours=int((end-start).total_seconds()//3600)
    if not 120<=hours<=168:
        return {
            "kind":BLOCKED_KIND,
            "status":"BLOCKED_HISTORY_WINDOW_NOT_5_TO_7_DAYS",
            "historical_hours":hours,
            "selected_strategy":None,
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }

    scenarios=analysis.get("scenarios")
    if not isinstance(scenarios,Mapping) or set(scenarios)!=set(SCENARIOS):
        raise ValueError("exact three historical cost scenarios required")

    validation_metrics={}
    candidate_passes={strategy:{} for strategy in ACTIVE}
    for scenario in SCENARIOS:
        wrapper=scenarios[scenario]
        report=wrapper.get("offline_report") if isinstance(wrapper,Mapping) else None
        if not isinstance(report,Mapping):
            raise ValueError("scenario offline report required")
        validation_metrics[scenario]={}
        for strategy in ACTIVE:
            metric=_fold_metric(report,strategy,"validation")
            validation_metrics[scenario][strategy]=metric
            candidate_passes[strategy][scenario]=_passes(metric)

    eligible=[
        strategy for strategy in ACTIVE
        if all(candidate_passes[strategy][scenario] for scenario in SCENARIOS)
    ]
    if len(eligible)!=1:
        return {
            "kind":BLOCKED_KIND,
            "status":(
                "BLOCKED_NO_VALIDATION_CANDIDATE"
                if not eligible else
                "BLOCKED_MULTIPLE_VALIDATION_CANDIDATES_NO_RANKING"
            ),
            "historical_hours":hours,
            "validation_candidate_passes":candidate_passes,
            "selected_strategy":None,
            "automatic_strategy_ranking":"DISABLED",
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }

    selected=eligible[0]
    test_metrics={}
    test_passes={}
    for scenario in SCENARIOS:
        wrapper=scenarios[scenario]
        report=wrapper["offline_report"]
        metric=_fold_metric(report,selected,"untouched_test")
        test_metrics[scenario]=metric
        test_passes[scenario]=_passes(metric)

    base={
        "kind":OUTPUT_KIND,
        "symbols":list(SYMBOLS),
        "historical_start_utc":start.isoformat(),
        "historical_end_utc":end.isoformat(),
        "historical_hours":hours,
        "chronological_fold_count":3,
        "selected_strategy":selected,
        "strictly_chronological":True,
        "selection_used_validation_only":True,
        "untouched_test_used_only_as_veto":True,
        "test_used_for_tuning":False,
        "historical_data_is_not_prospective_validation":True,
        "validation_candidate_passes":candidate_passes,
        "validation_metrics":validation_metrics,
        "untouched_test_metrics":test_metrics,
        "cost_stress_passes":test_passes,
        "broker_order_submission":"DISABLED",
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
        "automatic_strategy_promotion":"DISABLED",
    }
    if not all(test_passes.values()):
        return {
            "kind":BLOCKED_KIND,
            "status":"BLOCKED_UNTOUCHED_TEST_VETO",
            "historical_hours":hours,
            "selected_strategy":selected,
            "selection_used_validation_only":True,
            "untouched_test_used_only_as_veto":True,
            "untouched_test_metrics":test_metrics,
            "cost_stress_passes":test_passes,
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
    raw=json.dumps(base,sort_keys=True,separators=(",",":")).encode()
    return {
        **base,
        "receipt_sha256":hashlib.sha256(raw).hexdigest(),
    }


def _write_once(path:Path,obj:Mapping[str,object])->None:
    target=Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("bootstrap validation output already exists")
    raw=(json.dumps(dict(obj),sort_keys=True,indent=2)+"\n").encode()
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(target,flags,0o600)
    with os.fdopen(fd,"wb") as handle:
        os.fchmod(handle.fileno(),0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Offline six-day historical bootstrap validator for supervised PAPER"
    )
    parser.add_argument("analysis",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=build_historical_bootstrap_validation(_read(args.analysis))
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
