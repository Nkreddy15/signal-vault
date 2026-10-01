"""CLI review for predeclared cross-sectional crypto allocator on 90-day history."""
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
    if len(n)!=1:
        raise ValueError("aligned six-crypto length required")
    count=next(iter(n))
    if count!=2160:
        raise ValueError("exact 90-day hourly history required")
    return datasets,count


def build_review(folder:Path)->dict[str,object]:
    data,n=_load(folder)
    warm=73
    usable=n-warm
    dev_end=warm+usable//2
    val_end=dev_end+usable//4
    folds={"development":(warm,dev_end),"validation":(dev_end,val_end),"untouched_test":(val_end,n)}
    results={}
    validation_support={}
    for name,(fee,spread,slip) in SCENARIOS.items():
        cfg=CrossSectionalConfig(
            fee_bps=Decimal(fee),full_spread_bps=Decimal(spread),
            slippage_bps=Decimal(slip),
        )
        results[name]={}
        for fold,(a,b) in folds.items():
            results[name][fold]=simulate_cross_sectional_strength(
                data,config=cfg,evaluation_start_index=a,evaluation_end_index=b)
        validation_support[name]=all(
            Decimal(results[name][fold]["net_marked_pnl_usd"])>0 and
            Decimal(results[name][fold]["net_marked_pnl_usd"])>=
                Decimal(results[name][fold]["passive_equal_weight_marked_pnl_usd"]) and
            results[name][fold]["fill_count"]>=2 and
            Decimal(results[name][fold]["max_marked_drawdown_usd"])<=Decimal("10")
            for fold in ("development","validation")
        )
    pre_test=all(validation_support.values())
    test_passes={}
    if pre_test:
        for name in SCENARIOS:
            x=results[name]["untouched_test"]
            test_passes[name]=(
                Decimal(x["net_marked_pnl_usd"])>0 and
                Decimal(x["net_marked_pnl_usd"])>=Decimal(x["passive_equal_weight_marked_pnl_usd"]) and
                x["fill_count"]>=2 and
                Decimal(x["max_marked_drawdown_usd"])<=Decimal("10")
            )
    status=(
        "CROSS_SECTIONAL_CANDIDATE_FROZEN_FOR_LATER_CONFIRMATION"
        if pre_test and all(test_passes.values()) else
        "BLOCKED_CROSS_SECTIONAL_CANDIDATE"
    )
    return {
        "kind":"CRYPTO_90DAY_CROSS_SECTIONAL_RESEARCH_RECEIPT",
        "status":status,
        "strategy":"cross-sectional-top2-72h-150bps-daily-v1-predeclared",
        "historical_hours":2160,
        "development_and_validation_pass_all_costs":validation_support,
        "untouched_test_used_only_as_veto":True,
        "untouched_test_passes":test_passes,
        "results":results,
        "six_day_confirmation_still_required":True,
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
        with os.fdopen(fd,"wb") as f:
            os.fchmod(f.fileno(),0o600);f.write(raw);f.flush();os.fsync(f.fileno())
        print(json.dumps({k:v for k,v in result.items() if k!="results"},sort_keys=True,indent=2))
        return 0 if result["status"].startswith("CROSS_SECTIONAL_") else 3
    except Exception as exc:
        print(json.dumps({
            "kind":"CRYPTO_90DAY_CROSS_SECTIONAL_RESEARCH_RECEIPT",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "broker_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
