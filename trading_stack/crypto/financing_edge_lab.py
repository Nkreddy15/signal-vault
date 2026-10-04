"""Current-eligibility and discrete-financing research; never trading activation."""
import argparse
import hashlib
import itertools
import math
from pathlib import Path

import numpy as np
import multi_strategy_lab as m
import regime_swing_lab as r
import durable_trend_lab as d

VERSION='FINANCING-EDGE-LAB-1'
CURRENT_US_PAIRS=frozenset(p+'/USD' for p in (
    'BTC','ETH','XRP','SOL','SUI','DOGE','ZEC','PEPE','ADA','AVAX','LINK','RENDER','BCH','LTC','PENGU'))
PROFILES=dict(zero_control=(0.,0.),illustrative_light=(.0001,.0001),
    illustrative_medium=(.00025,.00025),illustrative_heavy=(.0005,.0005))
SOURCES=dict(eligibility='https://support.kraken.com/articles/getting-started-us-margin',
    financing='https://support.kraken.com/articles/us-margin-fees',
    fee_basis='https://support.kraken.com/articles/206161568-what-are-the-fees-opening-and-rollover-for-trading-using-margin-')
LIMITATIONS=[
    'Reused development data and a post-selected short-only hypothesis; not independent validation.',
    'Current US pair list checked October 3, 2026; historical March–June eligibility and product availability are not reconstructed.',
    'Illustrative rates, not historical or current execution quotes. Actual rates are dynamic and must be captured at order time.',
    'Full notional is reserved: no leverage increase. Actual collateral, liquidation, borrow availability and account minimums remain unmodeled.',
    'Opening and four-hour fees use a simplified shadow USD conversion of borrowed-asset charges at observed marks.',
    'Overdue charges are assessed when the feed returns, with due/assessment/quote timestamps; missing execution quotes are not invented.',
    'Only Kraken taker tiers are used. These remain cost sensitivities, not venue-native performance evidence.',
    'Operating costs are user-supplied sensitivities. No paper entry resumes or broker orders.',
]


def compile_research(frames,policy,direction):
    if policy not in ('archive24_control','current_us_supported_sensitivity') or direction not in ('both','short_only'):
        raise ValueError('Unknown financing research policy')
    selected=frames if policy=='archive24_control' else {p:f for p,f in frames.items() if p in CURRENT_US_PAIRS}
    if not selected:
        raise ValueError('No assets in the eligibility intersection')
    # Apply eligibility before ranking; do not first rank unsupported assets
    # and then delete their orders. The original formation universe is retained.
    market,exits,receipts=d.compile_research(selected,'synthetic_long_short')
    filtered=[]
    for now,rows in market:
        filtered.append((now,{pair:(bar,[s for s in signals if s.family=='weekly_leader_28d'
            and (direction=='both' or s.side==-1)]) for pair,(bar,signals) in rows.items()}))
    return filtered,exits,receipts,sorted(selected)


