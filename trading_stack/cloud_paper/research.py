"""Reproducible historical screening, isolated from every execution ledger.

Previously inspected data is explicitly reused, never an untouched holdout.
Uses next-hour opens, adverse same-bar ordering and lagged liquidity screens.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import random
import statistics
import zipfile
from collections import Counter
from pathlib import Path
from .engine import load_config
from .providers import iso
from .store import digest
from .strategies import signals


def load_archive(path,symbols):
    data={};manifest={}
    with zipfile.ZipFile(path) as archive:
        for symbol in symbols:
            name="candles/"+symbol.replace("/","_")+"-15m.csv"
            if name not in archive.namelist(): continue
            raw=archive.read(name);groups={};count=0
            for row in csv.DictReader(io.StringIO(raw.decode())):
                t=int(row["ts"])//1000;count+=1
                r={k:float(row[k]) for k in ("open","high","low","close","volume")};r["time"]=t
                if not all(math.isfinite(r[k]) and r[k]>0 for k in ("open","high","low","close")): continue
                groups.setdefault(t//3600*3600,[]).append(r)
            hours=[]
            for t,rs in sorted(groups.items()):
                rs.sort(key=lambda r:r["time"])
                if [r["time"] for r in rs]!=[t+i*900 for i in range(4)]:continue
                hours.append(dict(time=t,open=rs[0]["open"],high=max(r["high"] for r in rs),low=min(r["low"] for r in rs),
                                  close=rs[-1]["close"],volume=sum(r["volume"] for r in rs)))
            data[symbol]=hours
            manifest[symbol]=dict(sha256=hashlib.sha256(raw).hexdigest(),quarter_hours=count,complete_hours=len(hours),
                                 incomplete_hours_discarded=len(groups)-len(hours),start=iso(hours[0]["time"]),end=iso(hours[-1]["time"]+3600))
    return data,manifest


def precompute(data,cfg):
    candidates={};blocks=Counter()
    for symbol,rows in data.items():
        for i,r in enumerate(rows):
            if i<60:continue
            history=rows[max(0,i-720):i]
            found,reason=signals(history,"crypto",symbol,r["time"],cfg)
            if not found:blocks[reason]+=1;continue
            lagged=history[-24:]
            if len(lagged)<24 or lagged[-1]["time"]-lagged[0]["time"]!=23*3600:
                blocks["Incomplete lagged daily liquidity"]+=1;continue
            if sum(b["close"]*b["volume"] for b in lagged)<cfg["minimum_daily_volume_usd"]:
                blocks["Below lagged daily volume"]+=1;continue
            c=found[0];c["lagged_volume_cap"]=.01*history[-1]["volume"]
            candidates.setdefault(r["time"],[]).append(c)
    return candidates,blocks


def bootstrap_means(values):
    if len(values)<5:return None
    rng=random.Random(20261004);n=len(values)
    means=sorted(statistics.mean(rng.choices(values,k=n)) for _ in range(1000))
    return [means[25],means[974]]


def replay(data,candidates,cfg,start,end):
    fee=cfg["crypto_fee_fraction"];friction=cfg["slippage_fraction"]+cfg["max_spread_fraction"]/2
    indexed={sym:{r["time"]:r for r in rows} for sym,rows in data.items()}
    cash=cfg["capital"];peak=cash;day_equity=cash;daily_halt=False;halt=False
    positions={};marks={};trades=[];curve=[];seen=set();turnover=0;fees=0;blocks=Counter()
    def equity():return cash+sum(p["qty"]*marks.get(sym,p["entry"])*(1-friction)*(1-fee) for sym,p in positions.items())
    def sell(sym,reference,t,reason):
        nonlocal cash,turnover,fees
        p=positions.pop(sym);price=reference*(1-friction);gross=p["qty"]*price;cost=gross*fee
        cash+=gross-cost;turnover+=gross;fees+=cost
        trades.append(dict(symbol=sym,strategy=p["strategy"],entry_at=iso(p["at"]),exit_at=iso(t),
                           net_pnl=gross-cost-p["cost"],reason=reason))
    for t in range(start,end,3600):
        current={sym:rows[t] for sym,rows in indexed.items() if t in rows}
        # Opening-price marks precede decisions; a missing bar blocks new risk.
        for sym,r in current.items():marks[sym]=r["open"]
        if t==start or t//86400!=(t-3600)//86400:day_equity=equity();daily_halt=False
        for sym,p in list(positions.items()):
            if sym in current and (halt or daily_halt or t-p["at"]>=cfg["max_hold_hours"]*3600):
                sell(sym,current[sym]["open"],t,"RISK_OR_TIME_EXIT")
        for c in sorted(candidates.get(t,[]),key=lambda c:(-c["score"],c["symbol"])):
            sym=c["symbol"]
            if halt or daily_halt:blocks["Risk halt"]+=1;continue
            if any(sym not in current for sym in positions):blocks["Missing held-asset bar"]+=1;continue
            if sym in positions or c["signal"] in seen or len(positions)>=cfg["max_positions"]:continue
            r=current[sym];reference=r["open"]
            if abs(reference/c["reference"]-1)>.03:blocks["Next open moved over 3%"]+=1;continue
            entry=reference*(1+friction);eq=equity()
            target=c["target"] if c.get("target_anchored") else entry+c["target"]-c["reference"]
            if cfg.get("strategy_pack")=="regime-v2" and target/entry-1<c["cost_break_even_fraction"]+.01:
                blocks["Fresh entry price leaves insufficient target room after costs"]+=1;continue
            exposure=sum(p["qty"]*marks.get(s,p["entry"]) for s,p in positions.items())
            budget=min(cash,eq*cfg["max_position_fraction"],eq*cfg["max_exposure_fraction"]-exposure)
            spread_reserve=cfg["max_spread_fraction"] if cfg.get("strategy_pack")=="regime-v2" else 0
            quantity=min(budget/(entry*(1+fee)),eq*cfg["risk_per_trade"]/(c["stop_distance"]+entry*(2*fee+2*cfg["slippage_fraction"]+spread_reserve)),c["lagged_volume_cap"])
            quantity=math.floor(max(0,quantity)*1e8)/1e8
            if quantity*entry<cfg["minimum_order_usd"]:blocks["Minimum size or lagged liquidity cap"]+=1;continue
            cost=quantity*entry*(1+fee);cash-=cost;fees+=quantity*entry*fee;turnover+=quantity*entry
            positions[sym]=dict(qty=quantity,entry=entry,cost=cost,at=t,strategy=c["strategy"],stop=entry-c["stop_distance"],
                                target=target,distance=c["stop_distance"],peak=entry)
            seen.add(c["signal"])
        for sym,p in list(positions.items()):
            if sym not in current:continue
            r=current[sym]
            # Stop first if both levels occur; no favorable intrabar path invented.
            if r["low"]<=p["stop"]:sell(sym,min(r["open"],p["stop"]),t+3599,"STOP")
            elif r["high"]>=p["target"]:sell(sym,p["target"],t+3599,"TARGET")
            else:
                p["peak"]=max(p["peak"],r["high"])
                if p["peak"]>=p["entry"]+p["distance"]:p["stop"]=max(p["stop"],p["peak"]-p["distance"])
            marks[sym]=r["close"]
        eq=equity();peak=max(peak,eq);dd=1-eq/peak
        if eq<=day_equity*(1-cfg["daily_loss_fraction"]):daily_halt=True
        if dd>=cfg["drawdown_fraction"]:halt=True
        exposure=sum(p["qty"]*marks.get(s,p["entry"]) for s,p in positions.items())
        curve.append(dict(at=t+3600,equity=eq,drawdown=dd,exposure_fraction=exposure/eq))
    # End marks include modeled liquidation cost; no invented terminal fills.
    wins=sum(max(0,t["net_pnl"]) for t in trades);losses=-sum(min(0,t["net_pnl"]) for t in trades)
    pnl=[t["net_pnl"] for t in trades]
    btc=[r for r in data.get("BTC/USD",[]) if start<=r["time"]<end]
    baseline_return=(btc[-1]["close"]*(1-friction)*(1-fee)/(btc[0]["open"]*(1+friction)*(1+fee))-1) if btc else None
    bp=cfg["capital"];bdd=0
    if btc:
        for r in btc:
            value=cfg["capital"]*r["close"]*(1-friction)*(1-fee)/(btc[0]["open"]*(1+friction)*(1+fee));bp=max(bp,value);bdd=max(bdd,1-value/bp)
    by_strategy={family:dict(closed_trades=sum(t["strategy"]==family for t in trades),net_realized=sum(t["net_pnl"] for t in trades if t["strategy"]==family)) for family in cfg["strategies"] if family in ("trend","breakout","pullback","range_reversion")}
    return dict(start=iso(start),end=iso(end),final_equity=equity(),net_return=equity()/cfg["capital"]-1,
                maximum_drawdown=max(r["drawdown"] for r in curve),closed_trades=len(trades),open_positions=len(positions),
                mean_exposure_fraction=statistics.mean(r["exposure_fraction"] for r in curve),turnover_usd=turnover,
                turnover_multiple=turnover/cfg["capital"],fees_usd=fees,profit_factor=wins/losses if losses else None,
                mean_trade_pnl=statistics.mean(pnl) if pnl else None,descriptive_iid_bootstrap_mean_trade_pnl_95=bootstrap_means(pnl),
                drawdown_halted=halt,strategies=by_strategy,blockers=dict(blocks),
                baselines=dict(cash_return=0,btc_buy_hold_after_cost_return=baseline_return,btc_buy_hold_max_drawdown=bdd),
                curve_daily=[r for r in curve if r["at"]%86400==0],trades=trades)


def main():
    p=argparse.ArgumentParser();p.add_argument("--archive",required=True);p.add_argument("--output",required=True);args=p.parse_args()
    cfg=load_config();data,manifest=load_archive(args.archive,cfg["crypto_symbols"])
    candidates,blocks=precompute(data,cfg)
    first=max(rows[0]["time"] for rows in data.values());last=min(rows[-1]["time"]+3600 for rows in data.values())
    hours=(last-first)//3600;cuts=[first,first+int(hours*.6)*3600,first+int(hours*.8)*3600,last]
    periods={name:replay(data,candidates,cfg,cuts[i],cuts[i+1]) for i,name in enumerate(("reused_development","reused_validation","reused_test_not_holdout"))}
    result=dict(kind="HISTORICAL SCREENING ONLY",config=cfg,config_hash=digest(cfg),archive_sha256=hashlib.sha256(Path(args.archive).read_bytes()).hexdigest(),
        provenance="All Q1/Q2 data was inspected in earlier Signal Vault research. Chronological partitions are reused; there is no untouched holdout. No parameters were selected from this run.",
        assumptions=["15-asset spot long-only portfolio; no leverage, borrow, funding or financing cost",
          "Same frozen signal function; last 720 closed hourly bars; strict complete 15-minute-to-hour aggregation",
          "Each chronological partition starts with $500; duration extended to partition length for screening; drawdown halts persist within partition",
          "Next-hour open entry; 0.4% fee each side, 0.15% half-spread each side, 0.1% slippage each side",
          "Entry quantity at most 1% of prior hour's volume; prior closed 24-hour notional at least $500,000",
          "Historical venue eligibility, lot rules, order-book depth and executable spreads unavailable; assumed $5 minimum and eight quantity decimals",
          "Adverse stop before target if both touched; stop gaps use worse opening price; trailing levels update for next bar",
          "Loss controls and time exits evaluated hourly, unlike the prospective 30-second worker; historical fills are modeled, not executions",
          "Residual positions marked after modeled exit costs; no terminal fills invented",
          "Bootstrap trade-mean interval is descriptive IID only; serial/cross-asset dependence and reused data invalidate formal edge claims",
          "No stock or prediction-market performance is inferred from crypto data; no calibrated Kalshi edge available"],
        dataset=manifest,signal_blockers=dict(blocks),periods=periods,conclusion="Experimental only. Reused, assumption-dependent screening cannot establish out-of-sample profitability.")
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:{m:v[m] for m in ("net_return","maximum_drawdown","closed_trades","profit_factor","final_equity")} for k,v in periods.items()},indent=2))


if __name__=="__main__":main()
