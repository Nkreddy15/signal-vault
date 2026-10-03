"""Observed 15m short-hold research; no broker requests or paper activation."""
import argparse
import hashlib
import itertools
from collections import Counter
from pathlib import Path

import numpy as np
import multi_strategy_lab as m
import regime_swing_lab as r

VERSION='SCALPING-EDGE-LAB-1'
FAMILIES=('scalp_breakout','scalp_reversion','scalp_pullback','blend','turnover_control')
PROFILES=('kraken_spot','hypothetical_10bp','zero_cost_control')
SPEC=dict(
    timeframe='Observed 15m candles only; no inferred one-minute bars or maker fills',
    scalp_breakout='Close above prior four-bar high, EMA20 above EMA60, volume ratio >=1',
    scalp_reversion='20-bar z-score <=-1.5, RSI14 <=40, close above previous close',
    scalp_pullback='EMA20 above EMA60, previous close at/below previous EMA20, current close above EMA20',
    blend='All three signal families share one account; one position per pair',
    turnover_control='Enter each consecutive eligible closed bar; diagnostic churn, not a proposed strategy',
    target='0.50% target; 0.50% stop; four-bar maximum hold, control one bar; no trailing',
    allocation='Long only, full cash notional reservation, 1% risk, existing shared-account limits',
    timing='64 consecutive observed bars warm-up; signal fills only on next observed adjacent bar',
    costs='Current Kraken taker tiers vs hypothetical 0.10% per side vs zero-cost control; no maker-fee claim',
    running_cost='Independent $0/day and illustrative $0.10/day replays',
    cost_guard='Sub-cost targets explicitly permitted only in research to measure their loss; defaults elsewhere retained')
LIMITATIONS=[
    'Reused January–June development data; March–June account window, not untouched validation.',
    '15m candles cannot establish one-minute scalping, quote depth, queue priority, latency or hundreds of realizable fills.',
    'Current fee schedules are applied as present-cost sensitivities, not reconstructed historical fee schedules.',
    'Hypothetical lower/zero costs are diagnostics on Kraken prices, not executable venue results.',
    'Market-trigger fills only; intrabar order is unknown, simultaneous stop/target uses stop first.',
    'Existing drawdown and daily-loss halts remain; no leverage, broker orders or paper-entry resumes.',
    'Original 24 formation-selected assets retained; historical venue minimum quantities and execution depth not reconstructed.',
]


def candidates(raw):
    f=m.features(raw)
    # Rolling calculations stay within contiguous observed blocks. An omitted
    # no-trade candle is still not an executable quote for this short-hold test.
    blocks=(f.ts.diff().fillna(m.BAR)!=m.BAR).cumsum()
    groups=f.groupby(blocks)
    f['hi4']=groups.high.transform(lambda x:x.shift().rolling(4).max())
    mean=groups.close.transform(lambda x:x.rolling(20).mean())
    std=groups.close.transform(lambda x:x.rolling(20).std(ddof=0))
    f['z20']=(f.close-mean)/std.replace(0,np.nan)
    valid=(f.age>=64)&(f.volume>0)&f.atr.between(.0001,.03)
    masks={
        'scalp_breakout':valid&(f.close>f.hi4)&(f.ema20>f.ema60)&(f.vol_ratio>=1),
        'scalp_reversion':valid&(f.z20<=-1.5)&(f.rsi<=40)&(f.close>f.prev_close),
        'scalp_pullback':valid&(f.ema20>f.ema60)&(f.prev_close<=f.prev_fast)&(f.close>f.ema20),
        'turnover_control':valid,
    }
    out={}
    for family,mask in masks.items():
        for v in f.loc[mask].itertuples(index=False):
            score=float(abs(v.z20)) if family=='scalp_reversion' else float(v.vol_ratio) if family=='scalp_breakout' else 1.
            out.setdefault(int(v.ts),[]).append(m.Signal(family,1,score,.005,
                None if family=='turnover_control' else .005,1 if family=='turnover_control' else 4,
                int(v.ts),float(v.close),float(v.atr),False))
    return f,out


def compile_research(frames):
    market={};counts=Counter()
    for pair,raw in frames.items():
        f,signals=candidates(raw)
        for v in f[['ts','open','high','low','close','atr']].itertuples(index=False,name=None):
            now=int(v[0]);ss=signals.get(now-m.BAR,[])
            counts.update(s.family for s in ss)
            market.setdefault(now,{})[pair]=(tuple(float(x) for x in v[1:]),ss)
    return sorted(market.items()),dict(counts)