def run(frames,receipt,manifest,out,daily_cost=.1):
    if not math.isfinite(daily_cost) or daily_cost<0:
        raise ValueError('Operating-cost sensitivity must be finite and nonnegative')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    reports=[];input_receipts=[]
    costs=(0.,daily_cost) if daily_cost else (0.,)
    expected=2*2*2*len(PROFILES)*2*len(costs)
    policies=('archive24_control','current_us_supported_sensitivity')
    for policy,direction in itertools.product(policies,('both','short_only')):
        print('Compiling '+policy+'/'+direction,flush=True)
        market,exits,rankings,pairs=compile_research(frames,policy,direction)
        market=[row for row in market if row[0]>=r.START]
        if len(market)<96:
            raise ValueError('Insufficient research candles')
        windows=m.month_windows(market)
        input_receipts.append(dict(policy=policy,direction=direction,included=pairs,
            excluded=sorted(set(frames)-set(pairs))))
        m.save_json(out/(policy+'-'+direction+'-rankings.json'),dict(rankings=rankings,pairs=pairs))
        for risk,profile,execution,cost in itertools.product(('balanced','aggressive'),PROFILES,
                ('trigger','extrema'),costs):
            opening,rollover=PROFILES[profile]
            cfg=m.Config(family='weekly_leader_28d',risk=risk,mode='synthetic_long_short',
                fee_profile='kraken_spot',spread_bps=15,execution=execution,slippage=.001,
                short_carry_per_day=0,short_opening_fee=opening,short_rollover_per_4h=rollover,
                daily_operating_cost_usd=cost)
            name=f'{policy}-{direction}-{risk}-{profile}-{execution}-cost{cost:g}'
            result=m.simulate(market,cfg,allowed_families=d.FAMILIES,scheduled_exits=exits)
            months=[]
            for month,lo,hi,partial in windows:
                part=m.simulate(market,cfg,lo,hi,allowed_families=d.FAMILIES,scheduled_exits=exits)
                months.append(dict(month=month,partial=partial,**part['summary']))
            full=[v for v in months if not v['partial']]
            row=dict(name=name,policy=policy,direction=direction,financing_profile=profile,
                config=m.asdict(cfg),**result['summary'],complete_months=len(full),
                positive_months=sum(v['return_pct']>0 for v in full),
                median_month_return_pct=float(np.median([v['return_pct'] for v in full])) if full else None,
                by_side={str(side):dict(trades=sum(t['side']==side for t in result['trades']),
                    pnl=sum(t['pnl'] for t in result['trades'] if t['side']==side)) for side in (1,-1)})
            row['numerical_development_screen_pass']=bool(len(full)>=3 and row['trades']>=20
                and row['return_pct']>0 and row['median_month_return_pct']>0
                and row['positive_months']>=math.ceil(.6*len(full))
                and row['profit_factor'] is not None and row['profit_factor']>=1.1
                and row['max_drawdown_pct']<=100*cfg.drawdown_limit and not row['pending_positions'])
            row['activation_eligible']=False
            result.update(version=VERSION,policy=policy,direction=direction,financing_profile=profile,
                monthly_independent_100=months,limitations=LIMITATIONS,included_pairs=pairs,
                input_manifest=manifest,formation_universe=receipt)
            m.save_json(out/(name+'.json'),result)
            reports.append(row)
            print(f"[{len(reports)}/{expected}] {name}: ${row['ending_equity']:.2f}; {row['trades']} trades; DD {row['max_drawdown_pct']:.2f}%",flush=True)
            m.save_json(out/'financing-progress.json',dict(version=VERSION,completed=len(reports),expected=expected,reports=reports))
    summary=dict(version=VERSION,status='RESEARCH_ONLY_NO_ACTIVATION',reports=reports,
        formation_universe=receipt,input_manifest=manifest,pair_receipts=input_receipts,
        financing_profiles={k:dict(opening_rate=v[0],rollover_rate_per_4h=v[1]) for k,v in PROFILES.items()},
        sources=SOURCES,source_checked='2026-10-03',limitations=LIMITATIONS,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        accounting_sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
        daily_source_sha256=hashlib.sha256(Path(r.__file__).read_bytes()).hexdigest(),
        strategy_source_sha256=hashlib.sha256(Path(d.__file__).read_bytes()).hexdigest())
    m.save_json(out/'financing-summary.json',summary)
    for module in [__file__,m.__file__,r.__file__,d.__file__]:
        (out/('source-'+Path(module).name)).write_bytes(Path(module).read_bytes())
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    inputs=p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--bundle');inputs.add_argument('--data-dir')
    p.add_argument('--output-dir',required=True)
    p.add_argument('--daily-operating-cost-usd',type=float,default=.1)
    a=p.parse_args()
    if a.bundle:
        from export_research_bundle import load_bundle
        frames,receipt,bundle=load_bundle(a.bundle)
        manifest=[dict(pair=v['pair'],bars=v['bars'],sha256=v['source_feather_sha256']) for v in bundle['candles']]
    else:
        frames,receipt,manifest=r.load_universe(a.data_dir)
    run(frames,receipt,manifest,a.output_dir,a.daily_operating_cost_usd)


if __name__=='__main__':
    main()
