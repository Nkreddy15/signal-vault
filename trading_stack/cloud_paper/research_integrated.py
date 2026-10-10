"""One frozen comparison; all costs/scenarios reported, no automatic promotion."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

from .engine import load_config
from .providers import Kraken, iso
from .research import load_archive, precompute, replay
from .store import digest


def capture(config, output):
    client=Kraken();client.load_assets();captured=time.time()
    missing=set(config["crypto_symbols"])-set(client.assets)
    if missing:raise ValueError("Unsupported configured symbols: "+repr(sorted(missing)))
    data={};errors={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(client.bars,symbol,captured,"4h"):symbol for symbol in config["crypto_symbols"]}
        for job in as_completed(jobs):
            symbol=jobs[job]
            try:data[symbol]=job.result()
            except Exception as error:errors[symbol]=type(error).__name__
    result=dict(captured_at=iso(captured),source="Kraken public OHLC native 4h; recent bounded API history",config_hash=digest(config),data=data,errors=errors)
    Path(output).write_text(json.dumps(result,sort_keys=True,allow_nan=False)+"\n")
    if errors:raise ValueError("Incomplete capture; saved failures, no partial-universe evaluation")
    return result


def evaluate(data, cfg, start, end):
    candidates,blocks=precompute(data,cfg)
    result=replay(data,candidates,cfg,start,end)
    result["signal_blockers"]=dict(blocks)
    result["configuration_hash"]=digest(cfg)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",required=True)
    parser.add_argument("--capture",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--fetch",action="store_true")
    args=parser.parse_args()
    cfg=load_config(Path(__file__).with_name("campaign.integrated.json"))
    if args.fetch:capture(cfg,args.capture)
    fresh=json.loads(Path(args.capture).read_text())
    if fresh["errors"] or set(fresh["data"])!=set(cfg["crypto_symbols"]):raise ValueError("Incomplete native capture")
    reused,manifest=load_archive(args.archive,cfg["crypto_symbols"],14400)
    if set(reused)!=set(cfg["crypto_symbols"]):raise ValueError("Archive missing configured symbol")
    for rows in fresh["data"].values():
        if len(rows)<180 or any(b["time"]-a["time"]!=14400 for a,b in zip(rows,rows[1:])):raise ValueError("Insufficient or gapped fresh history")
    # New public capture is retrospective and may overlap earlier research elsewhere.
    # Its provenance is explicit; this script never labels it an untouched holdout.
    start=max(int(rows[120]["time"]) for rows in fresh["data"].values())
    end=min(int(rows[-1]["time"])+14400 for rows in fresh["data"].values())
    old_start=max(int(rows[120]["time"]) for rows in reused.values())
    old_end=min(int(rows[-1]["time"])+14400 for rows in reused.values())
    scenarios={
        "kraken_tier1":dict(crypto_fee_fraction=.008),
        "kraken_adverse_slippage":dict(crypto_fee_fraction=.008,slippage_fraction=.002),
        "hypothetical_alpaca_fee_on_kraken_data":dict(crypto_fee_fraction=.0025),
    }
    result=dict(kind="RETROSPECTIVE RESEARCH; NO EXECUTED TRADES",config=cfg,config_hash=digest(cfg),
        archive_sha256=hashlib.sha256(Path(args.archive).read_bytes()).hexdigest(),
        capture_sha256=hashlib.sha256(Path(args.capture).read_bytes()).hexdigest(),captured_at=fresh["captured_at"],dataset=manifest,
        assumptions=["Three frozen entry families combined in one $500 account per scenario; scenarios are independent, never summed",
          "Next 4h open entries; lagged volume cap; 4h risk checks; adverse stop/target ordering; trailing update takes effect next bar",
          "Kraken tier-1 scenario: 0.8% taker each side, 0.15% half-spread, 0.1% slippage each side; no maker fills or volume discounts assumed",
          "Lower-fee scenario borrows published Alpaca 0.25% taker solely as cost sensitivity on Kraken data; no Alpaca fill, eligibility or spread claimed",
          "Returns include specified trading fees, spread and slippage; hosting, taxes and costs outside these scenarios are excluded",
          "Q1/Q2 archive was previously inspected. Newly fetched history is retrospective and NOT certified untouched; no prospective profitability claim",
          "No parameters selected or changed from results; no automatic promotion; open positions valued after modeled liquidation costs",
          "Book depth, availability, lot rules and actual historical spreads unverified; simulation is assumption-dependent"],scenarios={})
    for name,overrides in scenarios.items():
        scenario=dict(cfg,**overrides)
        result["scenarios"][name]={"reused_archive":evaluate(reused,scenario,old_start,old_end),
                                   "new_public_capture":evaluate(fresh["data"],scenario,start,end)}
        print(json.dumps({name:{period:{key:r[key] for key in ("net_return","closed_trades","maximum_drawdown","profit_factor","final_equity")} for period,r in result["scenarios"][name].items()}}),flush=True)
    result["conclusion"]="No demonstrated prospective edge. These are all predeclared retrospective scenarios; do not deploy based on the best row."
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":main()
