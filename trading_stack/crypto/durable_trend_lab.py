"""Three fixed turnover hypotheses, evaluated on reused development data only."""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
import multi_strategy_lab as m
import regime_swing_lab as r

VERSION = 'DURABLE-TREND-LAB-1'
FAMILIES = ('trend_hold_28d','weekly_leader_28d','channel_28d','blend')
SPEC = dict(decision='Closed UTC daily archive; next observed 15m opening execution',
    daily_input='Aggregate observed Kraken trade-only intervals; do not add execution rows',
    selection='Same January 1–7 formation universe; no subsequent winner selection',
    trend_hold_28d='Original top-two 28d leader entry; retain until EMA21 direction breaks, not rank loss',
    weekly_leader_28d='Original top-two entry/top-four retention on Monday UTC only; risk exits still apply every observed bar',
    channel_28d='Break previous 28 daily highs/lows and EMA21; retain until EMA21 direction breaks',
    stop='Unchanged: three daily ATRs, clipped at 6–20%; trailing starts after one initial stop-distance gain',
    fixed_take_profit=None,maximum_hold_days=56,profit_ceiling=None,
    blend='One shared account, one position per asset, at most 50% per family at entry')


def daily_features(raw, cutoff, strict_intervals=False):
    f=r.daily_features(raw,cutoff,strict_intervals)
    if f.empty:
        return f
    blocks=(f.ts.diff().fillna(m.DAY)!=m.DAY).cumsum()
    f['high28']=f.groupby(blocks).high.transform(lambda v:v.shift().rolling(28).max())
    f['low28']=f.groupby(blocks).low.transform(lambda v:v.shift().rolling(28).min())
    return f


def trend_sides(rows,mode):
    desired={}
    for pair,v in rows.items():
        if v.age<29 or v.volume<=0 or not np.isfinite([v.ema21,v.close]).all():
            continue
        side=1 if v.close>v.ema21 else -1 if v.close<v.ema21 else 0
        if side and (mode!='long_only' or side==1):
            desired[pair]=side
    return desired


def decisions(rows,day,mode):
    leaders,buffer=r.rank_day(rows,'leader_28d',mode)
    trend=trend_sides(rows,mode)
    result={'trend_hold_28d':(leaders,trend,'TREND_EXIT')}
    if pd.Timestamp(day,unit='ms',tz='UTC').weekday()==0:
        result['weekly_leader_28d']=(leaders,buffer,'WEEKLY_RANK_EXIT')
    channel={}
    for pair,side in trend.items():
        v=rows[pair]
        if not np.isfinite([v.high28,v.low28,v.r7,v.volatility]).all():
            continue
        if (side==1 and v.close>v.high28) or (side==-1 and v.close<v.low28):
            channel[pair]=(side,float(abs(v.r7)/v.volatility+1),v)
    result['channel_28d']=(channel,trend,'TREND_EXIT')
    return result


def compile_research(frames,mode,strict_intervals=False):
    cutoff=max(int(raw.ts.iloc[-1])+m.BAR for raw in frames.values())
    by_day={}
    for pair,raw in frames.items():
        for row in daily_features(raw,cutoff,strict_intervals).itertuples(index=False):
            by_day.setdefault(int(row.ts),{})[pair]=row
    signals,exits,receipts={},{},[]
    for day,rows in sorted(by_day.items()):
        entry_ms=day+m.DAY
        signal_ms=entry_ms-m.BAR
        receipt=dict(day_start_ms=day,signal_ms=signal_ms,entry_ms=entry_ms,strategies={})
        for family,(entries,desired,reason) in decisions(rows,day,mode).items():
            receipt['strategies'][family]=dict(entries=[dict(pair=p,side=v[0],score=v[1])
                for p,v in sorted(entries.items())],retained_sides=desired)
            for pair,(side,score,v) in entries.items():
                signals.setdefault((entry_ms,pair),[]).append(m.Signal(family,side,score,
                    float(v.stop),None,56*96,signal_ms,float(v.close),float(v.atr),True,float(v.stop)))
            for pair in frames:
                exits.setdefault(entry_ms,{}).setdefault(pair,{})[family]=(signal_ms,reason,desired.get(pair,0))
        receipts.append(receipt)
    market={}
    for pair,raw in frames.items():
        for v in raw.itertuples(index=False):
            now=int(v.ts)
            market.setdefault(now,{})[pair]=((float(v.open),float(v.high),float(v.low),float(v.close),0.),
                signals.get((now,pair),[]))
    return sorted(market.items()),exits,receipts


def run(frames,receipt,manifest,out,daily_cost=0):
    return r.run(frames,receipt,manifest,out,daily_cost,experiment=dict(families=FAMILIES,
        compiler=compile_research,spec=SPEC,version=VERSION,source=__file__))


def execution_stress(frames,out):
    """Post-selection diagnostics, not validation or a measured operating bill."""
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    market,exits,_=compile_research(frames,'synthetic_long_short')
    market=[row for row in market if row[0]>=r.START]
    rows=[]
    for label,spread,slip,cost in [('original',15,.001,0),
            ('double_execution_cost',30,.002,0),('double_execution_plus_10c_daily',30,.002,.1)]:
        for fee in m.FEE_PROFILES:
            for execution in ('trigger','extrema'):
                cfg=m.Config(family='weekly_leader_28d',risk='aggressive',mode='synthetic_long_short',
                    fee_profile=fee,execution=execution,spread_bps=spread,slippage=slip,daily_operating_cost_usd=cost)
                result=m.simulate(market,cfg,allowed_families=FAMILIES,scheduled_exits=exits)
                by_side={str(side):dict(trades=sum(t['side']==side for t in result['trades']),
                    pnl=sum(t['pnl'] for t in result['trades'] if t['side']==side)) for side in (1,-1)}
                rows.append(dict(case=label,config=m.asdict(cfg),**result['summary'],by_side=by_side))
                m.save_json(out/(label+'-'+fee+'-'+execution+'.json'),result)
                print(f"Stress {label}/{fee}/{execution}: ${result['summary']['ending_equity']:.2f}",flush=True)
    summary=dict(kind='POST_SELECTION_EXECUTION_STRESS_NOT_VALIDATION',reports=rows,
        experiment_version=VERSION,operating_cost_is_sensitivity_estimate=True)
    m.save_json(out/'summary.json',summary)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    inputs=p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--bundle')
    inputs.add_argument('--data-dir')
    p.add_argument('--output-dir',required=True)
    p.add_argument('--daily-operating-cost-usd',type=float,default=0)
    p.add_argument('--stress',action='store_true',help='Also run the fixed post-selection execution/operating-cost sensitivity')
    a=p.parse_args()
    if not math.isfinite(a.daily_operating_cost_usd) or a.daily_operating_cost_usd<0:
        p.error('Operating cost must be finite and nonnegative')
    if a.bundle:
        from export_research_bundle import load_bundle
        frames,receipt,bundle=load_bundle(a.bundle)
        manifest=[dict(pair=c['pair'],bars=c['bars'],sha256=c['source_feather_sha256']) for c in bundle['candles']]
    else:
        frames,receipt,manifest=r.load_universe(a.data_dir)
    run(frames,receipt,manifest,Path(a.output_dir),a.daily_operating_cost_usd)
    if a.stress:
        execution_stress(frames,Path(a.output_dir)/'stress')


if __name__=='__main__':
    main()