def frequency(result):
    byday=Counter(t['entry_ms']//m.DAY for t in result['trades'])
    s=result['summary'];days=(s['end_ms']-s['start_ms'])/m.DAY
    return dict(max_entries_in_utc_day=max(byday.values(),default=0),days_with_100_entries=sum(n>=100 for n in byday.values()),
        active_entry_days=len(byday),mean_entries_per_active_day=float(np.mean(list(byday.values()))) if byday else 0,
        mean_entries_per_calendar_day=len(result['trades'])/days if days else 0,
        calendar_days=days,entry_notional_usd=sum(t['stake'] for t in result['trades']),
        median_hold_minutes=float(np.median([(t['exit_ms']-t['entry_ms'])/60000 for t in result['trades']])) if result['trades'] else None)


def run(frames,receipt,manifest,out,starting_balance=100):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    market,counts=compile_research(frames);market=[v for v in market if v[0]>=r.START]
    if len(market)<96: raise ValueError('Insufficient observed research data')
    windows=m.month_windows(market);reports=[]
    # Profiles are registered only for this read-only research process.
    m.FEE_PROFILES['hypothetical_10bp']=((0,.001),)
    m.FEE_PROFILES['zero_cost_control']=((0,0.),)
    for family,profile,execution,cost in itertools.product(FAMILIES,PROFILES,('trigger','extrema'),(0.,.1)):
        cfg=m.Config(family=family,risk='balanced',mode='long_only',fee_profile=profile,
            starting_balance=starting_balance,
            spread_bps=0 if profile=='zero_cost_control' else 15,
            slippage=0 if profile=='zero_cost_control' else .001,
            execution=execution,daily_operating_cost_usd=cost,allow_subcost_targets=True)
        # A blend must not include the deliberately indiscriminate control.
        rows=market if family!='blend' else [(ts,{p:(bar,[s for s in ss if s.family!='turnover_control']) for p,(bar,ss) in pairs.items()}) for ts,pairs in market]
        result=m.simulate(rows,cfg,allowed_families=FAMILIES)
        months=[]
        for month,lo,hi,partial in windows:
            part=m.simulate(rows,cfg,lo,hi,allowed_families=FAMILIES)
            months.append(dict(month=month,partial=partial,**part['summary'],frequency=frequency(part)))
        full=[v for v in months if not v['partial']]
        name=f'{family}-{profile}-{execution}-cost{cost:g}'
        row=dict(name=name,config=m.asdict(cfg),**result['summary'],frequency=frequency(result),
            positive_months=sum(v['return_pct']>0 for v in full),complete_months=len(full),
            median_month_return_pct=float(np.median([v['return_pct'] for v in full])) if full else None,
            activation_eligible=False)
        result.update(version=VERSION,spec=SPEC,frequency=row['frequency'],monthly_independent_accounts=months,
            input_manifest=manifest,formation_universe=receipt,limitations=LIMITATIONS)
        m.save_json(out/(name+'.json'),result);reports.append(row)
        print(f"[{len(reports)}/60] {name}: ${row['ending_equity']:.2f}; {row['trades']} entries; max/day {row['frequency']['max_entries_in_utc_day']}",flush=True)
        m.save_json(out/'scalping-progress.json',dict(version=VERSION,reports=reports))
    summary=dict(version=VERSION,status='RESEARCH_ONLY_NO_ACTIVATION',reports=reports,spec=SPEC,
        starting_balance=starting_balance,
        candidate_signal_counts=counts,input_manifest=manifest,formation_universe=receipt,limitations=LIMITATIONS,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        accounting_sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest())
    m.save_json(out/'scalping-summary.json',summary)
    for module in [__file__,m.__file__]: (out/('source-'+Path(module).name)).write_bytes(Path(module).read_bytes())
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    inputs=p.add_mutually_exclusive_group(required=True);inputs.add_argument('--bundle');inputs.add_argument('--data-dir')
    p.add_argument('--output-dir',required=True);p.add_argument('--starting-balance',type=float,default=100);a=p.parse_args()
    if a.bundle:
        from export_research_bundle import load_bundle
        frames,receipt,bundle=load_bundle(a.bundle)
        manifest=[dict(pair=v['pair'],bars=v['bars'],sha256=v['source_feather_sha256']) for v in bundle['candles']]
    else: frames,receipt,manifest=r.load_universe(a.data_dir)
    run(frames,receipt,manifest,a.output_dir,a.starting_balance)


if __name__=='__main__': main()
