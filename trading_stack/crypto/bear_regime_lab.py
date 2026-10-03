"""Fixed bear-market hypotheses with current pair and financing sensitivities."""
import argparse
import hashlib
import itertools
from pathlib import Path

import numpy as np
import multi_strategy_lab as m
import regime_swing_lab as r
import durable_trend_lab as d
import financing_edge_lab as f

VERSION='BEAR-REGIME-LAB-1'
FAMILIES=('bear_gate_weekly','failed_rebound','bear_channel7')
SPEC=dict(bear_gate_weekly='Original weekly short leaders only while closed BTC is below EMA21 and 28d return <= -3%; exit next observed quote when regime fails',
    failed_rebound='BTC bear gate; asset below EMA21 with 28d return <= -3%; previous two closed days rallied >=3%, then latest day closed lower; top two by negative 28d momentum/volatility',
    bear_channel7='BTC bear gate; asset below EMA21 with 28d return <= -3%; close below previous seven daily lows; top two by negative 28d momentum/volatility',
    exits='New daily families retain below EMA21 while BTC bear gate holds; same 6–20% ATR-derived stop/trailing; 28-day maximum hold',
    allocation='Unchanged aggressive 3% risk budget, full notional reservation, no added leverage',
    eligibility='Only the original formation universe intersected with the current published US pair list',
    financing='Illustrative light and medium opening/four-hour rates; no historical quote claim')


def decisions(rows,day):
    btc=rows.get('BTC/USD')
    gate=bool(btc and btc.age>=29 and np.isfinite([btc.r28,btc.ema21]).all()
        and btc.close<btc.ema21 and btc.r28<=-.03)
    result={}
    if not gate:
        return {name:({}, {}) for name in FAMILIES}
    if d.pd.Timestamp(day,unit='ms',tz='UTC').weekday()==0:
        entries,desired=r.rank_day(rows,'leader_28d','synthetic_long_short')
        result['bear_gate_weekly']=({p:v for p,v in entries.items() if v[0]==-1},
            {p:side for p,side in desired.items() if side==-1})
    desired={p:-1 for p,v in rows.items() if v.age>=29 and v.volume>0 and v.close<v.ema21}
    pools={'failed_rebound':[],'bear_channel7':[]}
    for pair,v in rows.items():
        if v.age<29 or v.volume<=0 or not np.isfinite([v.r28,v.volatility,v.stop,v.prev_close,v.rebound2,v.low7]).all():
            continue
        if v.r28>-.03 or v.close>=v.ema21:
            continue
        score=float(-v.r28/v.volatility)
        if v.rebound2>=.03 and v.close<v.prev_close:
            pools['failed_rebound'].append((score,pair,v))
        if v.close<v.low7:
            pools['bear_channel7'].append((score,pair,v))
    for family,pool in pools.items():
        pool.sort(key=lambda item:(-item[0],item[1]))
        result[family]=({pair:(-1,score,v) for score,pair,v in pool[:2]},desired)
    return result


