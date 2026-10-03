"""Frozen V10 historical OHLC stress replay, separate from forward paper state.

15m OHLC cannot reproduce 30-second quotes. Use next-bar opens for entries,
modeled spreads, and adverse extrema before favorable extrema for exits.
Results are approximation/research evidence, never unseen validation.
"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd
import paper_v10 as m


class MemoryLedger:
    def __init__(self, now, end):
        with tempfile.TemporaryDirectory() as d:
            ledger = m.Ledger(Path(d)/'seed.sqlite3', now)
            self.state = ledger.state
            ledger.db.close()
        self.state['deadline_ms'] = min(now+7*m.DAY,end)
        self.events = []

    def commit(self, event=None):
        if event and event['kind'] in ('OPEN','CLOSE'):
            self.events.append(dict(event))


def prepare(frame, pair):
    f=frame.copy()
    if 'ts' not in f:
        f['ts']=pd.to_datetime(f['date'],utc=True).astype('int64')//1_000_000
    f=f[['ts','open','high','low','close','volume']].sort_values('ts').reset_index(drop=True)
    if f.empty or f.ts.duplicated().any():
        raise ValueError(f'{pair}: empty or duplicate candles')
    if not all(math.isfinite(float(x)) for x in f.to_numpy().flat):
        raise ValueError(f'{pair}: nonfinite candles')
    if not ((f.ts%m.BAR==0)&(f.low>0)&(f.volume>=0)&
            (f.high>=f[['open','close','low']].max(axis=1))&
            (f.low<=f[['open','close']].min(axis=1))).all():
        raise ValueError(f'{pair}: invalid candles')
    # Indicators restart at every gap; never fill a missing candle with a price.
    blocks=(f.ts.diff().fillna(m.BAR)!=m.BAR).cumsum()
    pieces=[]
    for _,block in f.groupby(blocks):
        block=m.indicators(block.reset_index(drop=True))
        block['block_age']=range(1,len(block)+1)
        pieces.append(block)
    return pd.concat(pieces,ignore_index=True)


def quote(mid, spread_bps, now):
    half=spread_bps/20_000
    return dict(bid=float(mid)*(1-half),ask=float(mid)*(1+half),observed_ms=now)


def replay(frames, spread_bps=5, progress=None):
    if spread_bps < 0 or spread_bps > 100:
        raise ValueError('Spread must be 0–100 bps')
    indexes={p:{int(ts):i for i,ts in enumerate(f.ts)} for p,f in frames.items()}
    timeline=sorted(set.union(*[set(v) for v in indexes.values()]))
    if len(timeline)<m.SPEC['warmup_bars']+2:
        raise ValueError('Insufficient historical candles')
    first=timeline[m.SPEC['warmup_bars']]
    end=timeline[-1]+m.BAR
    sessions=[]
    all_trades=[]
    reasons=Counter()
    execution=Counter()
    starts=list(range(first,end,7*m.DAY))
    for number,start in enumerate(starts,1):
        finish=min(start+7*m.DAY,end)
        if progress:
            progress(number,len(starts),start,finish)
        ledger=MemoryLedger(start,finish)
        s=ledger.state
        session_reasons=Counter()
        for now in timeline:
            if not start<=now<finish:
                continue
            rows={p:f.iloc[indexes[p][now]] for p,f in frames.items() if now in indexes[p]}
            qs={p:quote(r.open,spread_bps,now) for p,r in rows.items()}
            signal_frames={}
            for p,f in frames.items():
                i=indexes[p].get(now)
                if i is not None and i>0 and int(f.ts.iloc[i-1])==now-m.BAR and f.block_age.iloc[i-1]>=m.SPEC['warmup_bars']:
                    window=f.iloc[max(0,i-719):i][['ts','open','high','low','close','volume']]
                    if (window.ts.diff().dropna()==m.BAR).all():
                        # Kraken's 720-row response includes one unfinished row.
                        # Recompute the identical rolling-window warm start.
                        signal_frames[p]=m.indicators(window)
            m.manage(ledger,qs,now,signal_frames)
            m.evaluate(ledger,signal_frames,qs,now)
            for r in s['diagnostics']:
                if r.get('candle')==m.iso(now-m.BAR):
                    session_reasons[r['reason']]+=1
                    execution[r.get('execution','WAITING')]+=1
            # A deliberately adverse-first sampled intrabar path. Unknown quote
            # history/spread/liquidity prevents an exact poll-runtime backtest.
            for adverse in (True,False):
                marks={}
                for p,pos in s['positions'].items():
                    r=rows.get(p)
                    if r is not None:
                        use_high=pos['is_short'] if adverse else not pos['is_short']
                        marks[p]=quote(r.high if use_high else r.low,spread_bps,now+(1 if adverse else 2))
                m.manage(ledger,marks,now+(1 if adverse else 2))
            close_marks={p:quote(r.close,spread_bps,now+m.BAR-1) for p,r in rows.items()}
            m.manage(ledger,close_marks,now+m.BAR-1)
            if s['halt_reason'] and not s['positions']:
                break
        # Finish at the last available candle close, retaining missing marks as
        # pending positions rather than inventing end-of-period liquidation.
        last={p:q for p,q in s['last_quotes'].items() if q['observed_ms']>=finish-m.BAR}
        m.manage(ledger,last,finish)
        trades=s['closed']
        pnl=s['balance']-100
        wins=sum(t['profit_abs']>0 for t in trades)
        fees=sum(t['fee_usd'] for t in trades)
        slips=sum(t['slippage_allowance_usd'] for t in trades)
        sessions.append(dict(start=m.iso(start),end=m.iso(finish),starting_balance=100,
            partial=finish-start<7*m.DAY,
            trades=len(trades),entries=s['entries'],net_realized_pnl_usd=pnl,
            ending_realized_balance=s['balance'],pending_positions=len(s['positions']),
            max_drawdown_usd=s['max_drawdown_usd'],wins=wins,fees_usd=fees,
            slippage_allowance_usd=slips,halt_reason=s['halt_reason'],
            signal_reasons=dict(session_reasons)))
        for trade in trades:
            all_trades.append(dict(trade,session_start=m.iso(start),spread_bps=spread_bps))
        reasons.update(session_reasons)
    profits=sum(t['profit_abs'] for t in all_trades if t['profit_abs']>0)
    losses=-sum(t['profit_abs'] for t in all_trades if t['profit_abs']<0)
    full=[s for s in sessions if not s['partial'] and not s['pending_positions']]
    summary=dict(spread_bps=spread_bps,independent_sessions=len(sessions),full_week_sessions=len(full),
        trades=len(all_trades),long_trades=sum(not t['is_short'] for t in all_trades),
        short_trades=sum(t['is_short'] for t in all_trades),
        winning_trades=sum(t['profit_abs']>0 for t in all_trades),
        profit_factor=profits/losses if losses else None,
        summed_independent_session_pnl_usd=sum(s['net_realized_pnl_usd'] for s in sessions),
        median_full_week_pnl_usd=statistics.median(s['net_realized_pnl_usd'] for s in full) if full else None,
        profitable_full_weeks=sum(s['net_realized_pnl_usd']>0 for s in full),
        zero_trade_full_weeks=sum(s['trades']==0 for s in full),
        worst_session_drawdown_usd=max(s['max_drawdown_usd'] for s in sessions),
        fees_usd=sum(t['fee_usd'] for t in all_trades),
        slippage_allowance_usd=sum(t['slippage_allowance_usd'] for t in all_trades),
        pending_positions=sum(s['pending_positions'] for s in sessions),
        reasons=dict(reasons),entry_checks=dict(execution))
    return dict(summary=summary,sessions=sessions,trades=all_trades)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',action='append',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--spread-bps',nargs='+',type=float,default=[5,15])
    args=parser.parse_args()
    output=Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=True)
    reports=[]
    for directory in args.data_dir:
        root=Path(directory)
        frames={}
        manifest=[]
        for pair in m.PAIRS:
            path=root/(pair.replace('/','_')+'-15m.feather')
            frames[pair]=prepare(pd.read_feather(path),pair)
            f=frames[pair]
            manifest.append(dict(pair=pair,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bars=len(f),gap_count=int((f.ts.diff().dropna()!=m.BAR).sum()),
                start=m.iso(int(f.ts.iloc[0])),end=m.iso(int(f.ts.iloc[-1])+m.BAR)))
        for spread in args.spread_bps:
            print(f'Replaying {root.name}, modeled spread {spread:g} bps...',flush=True)
            terminal=sys.stdout
            def progress(number,total,start,finish):
                print(f'  Campaign {number}/{total}: {m.iso(start)} to {m.iso(finish)}',file=terminal,flush=True)
            with contextlib.redirect_stdout(io.StringIO()):
                result=replay(frames,spread,progress)
            name=f'{root.name}-spread-{spread:g}bps'
            report=dict(kind='V10_FROZEN_OHLC_STRESS_REPLAY',version=m.VERSION,spec=m.SPEC,
                input_manifest=manifest,**result,
                limitations=['Q1/Q2 were previously used in strategy research; this is not unseen validation.',
                    '15m OHLC cannot reproduce 30-second quotes, spread history or liquidity.',
                    'Entries use next-bar opens and modeled spreads. Intrabar adverse extrema precede favorable extrema; exits can overshoot levels.',
                    'Seven-day campaigns reset to $100 independently. Summed P&L is not a continuous $100 account return.',
                    'Incomplete final weeks are excluded from full-week statistics. Missing-data end positions remain pending.',
                    'Borrow/funding excluded. No forward ledger or running container is modified.'])
            m.atomic_json(output/(name+'.json'),report)
            if result['trades']:
                pd.DataFrame(result['trades']).to_csv(output/(name+'-trades.csv'),index=False)
            reports.append(dict(dataset=root.name,**result['summary']))
            print(json.dumps(reports[-1],indent=2),flush=True)
    m.atomic_json(output/'v10-backtest-summary.json',dict(version=m.VERSION,reports=reports,
        note='Frozen historical research replay, not a profitability certification.'))
    print(f'Reports saved in {output}. Running V10 unchanged.',flush=True)


if __name__=='__main__':
    main()
