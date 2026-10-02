"""Retrospective 90-day review for one breadth-gated strength tilt."""
from __future__ import annotations

import argparse, json, os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .offline_multimarket_pipeline import combine_historical_archives, read_historical_archive
from .regime_gated_strength_tilt_research import (
    SYMBOLS, RegimeTiltConfig, simulate_regime_tilt,
)

SCENARIOS={
    "illustrative_low_friction":("15","2","5"),
    "illustrative_base_friction":("25","4","10"),
    "illustrative_high_friction":("40","12","20"),
}
STRATEGY="equal-weight-unless-4of6-positive-168h-top2-10x2.5-weekly-v1-predeclared"


def _load(folder:Path):
    files=sorted(folder.glob("historical-crypto-*.json"))
    if not files:
        raise ValueError("historical archives required")
    batches=tuple(read_historical_archive(p) for p in files)
    as_of=max(datetime.fromisoformat(b.downloaded_utc) for b in batches).astimezone(timezone.utc)
    datasets,_=combine_historical_archives(batches,as_of=as_of)
    if set(datasets)!=set(SYMBOLS) or {len(v) for v in datasets.values()}!={2160}:
        raise ValueError("exact aligned 90-day six-crypto history required")
    return datasets


def _passes(x:dict[str,object])->bool:
    return (
        Decimal(x["net_marked_pnl_usd"])>0 and
        Decimal(x["net_marked_pnl_usd"])>=Decimal(x["passive_equal_weight_marked_pnl_usd"]) and
        int(x["fill_count"])>=6 and
        Decimal(x["max_marked_drawdown_usd"])<=Decimal("10")
    )


def build_review(folder:Path)->dict[str,object]:
    data=_load(folder)
    n=2160
    warm=169
    usable=n-warm
    dev_end=warm+usable//2
    val_end=dev_end+usable//4
    folds={
        "development":(warm,dev_end),
        "validation":(dev_end,val_end),
        "historical_holdout_descriptive_only":(val_end,n),
    }
    results={}
    support={}
    for scenario,(fee,spread,slip) in SCENARIOS.items():
        cfg=RegimeTiltConfig(
            fee_bps=Decimal(fee),
            full_spread_bps=Decimal(spread),
            slippage_bps=Decimal(slip),
        )
        results[scenario]={}
        for fold,(a,b) in folds.items():
            results[scenario][fold]=simulate_regime_tilt(
                data,config=cfg,evaluation_start_index=a,evaluation_end_index=b
            )
        support[scenario]=all(
            _passes(results[scenario][fold]) for fold in ("development","validation")
        )
    passed=all(support.values())
    return {
        "kind":"CRYPTO_90DAY_REGIME_GATED_STRENGTH_TILT_RESEARCH_RECEIPT",
        "status":(
            "ONE_REGIME_GATED_STRENGTH_TILT_FROZEN_FOR_NEW_PROSPECTIVE_CONFIRMATION"
            if passed else
            "BLOCKED_REGIME_GATED_STRENGTH_TILT"
        ),
        "strategy":STRATEGY,
        "historical_hours":2160,
        "development_and_validation_pass_all_costs":support,
        "historical_holdout_is_descriptive_not_pristine":True,
        "historical_holdout_never_selects_or_vetoes":True,
        "results":results,
        "new_prospective_confirmation_required":True,
        "paper_activation_permitted":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main(argv=None)->int:
    p=argparse.ArgumentParser()
    p.add_argument("folder",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=build_review(args.folder)
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("output already exists")
        raw=(json.dumps(result,sort_keys=True,indent=2)+"\n").encode()
        fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as fh:
            os.fchmod(fh.fileno(),0o600);fh.write(raw);fh.flush();os.fsync(fh.fileno())
        print(json.dumps({k:v for k,v in result.items() if k!="results"},sort_keys=True,indent=2))
        return 0 if result["status"].startswith("ONE_") else 3
    except Exception as exc:
        print(json.dumps({
            "kind":"CRYPTO_90DAY_REGIME_GATED_STRENGTH_TILT_RESEARCH_RECEIPT",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "broker_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
