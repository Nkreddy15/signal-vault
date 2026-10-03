"""Daily relative-strength and channel hypotheses on the frozen 24-asset universe.

Decisions use complete UTC days only; fills use the following 15m opening bar.
Research only. This module never imports a venue client or touches paper state.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import multi_strategy_lab as m

VERSION = 'REGIME-SWING-LAB-1'
FAMILIES = ('leader_7d', 'leader_28d', 'channel_7d', 'blend')
START = int(pd.Timestamp('2026-03-01', tz='UTC').value//1_000_000)
SPEC = dict(decision='Complete UTC daily candle; next 15m opening fill',
    selection='Same January 1–7 formation universe; no later winner selection',
    leader_7d='Top two long / bottom two synthetic short, 7d momentum divided by 14d daily volatility',
    leader_28d='Top two / bottom two, equally weighted 7d and 28d risk-adjusted momentum',
    minimum_absolute_momentum=.03, rank_retention_buffer=4,
    channel_7d='Break past previous seven daily highs/lows; retain while above/below daily EMA21',
    stop='Three daily ATRs, clipped at 6–20%; fixed-distance trailing begins after one initial stop-distance gain',
    fixed_take_profit=None, maximum_hold_days=28, profit_ceiling=None,
    blend='Shared capital, one position per asset, at most 50% of account per strategy family at entry')
LIMITATIONS = [
    'Unvalidated research. Q1/Q2 have already influenced development; this is not untouched validation.',
    'No forecast calibration gate is reused. New fixed entry/exit hypotheses are explicitly different strategies.',
    'Long-only results are cash-funded spot approximations. Synthetic shorts are separate experiments, not executable spot shorts.',
    'Synthetic short carry is a 0.03%/day assumption; actual borrow, margin availability, funding and liquidation are not modeled.',
    'Alpaca rate sensitivity uses Kraken data and simplified cash-fee accounting, not Alpaca venue or asset eligibility evidence.',
    'Days with missing 15m bars are excluded. Daily indicators restart after gaps. Pending exits wait for an observed asset quote.',
    'Daily rankings use only previously closed data; hold-rank buffers reduce forced turnover, but stops and exits still incur costs.',
    'No account or per-trade profit target. Stops, trend exits, 28-day time exits and drawdown triggers can still realize losses.',
    'Higher equity increases stake and capacity through the shared engine; it does not manufacture additional signals.',
    'Trigger/extrema fills remain intrabar approximations, with gap and missing-data risks. No broker orders or activation.',
]


def daily_features(raw):
    raw = m.normalized(raw)
    day = raw.ts//m.DAY*m.DAY
    grouped = raw.groupby(day, sort=True)
    f = grouped.agg(open=('open','first'), high=('high','max'), low=('low','min'),
        close=('close','last'), volume=('volume','sum'), count=('ts','size'),
        first_ms=('ts','min'), last_ms=('ts','max')).reset_index(names='ts')
    f = f[(f['count']==96) & (f.first_ms==f.ts) & (f.last_ms==f.ts+m.DAY-m.BAR)].copy()
    if f.empty:
        return f.reset_index(drop=True)
    block = (f.ts.diff().fillna(m.DAY)!=m.DAY).cumsum()
    parts = []
    for _, p in f.groupby(block):
        p=p.copy()
        p['ema7']=p.close.ewm(span=7,adjust=False).mean()
        p['ema21']=p.close.ewm(span=21,adjust=False).mean()
        p['r7']=p.close.pct_change(7,fill_method=None)
        p['r28']=p.close.pct_change(28,fill_method=None)
        tr=pd.concat([p.high-p.low,(p.high-p.close.shift()).abs(),(p.low-p.close.shift()).abs()],axis=1).max(axis=1)
        p['atr']=tr.ewm(alpha=1/14,adjust=False).mean()/p.close
        p['volatility']=np.log(p.close).diff().rolling(14).std(ddof=0).clip(lower=.005)
        p['high7']=p.high.shift().rolling(7).max()
        p['low7']=p.low.shift().rolling(7).min()
        p['stop']=(3*p.atr).clip(lower=.06,upper=.20)
        p['age']=range(1,len(p)+1)
        parts.append(p)
    return pd.concat(parts,ignore_index=True)


def rank_day(rows, family, mode):
    """Entry top-two, retention top-four; never rank an asset with stale data."""
    ranked={1:[], -1:[]}
    for pair, r in rows.items():
        if r.age < 29 or r.volume <= 0 or not np.isfinite([r.r7,r.r28,r.atr,r.volatility]).all():
            continue
        if family=='channel_7d':
            continue
        score=r.r7/r.volatility if family=='leader_7d' else (.5*r.r7+.5*r.r28)/r.volatility
        for side in (1,-1):
            if mode=='long_only' and side==-1:
                continue
            momentum=r.r7 if family=='leader_7d' else r.r28
            if side*momentum >= .03 and side*r.r7 > 0 and side*(r.close/r.ema21-1) > 0:
                ranked[side].append((float(side*score),pair,r))
    entries, desired = {}, {}
    for side, candidates in ranked.items():
        candidates.sort(key=lambda item:(-item[0],item[1]))
        for index,(score,pair,r) in enumerate(candidates[:4]):
            desired[pair]=side
            if index<2:
                entries[pair]=(side,score,r)
    if family=='channel_7d':
        for pair,r in rows.items():
            if r.age<29 or r.volume<=0 or not np.isfinite([r.atr,r.high7,r.low7,r.volatility]).all():
                continue
            side=1 if r.close>r.ema21 else -1 if r.close<r.ema21 else 0
            if not side or (side==-1 and mode=='long_only'):
                continue
            desired[pair]=side
            if (side==1 and r.close>r.high7) or (side==-1 and r.close<r.low7):
                score=abs(r.r7)/r.volatility+1
                entries[pair]=(side,float(score),r)
    return entries, desired


def compile_research(frames, mode):
    daily, by_day = {}, {}
    for pair,raw in frames.items():
        daily[pair]=daily_features(raw)
        for row in daily[pair].itertuples(index=False):
            by_day.setdefault(int(row.ts),{})[pair]=row
    signals, exits, rankings = {}, {}, []
    for day, rows in sorted(by_day.items()):
        now=day+m.DAY
        signal_ms=now-m.BAR
        ranking=dict(day_start_ms=day,signal_ms=signal_ms,entry_ms=now,strategies={})
        for family in FAMILIES[:-1]:
            entries,desired=rank_day(rows,family,mode)
            ranking['strategies'][family]=dict(entries=[dict(pair=p,side=v[0],score=v[1])
                for p,v in sorted(entries.items())],retained_sides=desired)
            for pair,(side,score,r) in entries.items():
                sig=m.Signal(family,side,score,float(r.stop),None,28*96,signal_ms,
                    float(r.close),float(r.atr),True,float(r.stop))
                signals.setdefault((now,pair),[]).append(sig)
            for pair in frames:
                exits.setdefault(now,{}).setdefault(pair,{})[family]=(signal_ms,
                    'CHANNEL_EXIT' if family=='channel_7d' else 'RANK_EXIT',desired.get(pair,0))
        rankings.append(ranking)
    market={}
    # Stop levels use the signal's daily ATR distance; 15m bars only determine
    # executions and gap quotes, never shorten that distance with 15m volatility.
    for pair,raw in frames.items():
        for r in raw.itertuples(index=False):
            now=int(r.ts)
            market.setdefault(now,{})[pair]=((float(r.open),float(r.high),float(r.low),float(r.close),0.),
                signals.get((now,pair),[]))
    return sorted(market.items()),exits,rankings


def load_universe(root):
    root=Path(root)
    receipt=json.loads((root/'universe.json').read_text())
    frames,manifest={},[]
    for asset in receipt['selected']:
        pair=asset['pair']
        path=root/(pair.replace('/','_')+'-15m.feather')
        f=m.normalized(pd.read_feather(path))
        frames[pair]=f
        manifest.append(dict(pair=pair,bars=len(f),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return frames,receipt,manifest


def run(frames, receipt, manifest, out, daily_cost=0):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    reports, baselines = [], {}
    for mode in ('long_only','synthetic_long_short'):
        print('Compiling daily decisions: '+mode,flush=True)
        market,exits,rankings=compile_research(frames,mode)
        market=[row for row in market if row[0]>=START]
        if len(market)<96:
            raise ValueError('Insufficient March–June research candles')
        m.save_json(out/(mode+'-rankings.json'),dict(spec=SPEC,rankings=rankings))
        windows=m.month_windows(market)
        for family in FAMILIES:
            for risk in ('balanced','aggressive'):
                for fee in m.FEE_PROFILES:
                    for execution in ('trigger','extrema'):
                        cfg=m.Config(family=family,risk=risk,mode=mode,spread_bps=15,
                            execution=execution,fee_profile=fee,daily_operating_cost_usd=daily_cost)
                        name=f'{family}-{risk}-{mode}-{fee}-15bps-{execution}'
                        result=m.simulate(market,cfg,allowed_families=FAMILIES,scheduled_exits=exits)
                        months=[]
                        for month,lo,hi,partial in windows:
                            r=m.simulate(market,cfg,lo,hi,allowed_families=FAMILIES,scheduled_exits=exits)
                            months.append(dict(month=month,partial=partial,**r['summary']))
                        full=[r for r in months if not r['partial']]
                        row=dict(name=name,config=m.asdict(cfg),**result['summary'],
                            complete_months=len(full),positive_months=sum(r['return_pct']>0 for r in full),
                            median_month_return_pct=float(np.median([r['return_pct'] for r in full])) if full else None,
                            milestone_month_counts={str(goal):sum(r['ending_equity']>=goal for r in full)
                                for goal in (250,500,1000,2500,5000,10000)})
                        row['development_screen_pass']=bool(mode=='long_only' and len(full)>=3 and
                            row['trades']>=20 and row['return_pct']>0 and row['median_month_return_pct']>0 and
                            row['positive_months']>=math.ceil(.6*len(full)) and
                            row['profit_factor'] is not None and row['profit_factor']>=1.1 and
                            row['max_drawdown_pct']<=100*cfg.drawdown_limit and not row['pending_positions'])
                        result.update(monthly_independent_100=months,version=VERSION,spec=SPEC,
                            input_manifest=manifest,universe=receipt,limitations=LIMITATIONS)
                        m.save_json(out/(name+'.json'),result)
                        if result['trades']:
                            pd.DataFrame(result['trades']).to_csv(out/(name+'-trades.csv'),index=False)
                        reports.append(row)
                        print(f"[{len(reports)}/64] {name}: end ${row['ending_equity']:.2f}; trades {row['trades']}; DD {row['max_drawdown_pct']:.2f}%",flush=True)
                        m.save_json(out/'regime-progress.json',dict(version=VERSION,completed=len(reports),expected=64,reports=reports))
                        key=fee+'-15bps'
                        if key not in baselines:
                            baselines[key]=m.buy_and_hold(market,cfg)
    robust=[]
    for family in FAMILIES:
        for risk in ('balanced','aggressive'):
            group=[r for r in reports if r['config']['family']==family and r['config']['risk']==risk and
                r['config']['mode']=='long_only' and r['config']['fee_profile']=='kraken_spot']
            if len(group)==2 and all(r['development_screen_pass'] for r in group):
                robust.append(f'{family}-{risk}-kraken-15bps')
    coverage={}
    for pair,raw in frames.items():
        daily=daily_features(raw)
        coverage[pair]=dict(complete_days=len(daily),
            complete_days_after_warmup=int((daily.get('age',pd.Series(dtype=int))>=29).sum()))
    summary=dict(version=VERSION,status='DEVELOPMENT_ONLY_NO_ACTIVATION',profit_ceiling=None,
        reports=reports,robust_kraken_long_only_candidates=robust,
        fee_rate_sensitivity_only=[r['name'] for r in reports if r['config']['fee_profile']!='kraken_spot'
            and r['development_screen_pass']],spec=SPEC,input_manifest=manifest,universe=receipt,
        buy_and_hold_baselines=baselines,limitations=LIMITATIONS,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        shared_engine_sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
        runtime_versions=dict(pandas=pd.__version__,numpy=np.__version__),sources=m.SOURCES,
        daily_coverage=coverage)
    m.save_json(out/'regime-summary.json',summary)
    lines=['# Daily regime swing research','', 'No activation. Reused data. Synthetic shorts are separate sensitivity experiments.','',
        '| Configuration | End equity | Peak | Trades | Gross | Fees | Carry | Max DD | Median month |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in reports:
        median='n/a' if r['median_month_return_pct'] is None else f"{r['median_month_return_pct']:.2f}%"
        lines.append(f"| {r['name']} | ${r['ending_equity']:.2f} | ${r['peak_equity']:.2f} | {r['trades']} | ${r['recorded_fill_gross_pnl']:.2f} | ${r['fees']:.2f} | ${r['short_carry']:.2f} | {r['max_drawdown_pct']:.2f}% | {median} |")
    lines.extend(['','Robust Kraken long-only development candidates: '+(', '.join(robust) if robust else 'NONE'),'',*LIMITATIONS])
    (out/'regime-results.md').write_text('\n'.join(lines)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',required=True)
    p.add_argument('--output-dir',required=True)
    p.add_argument('--daily-operating-cost-usd',type=float,default=0)
    a=p.parse_args()
    if not math.isfinite(a.daily_operating_cost_usd) or a.daily_operating_cost_usd<0:
        raise ValueError('Operating cost must be finite and nonnegative')
    frames,receipt,manifest=load_universe(a.data_dir)
    run(frames,receipt,manifest,a.output_dir,a.daily_operating_cost_usd)
    print('Saved regime-summary.json and regime-results.md. Paper entries remain paused.',flush=True)


if __name__=='__main__':
    main()
