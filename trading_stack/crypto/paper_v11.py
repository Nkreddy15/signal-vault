"""Isolated $500/48h prospective failed-rebound trial. Public data, no orders."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import math
import os
import signal
import sqlite3
import time
from pathlib import Path

import pandas as pd
import bear_regime_lab as b
import durable_trend_lab as d
import financing_edge_lab as f
import multi_strategy_lab as m
from paper_final import atomic_json, iso

VERSION='V11-PAPER-500-1'
PAIRS=tuple(sorted(f.CURRENT_US_PAIRS))
SPEC=dict(strategy='failed_rebound',starting_balance=500.,session_hours=48,risk_fraction=.03,
    max_open=6,max_allocation=.8,drawdown_limit=.5,daily_loss_limit=.2,
    opening_financing_rate=.0001,rollover_rate_per_4h=.0001,slippage=.001,
    operating_cost_per_day=.1,max_spread=.002,quote_max_age_ms=90000,entry_grace_ms=600000,
    max_hold_days=28,decision='Closed UTC day, next observed public bid/ask',pairs=list(PAIRS),
    fee_profile='kraken_spot',financing='Illustrative light rates, not broker quotes',
    execution='Synthetic short; observed quote stops/trailing, no intrabar replay')
SPEC['taker_tiers']=[list(v) for v in m.TIERS]
SPEC['signal_sha256']=hashlib.sha256(Path(b.__file__).read_bytes()).hexdigest()
SPEC['indicators_sha256']=hashlib.sha256(Path(d.__file__).read_bytes()+Path(d.r.__file__).read_bytes()).hexdigest()


def has_held_positions(state):
    if isinstance(state,dict):
        return bool(state.get('positions')) or any(has_held_positions(v) for v in state.values())
    if isinstance(state,list):return any(has_held_positions(v) for v in state)
    return False


class Ledger:
    def __init__(self,path,now):
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
        row=self.db.execute('SELECT payload FROM state WHERE id=1').fetchone()
        if row:
            self.state=json.loads(row[0])
            if self.state.get('version')!=VERSION or self.state.get('spec')!=SPEC:
                raise ValueError('Existing account specification differs; no reset allowed')
        else:
            self.state=dict(version=VERSION,spec=SPEC,started_ms=now,deadline_ms=now+48*3600000,
                balance=500.,positions={},closed=[],fills=[],events=[],next_id=1,boundary=None,
                last_daily_exit=None,risk_day=now//m.DAY,day_start_equity=500.,peak_equity=500.,
                max_drawdown_usd=0.,daily_halt=False,halt_reason=None,status='STARTING',cycles=0,
                last_success_ms=None,heartbeat_ms=now,last_quotes={},diagnostics=[],errors=[],
                operating_cost_usd=0.,last_cost_ms=now,intervals_evaluated=0,entries=0,drain=False)
            self.commit()

    def event(self,kind,**fields): self.state['events'].append(dict(kind=kind,**fields))

    def commit(self):
        with self.db:
            for event in self.state['events']:
                self.db.execute('INSERT INTO events(payload) VALUES(?)',(json.dumps(event,allow_nan=False),))
            self.state['events']=[]
            self.db.execute('INSERT OR REPLACE INTO state VALUES(1,?)',(json.dumps(self.state,allow_nan=False),))


def daily_rows(rows,now,pair):
    raw=m.normalized(pd.DataFrame(rows,columns=['ts','open','high','low','close','volume']))
    if (raw.ts % m.DAY != 0).any(): raise ValueError(f'{pair}: non-UTC daily timestamps')
    cutoff=now//m.DAY*m.DAY
    raw=raw[raw.ts<cutoff].copy()
    if len(raw)<90 or int(raw.ts.iloc[-1])!=cutoff-m.DAY:
        raise ValueError(f'{pair}: insufficient or stale closed daily history')
    features=d.daily_features(raw,cutoff)
    blocks=(features.ts.diff().fillna(m.DAY)!=m.DAY).cumsum()
    features['prev_close']=features.groupby(blocks).close.shift()
    features['rebound2']=features.groupby(blocks).close.transform(lambda x:x.shift(1)/x.shift(3)-1)
    if int(features.age.iloc[-1])<29:raise ValueError(f'{pair}: daily warm-up reset by missing days')
    return features


def quotes_from(tickers,now):
    quotes={};errors=[]
    for pair in PAIRS:
        t=tickers.get(pair,{})
        try:
            bid,ask=float(t.get('bid') or 0),float(t.get('ask') or 0)
            stamp=t.get('timestamp')
            if not(math.isfinite(bid) and math.isfinite(ask) and 0<bid<=ask): raise ValueError('invalid bid/ask')
            if stamp is not None and not -5000<=now-float(stamp)<=SPEC['quote_max_age_ms']: raise ValueError('stale quote')
            quotes[pair]=dict(bid=bid,ask=ask,observed_ms=now)
        except (ValueError,TypeError): errors.append(f'{pair}: invalid or stale public quote')
    return quotes,errors


def fees(state,now):
    result=m.Fees(SPEC['fee_profile'])
    for ts,notional in state['fills']: result.record(ts,notional)
    result.rate(now)
    return result


def trade_row(pos,q,rate,now,reason=None):
    price=q['ask']*(1+SPEC['slippage'])
    gross=pos['amount']*(pos['open_rate']-price)
    exit_fee=pos['amount']*price*rate
    net=gross-pos['entry_fee']-exit_fee-pos['opening_financing_fee']-pos['rollover_paid']
    result=dict(pos,current_rate=price,profit_abs=net,profit_ratio=net/pos['stake_amount'],
        gross_profit_abs=gross,fee_usd=pos['entry_fee']+exit_fee,
        financing_usd=pos['opening_financing_fee']+pos['rollover_paid'],is_open=reason is None,
        timeframe='1d',price_observed_at=iso(q['observed_ms']),mark_stale=now-q['observed_ms']>SPEC['quote_max_age_ms'])
    if reason:result.update(close_ms=now,close_date=iso(now),close_rate=price,exit_reason=reason,exit_fee=exit_fee)
    return result


def equity(state,now):
    rate=fees(state,now).rate(now);value=state['balance']
    for pair,pos in state['positions'].items():
        q=state['last_quotes'].get(pair)
        if q:
            mark=trade_row(pos,q,rate,now)
            value+=mark['gross_profit_abs']-(mark['fee_usd']-pos['entry_fee'])
    return value


def close(ledger,pair,q,now,reason):
    s=ledger.state;pos=s['positions'].pop(pair)
    row=trade_row(pos,q,fees(s,now).rate(now),now,reason)
    s['balance']+=row['gross_profit_abs']-row['exit_fee']
    s['fills'].append([now,pos['amount']*row['close_rate']]);s['closed'].append(row)
    ledger.event('CLOSE',**row)
    print(f"CLOSE {pair} {reason} net=${row['profit_abs']:.4f}",flush=True)


def manage(ledger,quotes,now):
    s=ledger.state;s['last_quotes'].update(quotes)
    cost_until=min(now,s['deadline_ms'])
    charge=SPEC['operating_cost_per_day']*max(0,cost_until-s['last_cost_ms'])/m.DAY
    s['balance']-=charge;s['operating_cost_usd']+=charge;s['last_cost_ms']=max(s['last_cost_ms'],cost_until)
    for pair,pos in s['positions'].items():
        q=quotes.get(pair)
        if not q or now-q['observed_ms']>SPEC['quote_max_age_ms']:continue
        while pos['next_rollover_ms']<=now:
            amount=pos['amount']*(q['bid']+q['ask'])/2*SPEC['rollover_rate_per_4h']
            s['balance']-=amount;pos['rollover_paid']+=amount
            ledger.event('ROLLOVER',pair=pair,due_ms=pos['next_rollover_ms'],assessed_ms=now,
                quote_ms=q['observed_ms'],amount_usd=amount)
            pos['next_rollover_ms']+=4*3600000
    marked=equity(s,now);s['peak_equity']=max(marked,s['peak_equity'])
    s['max_drawdown_usd']=max(s['max_drawdown_usd'],s['peak_equity']-marked)
    if s['risk_day']!=now//m.DAY and all(p in quotes for p in s['positions']):
        s.update(risk_day=now//m.DAY,day_start_equity=marked,daily_halt=False)
    if marked<=s['peak_equity']*(1-SPEC['drawdown_limit']):s['halt_reason']='SESSION_LOSS_LIMIT'
    if marked<=s['day_start_equity']*(1-SPEC['daily_loss_limit']):s['daily_halt']=True
    if now>=s['deadline_ms'] and not s['halt_reason']:s['halt_reason']='SESSION_COMPLETE'
    for pair,pos in list(s['positions'].items()):
        q=quotes.get(pair)
        if not q or now-q['observed_ms']>SPEC['quote_max_age_ms']:continue
        price=q['ask']*(1+SPEC['slippage'])
        reason=s['halt_reason'] or ('DAILY_LOSS_LIMIT' if s['daily_halt'] else None) or pos.get('pending_exit')
        if not reason and price>=pos['stop_price']:reason='HARD_STOP'
        if not reason and now-pos['open_ms']>=SPEC['max_hold_days']*m.DAY:reason='TIME_EXIT'
        if reason:close(ledger,pair,q,now,reason);continue
        pos['peak_price']=min(pos['peak_price'],q['bid'])
        if pos['peak_price']<=pos['open_rate']*(1-pos['initial_stop']):
            pos['stop_price']=min(pos['stop_price'],pos['peak_price']*(1+pos['initial_stop']))
        pos['price_history']=(pos.get('price_history',[])+[price])[-80:]


def evaluate(ledger,frames,quotes,now):
    s=ledger.state;day=now//m.DAY*m.DAY;expected=day-m.DAY
    rows={p:list(raw.itertuples(index=False))[-1] for p,raw in frames.items()
        if len(raw) and int(raw.ts.iloc[-1])==expected}
    if set(rows)!=set(PAIRS):
        s['diagnostics']=[dict(pair=p,reason='Waiting for complete current daily ranking universe',execution='WAITING') for p in PAIRS]
        return
    choices,desired=b.decisions(rows,expected)['failed_rebound']
    if s['last_daily_exit']!=expected:
        for pair,pos in s['positions'].items():
            if desired.get(pair,0)!=-1:pos['pending_exit']='BEAR_REGIME_OR_TREND_EXIT'
        s['last_daily_exit']=expected
    first=s['boundary'] is None
    if not first and s['boundary']>=expected:return
    s['boundary']=expected
    if not first:s['intervals_evaluated']+=1
    s['diagnostics']=[dict(pair=p,side='SHORT' if p in choices else 'WAIT',regime='DAILY FAILED REBOUND',
        reason='Closed-day failed rebound qualifies' if p in choices else 'No qualifying BTC regime/failed rebound',execution='WAITING') for p in PAIRS]
    diag={v['pair']:v for v in s['diagnostics']}
    for pair,(side,score,row) in sorted(choices.items(),key=lambda v:(-v[1][1],v[0])):
        q=quotes.get(pair);reason=None
        if first:reason='Initial boundary only; no historical entry'
        elif now-day>SPEC['entry_grace_ms']:reason='Missed daily entry window; no late fill'
        elif s['halt_reason'] or s['daily_halt'] or s['drain']:reason=s['halt_reason'] or ('DAILY_LOSS_LIMIT' if s['daily_halt'] else 'DRAINING')
        elif pair in s['positions']:reason='Position already held'
        elif len(s['positions'])>=m.slots(equity(s,now)):reason='Portfolio capacity'
        elif q is None or now-q['observed_ms']>SPEC['quote_max_age_ms']:reason='No fresh bid/ask'
        elif q['ask']/q['bid']-1>SPEC['max_spread']:reason='Spread above 0.20%'
        elif abs((q['bid']+q['ask'])/2/row.close-1)>max(.01,3*row.atr):reason='Opening price drift'
        if reason:diag[pair]['execution']=reason;continue
        marked=equity(s,now);rate=fees(s,now).rate(now);capacity=m.slots(marked)
        reserved=sum(p['stake_amount'] for p in s['positions'].values())
        stake=min(marked*.03/(row.stop+2*rate+2*SPEC['slippage']+SPEC['opening_financing_rate']),
            .8*marked/capacity,max(0,.8*marked-reserved),max(0,s['balance']-reserved)/(1+rate+SPEC['opening_financing_rate']))
        if stake<5:diag[pair]['execution']='Insufficient unreserved paper cash';continue
        price=q['bid']*(1-SPEC['slippage']);entry_fee=stake*rate;opening=stake*SPEC['opening_financing_rate']
        pos=dict(trade_id=f"v11-{s['next_id']}",pair=pair,is_short=True,stake_amount=stake,amount=stake/price,
            open_rate=price,open_ms=now,open_date=iso(now),signal_ms=expected+m.DAY-m.BAR,
            entry_fee=entry_fee,opening_financing_fee=opening,rollover_paid=0.,next_rollover_ms=now+4*3600000,
            initial_stop=float(row.stop),stop_price=price*(1+row.stop),target_price=None,peak_price=price,
            enter_tag='failed_rebound',signal_reason='BTC bear regime, 2-day rebound followed by lower close',
            target_rule='No fixed profit target',exit_logic='ATR stop/trailing, closed-day BTC/EMA exit, 48h campaign end',
            price_history=[price])
        s['balance']-=entry_fee+opening;s['fills'].append([now,stake]);s['positions'][pair]=pos
        s['entries']+=1;s['next_id']+=1;diag[pair]['execution']='OPENED'
        ledger.event('OPEN',**pos);print(f'OPEN SYNTHETIC SHORT {pair} stake=${stake:.2f}',flush=True)
    ledger.event('DAILY_SCAN',closed_day_ms=expected,first_scan=first,diagnostics=s['diagnostics'])


def publish(ledger,directory,now):
    s=ledger.state;rate=fees(s,now).rate(now)
    opened=[trade_row(pos,s['last_quotes'][p],rate,now) for p,pos in s['positions'].items() if p in s['last_quotes']]
    stale=any(t['mark_stale'] for t in opened) or len(opened)!=len(s['positions'])
    realized=sum(t['profit_abs'] for t in s['closed']);unrealized=sum(t['profit_abs'] for t in opened) if not stale else None
    crypto=dict(bot_state=s['status'],config=dict(strategy=VERSION+' / failed-rebound shorts',timeframe='1d',
        exchange='Kraken public quotes',runmode='SYNTHETIC PAPER',dry_run=True),open_trades=opened,
        closed_trades=list(reversed(s['closed'])),open_trade_count=len(s['positions']),closed_trade_count=len(s['closed']),
        closed_pnl_usd=realized-s['operating_cost_usd'],trade_realized_pnl_usd=realized,
        open_pnl_usd=unrealized,marked_equity=None if stale else equity(s,now),
        open_exposure_usd=sum(p['stake_amount'] for p in s['positions'].values()),marks_stale=stale,
        starting_balance=500.,cash_balance=s['balance'],operating_cost_usd=s['operating_cost_usd'],
        profit=dict(closed_trade_count=len(s['closed'])),errors=s['errors'])
    payload=dict(version=VERSION,status=s['status'],crypto=crypto,started_at=iso(s['started_ms']),
        ends_at=iso(s['deadline_ms']),next_evaluation_at=iso((now//m.DAY+1)*m.DAY),
        last_success_ms=s['last_success_ms'],heartbeat_ms=s['heartbeat_ms'],cycles=s['cycles'],
        intervals_evaluated=s['intervals_evaluated'],entries=s['entries'],diagnostics=s['diagnostics'],
        note='$500 / 48h synthetic failed-rebound trial. Daily UTC signals; no forced entries or broker orders. Light illustrative borrowing, taker tiers, observed spread, 0.10% slippage per side, $0.10/day running allowance.',
        safety=dict(live_trading=False,crypto_max_open_trades=6,crypto_stake_usd='3% risk / cash limits',
            crypto_stoploss='6–20% ATR stop with quote-based trailing',crypto_roi_reference='No fixed profit target',
            crypto_drawdown_lock='50% peak / 20% UTC-day triggers; gaps may exceed them',session_hours=48))
    atomic_json(Path(directory)/'summary.json',payload);return payload


class Runner:
    def __init__(self,ledger,directory,exchange):self.ledger,self.directory,self.exchange=ledger,Path(directory),exchange;self.frames={}
    def fresh_quotes(self):
        start=time.monotonic();ticks=self.exchange.fetch_tickers(list(PAIRS));now=int(time.time()*1000)
        if time.monotonic()-start>15:raise ValueError('Quote response exceeded 15 seconds')
        q,errors=quotes_from(ticks,now);self.ledger.state['errors'].extend(errors)
        if not q:raise ValueError('No fresh public bid/ask')
        return q,now
    def cycle(self):
        s=self.ledger.state;s['errors']=[];s['drain']=(self.directory/'drain').exists()
        if (self.directory/'stop').exists():s['halt_reason']='USER_STOP'
        try:
            q,now=self.fresh_quotes();manage(self.ledger,q,now)
            expected=now//m.DAY*m.DAY-m.DAY
            if not s['halt_reason']:
                changed=False
                for pair in PAIRS:
                    if pair in self.frames and int(self.frames[pair].ts.iloc[-1])==expected:continue
                    try:
                        self.frames[pair]=daily_rows(self.exchange.fetch_ohlcv(pair,'1d',limit=720),now,pair)
                        changed=True
                    except Exception as exc:self.frames.pop(pair,None);s['errors'].append(f'{pair}: {type(exc).__name__}')
                if changed:
                    atomic_json(self.directory/'candles.json',dict(pairs={p:[dict(time=iso(int(v.ts)),open=float(v.open),
                        high=float(v.high),low=float(v.low),close=float(v.close),volume=float(v.volume)) for v in raw.itertuples()] for p,raw in self.frames.items()}))
                    q,now=self.fresh_quotes()
                manage(self.ledger,q,now);evaluate(self.ledger,self.frames,q,now);manage(self.ledger,q,now)
            s['cycles']+=1;s['last_success_ms']=now
            s['status']='ENDING_PENDING_QUOTES' if s['halt_reason'] and s['positions'] else s['halt_reason'] or ('DRAINING' if s['drain'] else 'DAILY_LOSS_LIMIT' if s['daily_halt'] else 'DEGRADED' if s['errors'] else 'RUNNING')
        except Exception as exc:
            s['status']='DEGRADED';s['errors'].append(type(exc).__name__+': public data cycle failed')
        now=int(time.time()*1000);s['heartbeat_ms']=now;self.ledger.commit();return publish(self.ledger,self.directory,now)


def main():
    p=argparse.ArgumentParser();p.add_argument('--state-dir',default=os.getenv('PAPER_V11_STATE_DIR','/freqtrade/data/paper-v11-500'))
    p.add_argument('--preflight',action='store_true');p.add_argument('--once',action='store_true');a=p.parse_args()
    import ccxt
    exchange=ccxt.kraken({'enableRateLimit':True,'timeout':10000})  # no credentials or order methods
    if a.preflight:
        now=int(time.time()*1000)
        for pair in PAIRS:daily_rows(exchange.fetch_ohlcv(pair,'1d',limit=720),now,pair)
        q,errors=quotes_from(exchange.fetch_tickers(list(PAIRS)),int(time.time()*1000))
        if errors or len(q)!=len(PAIRS):raise SystemExit('Preflight failed: incomplete fresh bid/ask universe')
        print('Verified closed daily history and fresh quotes for all 15 assets. No account created.');return 0
    directory=Path(a.state_dir);directory.mkdir(parents=True,exist_ok=True)
    lock=(directory/'runtime.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    ledger=Ledger(directory/'ledger.sqlite3',int(time.time()*1000));runner=Runner(ledger,directory,exchange)
    running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        while running:
            result=runner.cycle()
            if a.once:return 0 if result['status']=='RUNNING' else 2
            if result['status'] in ('SESSION_COMPLETE','SESSION_LOSS_LIMIT','USER_STOP') and not ledger.state['positions']:
                print('TRIAL ENDED; all synthetic positions closed, ledger preserved.',flush=True)
                return 0
            for _ in range(30):
                if not running:break
                time.sleep(1)
        ledger.state['status']='STOPPED';ledger.commit();publish(ledger,directory,int(time.time()*1000))
    finally:ledger.db.close();lock.close()


if __name__=='__main__':raise SystemExit(main())