def compile_research(frames):
    frames={p:raw for p,raw in frames.items() if p in f.CURRENT_US_PAIRS}
    if 'BTC/USD' not in frames:
        raise ValueError('BTC regime candles are required')
    cutoff=max(int(raw.ts.iloc[-1])+m.BAR for raw in frames.values())
    days={}
    for pair,raw in frames.items():
        daily=d.daily_features(raw,cutoff)
        blocks=(daily.ts.diff().fillna(m.DAY)!=m.DAY).cumsum()
        daily['prev_close']=daily.groupby(blocks).close.shift()
        daily['rebound2']=daily.groupby(blocks).close.transform(lambda s:s.shift(1)/s.shift(3)-1)
        for row in daily.itertuples(index=False):
            days.setdefault(int(row.ts),{})[pair]=row
    signals,exits,receipts={},{},[]
    for day,rows in sorted(days.items()):
        now=day+m.DAY;signal_ms=now-m.BAR
        receipt=dict(signal_ms=signal_ms,entry_ms=now,strategies={})
        for family,(entries,desired) in decisions(rows,day).items():
            receipt['strategies'][family]=dict(entries=sorted(entries),retained_sides=desired)
            for pair,(side,score,v) in entries.items():
                signals.setdefault((now,pair),[]).append(m.Signal(family,side,score,float(v.stop),None,
                    28*96,signal_ms,float(v.close),float(v.atr),True,float(v.stop)))
            for pair in frames:
                exits.setdefault(now,{}).setdefault(pair,{})[family]=(signal_ms,'BEAR_REGIME_OR_TREND_EXIT',desired.get(pair,0))
        receipts.append(receipt)
    market={}
    for pair,raw in frames.items():
        for v in raw.itertuples(index=False):
            now=int(v.ts)
            market.setdefault(now,{})[pair]=((float(v.open),float(v.high),float(v.low),float(v.close),0.),signals.get((now,pair),[]))
    return sorted(market.items()),exits,receipts,sorted(frames)


def run(frames,receipt,manifest,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    market,exits,receipts,pairs=compile_research(frames)
    market=[row for row in market if row[0]>=r.START]
    windows=m.month_windows(market)
    reports=[]
    m.save_json(out/'bear-rankings.json',dict(receipts=receipts,pairs=pairs,spec=SPEC))
    for family,profile,execution,cost in itertools.product(FAMILIES,
            ('illustrative_light','illustrative_medium'),('trigger','extrema'),(0.,.1)):
        opening,rollover=f.PROFILES[profile]
        cfg=m.Config(family=family,risk='aggressive',mode='synthetic_long_short',spread_bps=15,
            execution=execution,slippage=.001,short_carry_per_day=0,short_opening_fee=opening,
            short_rollover_per_4h=rollover,daily_operating_cost_usd=cost)
        result=m.simulate(market,cfg,allowed_families=FAMILIES,scheduled_exits=exits)
        months=[]
        for month,lo,hi,partial in windows:
            part=m.simulate(market,cfg,lo,hi,allowed_families=FAMILIES,scheduled_exits=exits)
            months.append(dict(month=month,partial=partial,**part['summary']))
        full=[v for v in months if not v['partial']]
        name=f'{family}-{profile}-{execution}-cost{cost:g}'
        row=dict(name=name,config=m.asdict(cfg),financing_profile=profile,**result['summary'],
            positive_months=sum(v['return_pct']>0 for v in full),complete_months=len(full),
            median_month_return_pct=float(np.median([v['return_pct'] for v in full])) if full else None,
            activation_eligible=False)
        result.update(version=VERSION,spec=SPEC,monthly_independent_100=months,input_manifest=manifest,
            formation_universe=receipt,limitations=f.LIMITATIONS)
        m.save_json(out/(name+'.json'),result)
        reports.append(row)
        print(f"[{len(reports)}/24] {name}: ${row['ending_equity']:.2f}; {row['trades']} trades",flush=True)
    summary=dict(version=VERSION,status='RESEARCH_ONLY_NO_ACTIVATION',reports=reports,spec=SPEC,
        included_pairs=pairs,input_manifest=manifest,formation_universe=receipt,limitations=f.LIMITATIONS,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        accounting_sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest())
    m.save_json(out/'bear-summary.json',summary)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    inputs=p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--bundle');inputs.add_argument('--data-dir')
    p.add_argument('--output-dir',required=True)
    a=p.parse_args()
    if a.bundle:
        from export_research_bundle import load_bundle
        frames,receipt,bundle=load_bundle(a.bundle)
        manifest=[dict(pair=v['pair'],bars=v['bars'],sha256=v['source_feather_sha256']) for v in bundle['candles']]
    else:
        frames,receipt,manifest=r.load_universe(a.data_dir)
    run(frames,receipt,manifest,a.output_dir)


if __name__=='__main__':
    main()
