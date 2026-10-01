"""Retrospective screening for predeclared low-churn cross-sectional crypto allocators."""
from __future__ import annotations

import argparse, json, os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .cross_sectional_crypto_research import (
    CrossSectionalConfig, SYMBOLS, simulate_cross_sectional_strength,
)
from .offline_multimarket_pipeline import combine_historical_archives, read_historical_archive

SCENARIOS={
    "illustrative_low_friction":("15","2","5"),
    "illustrative_base_friction":("25","4","10"),
    "illustrative_high_friction":("40","12","20"),
}

CANDIDATES={
    "cross-sectional-top1-168h-250bps-weekly-v1-predeclared": dict(
        lookback_bars=168,top_n=1,min_strength_bps=Decimal("250"),
        rebalance_interval_bars=168,
    ),
    "cross-sectional-top2-168h-250bps-weekly-v1-predeclared": dict(
        lookback_bars=168,top_n=2,min_strength_bps=Decimal("250"),
        rebalance_interval_bars=168,
    ),
}


def _load(folder:Path):
    files=sorted(folder.glob("historical-crypto-*.json"))
    if not files:
        raise ValueError("historical archives required")
    batches=tuple(read_historical_archive(p) for p in files)
    as_of=max(datetime.fromisoformat(b.downloaded_utc) for b in batches).astimezone(timezone.utc)
    datasets,_=combine_historical_archives(batches,as_of=as_of)
    if set(datasets)!=set(SYMBOLS):
        raise ValueError("exact six crypto required")
    n={len(v) for v in datasets.values()}
    if len(n)!=1 or next(iter(n))!=2160:
        raise ValueError("exact aligned 90-day hourly history required")
    return datasets,2160


def _passes(x:dict[str,object])->bool:
    return (
        Decimal(x["net_marked_pnl_usd"])>0 and
        Decimal(x["net_marked_pnl_usd"])>=Decimal(x["passive_equal_weight_marked_pnl_usd"]) and
        x["fill_count"]>=2 and
        Decimal(x["max_marked_drawdown_usd"])<=Decimal("10")
    )


def build_review(folder:Path)->dict[str,object]:
    data,n=_load(folder)
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
    for candidate_name,params in CANDIDATES.items():
        results[candidate_name]={}
        support[candidate_name]={}
        for scenario,(fee,spread,slip) in SCENARIOS.items():
            cfg=CrossSectionalConfig(
                **params,
                fee_bps=Decimal(fee),full_spread_bps=Decimal(spread),
                slippage_bps=Decimal(slip),
            )
            results[candidate_name][scenario]={}
            for fold,(a,b) in folds.items():
                results[candidate_name][scenario][fold]=simulate_cross_sectional_strength(
                    data,config=cfg,evaluation_start_index=a,evaluation_end_index=b)
            support[candidate_name][scenario]=all(
                _passes(results[candidate_name][scenario][fold])
                for fold in ("development","validation")
            )
    eligible=[
        name for name in CANDIDATES
        if all(support[name].values())
    ]
    if len(eligible)==1:
        status="ONE_LOW_CHURN_CANDIDATE_FROZEN_FOR_NEW_PROSPECTIVE_CONFIRMATION"
        selected=eligible[0]
    elif len(eligible)>1:
        status="BLOCKED_MULTIPLE_LOW_CHURN_CANDIDATES_NO_RANKING"
        selected=None
    else:
        status="BLOCKED_NO_LOW_CHURN_CANDIDATE"
        selected=None
    return {
        "kind":"CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
        "status":status,
        "historical_hours":2160,
        "candidate_support_development_and_validation":support,
        "selected_strategy":selected,
        "automatic_strategy_ranking":"DISABLED",
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
            "kind":"CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "broker_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
