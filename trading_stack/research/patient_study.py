"""Declared passive-entry hypotheses. Internal estimates, never exchange orders."""
import argparse
import json
import math
import statistics
from datetime import datetime,timezone
from pathlib import Path

from trading_stack.cloud_paper.entry_model import FEATURES
from .entry_study import ROOT,SYMBOLS,hashed,iso,load_symbol,read_events,save,settings,stamp


def replay(events,rows,cfg,start,end,pullback,hold):
    indexed={s:{b['time']:b for b in rs} for s,rs in rows.items()};by_time={}
    for e in events:
        if start<=e['at']<end:by_time.setdefault(e['at'],[]).append(e)
    cash=cfg['capital'];peak=cash;day_equity=cash;positions={};pending={};marks={};last_exit={}
    trades=[];blocks={};fees=0.;maximum_drawdown=0.;halt=False;daily_halt=False;gaps=0;orders=0;days={}
    def block(reason):blocks[reason]=blocks.get(reason,0)+1
    def equity():return cash+sum(p['qty']*marks.get(s,p['entry'])*(1-cfg['halfspread'])*(1-cfg['slip'])*(1-cfg['fee']) for s,p in positions.items())
    def sell(s,bid,t,reason):
        nonlocal cash,fees
        p=positions.pop(s);price=bid*(1-cfg['slip']);value=p['qty']*price;fee=value*cfg['fee'];cash+=value-fee;fees+=fee;last_exit[s]=t
        trades.append(dict(symbol=s,family=p['family'],entry_at=iso(p['at']),exit_at=iso(t),entry=p['entry'],exit_price=price,
            quantity=p['qty'],entry_fee=p['entry_fee'],exit_fee=fee,net_pnl=value-fee-p['cost']-p['entry_fee'],reason=reason,holding_hours=(t-p['at'])/3600))
    for t in range(start,end,300):
        current={s:ix[t] for s,ix in indexed.items() if t in ix}
        for s,b in current.items():marks[s]=b['open']
        if t==start or t//86400!=(t-300)//86400:day_equity=equity();daily_halt=False
        if equity()<=day_equity*(1-cfg['daily_loss']):daily_halt=True
        if equity()<=peak*(1-cfg['drawdown']):halt=True
        for s,p in list(positions.items()):
            if s not in current:gaps+=1;continue
            if halt or daily_halt or t-p['at']>=hold:sell(s,current[s]['open']*(1-cfg['halfspread']),t,'RISK' if halt or daily_halt else 'TIME')
        for s,p in list(pending.items()):
            if halt or daily_halt or t>=p['expires'] or s not in current:pending.pop(s);block('pending_canceled')
        for e in sorted(by_time.get(t,[]),key=lambda x:(-x['score'],x['symbol'])):
            s=e['symbol']
            if halt or daily_halt:block('risk_halt');continue
            if any(s not in current for s in positions):block('missing_held_mark');continue
            if s not in current or s in positions or s in pending or len(positions)+len(pending)>=cfg['max_positions']:continue
            if t-last_exit.get(s,-1e10)<cfg['cooldown']:block('cooldown');continue
            atr=e['features'][FEATURES.index('atr_fraction')]*e['reference'];limit=e['reference']-pullback*atr
            if limit<=0 or limit>=current[s]['open']*(1-cfg['halfspread']):block('passive_price_unavailable');continue
            stop=limit*(1-cfg['halfspread'])-min(.75*atr,limit*.003)
            risk_per_unit=limit*(1+cfg['fee'])-stop*(1-cfg['slip'])*(1-cfg['fee'])
            if stop<=0 or risk_per_unit<=0:block('invalid_risk');continue
            eq=equity();reserved=sum(p['qty']*p['entry']*(1+cfg['fee']) for p in pending.values())
            exposure=sum(p['qty']*marks.get(s,p['entry']) for s,p in positions.items())+reserved
            budget=min(cash-reserved,eq*cfg['max_position'],eq*cfg['max_exposure']-exposure)
            qty=min(max(0,budget)/(limit*(1+cfg['fee'])),eq*cfg['risk']/risk_per_unit,e['lagged_volume_cap'])
            qty=math.floor(max(0,qty)*1e8)/1e8
            if qty*limit<5:block('size_or_volume');continue
            target=limit*(1+cfg['fee']+cfg['net_target'])/((1-cfg['slip'])*(1-cfg['fee']))
            pending[s]=dict(qty=qty,entry=limit,stop=stop,target=target,family=e['family'],expires=t+600);orders+=1
        for s,p in list(pending.items()):
            b=current[s];guard=cfg['halfspread']+(.001 if cfg.get('stress') else .0005)
            if b['low']>=p['entry']*(1-guard):continue
            cost=p['qty']*p['entry'];fee=cost*cfg['fee']
            if cost+fee>cash+1e-8:pending.pop(s);block('fill_cash_unavailable');continue
            cash-=cost+fee;fees+=fee;positions[s]=dict(p,at=t,cost=cost,entry_fee=fee);pending.pop(s)
        for s,p in list(positions.items()):
            if s not in current:continue
            b=current[s];bid_open=b['open']*(1-cfg['halfspread'])
            if b['low']*(1-cfg['halfspread'])<=p['stop']:sell(s,min(bid_open,p['stop']),t+299,'STOP')
            elif t>p['at'] and b['high']*(1-cfg['halfspread'])>=p['target']:sell(s,p['target'],t+299,'NET_TARGET')
            marks[s]=b['close']
        eq=equity();peak=max(peak,eq);maximum_drawdown=max(maximum_drawdown,1-eq/peak)
        if eq<=day_equity*(1-cfg['daily_loss']):daily_halt=True
        if eq<=peak*(1-cfg['drawdown']):halt=True
        days[t//86400]=eq
    pnls=[t['net_pnl'] for t in trades];win=sum(max(0,p) for p in pnls);loss=-sum(min(0,p) for p in pnls)
    return dict(start=iso(start),end=iso(end),final_equity=equity(),net_return=equity()/cfg['capital']-1,net_realized=sum(pnls),
        closed_trades=len(trades),open_positions=len(positions),unfilled_limits=len(pending),limits_placed=orders,
        mean_trade_pnl=statistics.mean(pnls) if pnls else None,wins=sum(p>0 for p in pnls),losses=sum(p<0 for p in pnls),
        modeled_fees=fees,maximum_drawdown=maximum_drawdown,drawdown_halted=halt,held_missing_bars=gaps,
        profit_factor=win/loss if loss else None,blocks=blocks,daily_equity=[dict(day=iso(day*86400),equity=value) for day,value in sorted(days.items())],trades=trades)


def config(stress):return dict(settings(stress),stress=stress)
def eligible(result,minimum):return result['net_return']>0 and (result['mean_trade_pnl'] or 0)>0 and result['closed_trades']>=minimum and not result['drawdown_halted'] and not result['held_missing_bars']


def develop():
    if (ROOT/'patient_validation_started.json').exists():raise ValueError('Reserved outcomes opened; development is frozen')
    protocol=json.loads((ROOT/'patient_protocol.json').read_text());payload=read_events('development_events.json.gz')
    if payload['feature_source_sha256']!=hashed(Path(__file__).parents[1]/'cloud_paper/entry_model.py'):raise ValueError('Entry features changed')
    rows={s:load_symbol(s,['2026-05','2026-06','2026-07','2026-08']) for s in SYMBOLS};events=payload['events'];results=[]
    a=stamp(protocol['training_period'][0]);b=stamp(protocol['training_period'][1]);end=stamp(protocol['calibration_period'][1])
    for pullback in protocol['fixed_grid']['pullback_atr']:
        for minutes in protocol['fixed_grid']['hold_minutes']:
            result=dict(pullback_atr=pullback,hold_minutes=minutes)
            for period,start,finish,minimum in [('training',a,b,100),('calibration',b,end,20)]:
                result[period]={mode:replay(events,rows,config(mode=='stress'),start,finish,pullback,minutes*60) for mode in ('base','stress')}
            result['eligible']=all(eligible(result[period][mode],100 if period=='training' else 20) for period in ('training','calibration') for mode in ('base','stress'));results.append(result)
            print(json.dumps({'pullback':pullback,'hold_minutes':minutes,'training_return':result['training']['base']['net_return'],
                'calibration_return':result['calibration']['base']['net_return'],'calibration_trades':result['calibration']['base']['closed_trades'],
                'calibration_stress_return':result['calibration']['stress']['net_return'],'eligible':result['eligible']}),flush=True)
    qualified=[r for r in results if r['eligible']];selected=max(qualified,key=lambda r:(r['calibration']['stress']['net_return'],-r['calibration']['base']['closed_trades'])) if qualified else None
    save(ROOT/'patient_development_results.json',dict(kind='DEVELOPMENT ONLY; LIMIT FILLS UNVERIFIED',candidates=results))
    freeze=dict(status='FROZEN_FOR_RESERVED_VALIDATION' if selected else 'REJECTED_IN_DEVELOPMENT',
        selected={k:selected[k] for k in ['pullback_atr','hold_minutes']} if selected else None,
        feature_source_sha256=payload['feature_source_sha256'],events_sha256=hashed(ROOT/'development_events.json.gz'),
        protocol_sha256=hashed(ROOT/'patient_protocol.json'),cost_settings_protocol_sha256=hashed(ROOT/'protocol.json'),manifest_sha256=hashed(ROOT/'manifest.json'),research_source_sha256=hashed(__file__),
        dependencies_sha256=hashed(Path(__file__).with_name('entry_study.py')),frozen_at=datetime.now(timezone.utc).isoformat())
    save(ROOT/'patient_frozen_selection.json',freeze);print(json.dumps(freeze),flush=True)


def validate():
    freeze=json.loads((ROOT/'patient_frozen_selection.json').read_text())
    if freeze['status']!='FROZEN_FOR_RESERVED_VALIDATION':raise ValueError('No patient candidate qualifies; reserved outcomes stay closed')
    for key,path in [('protocol_sha256',ROOT/'patient_protocol.json'),('research_source_sha256',__file__),('dependencies_sha256',Path(__file__).with_name('entry_study.py')),
        ('feature_source_sha256',Path(__file__).parents[1]/'cloud_paper/entry_model.py'),('events_sha256',ROOT/'development_events.json.gz'),
        ('cost_settings_protocol_sha256',ROOT/'protocol.json'),('manifest_sha256',ROOT/'manifest.json')]:
        if freeze[key]!=hashed(path):raise ValueError('Frozen patient study changed')
    save(ROOT/'patient_validation_started.json',dict(at=datetime.now(timezone.utc).isoformat(),freeze_sha256=hashed(ROOT/'patient_frozen_selection.json')))
    from .entry_study import prepare
    events=prepare(['2026-08','2026-09'],'patient_validation_events.json.gz')['events'];rows={s:load_symbol(s,['2026-08','2026-09']) for s in SYMBOLS}
    a=stamp('2026-09-01T00:00:00Z');b=stamp('2026-10-01T00:00:00Z');p=freeze['selected']
    result={mode:replay(events,rows,config(mode=='stress'),a,b,p['pullback_atr'],p['hold_minutes']*60) for mode in ('base','stress')}
    result.update(kind='RESERVED HISTORICAL VALIDATION; NOT LIVE P&L',selection=freeze,passes_historical_gate=all(eligible(result[m],100) for m in ('base','stress')),
        limit_fills_verified=False,eligible_for_live_money=False)
    save(ROOT/'patient_validation_results.json',result);print(json.dumps({m:{k:result[m][k] for k in ['net_return','closed_trades','mean_trade_pnl']} for m in ('base','stress')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['develop','validate']);stage=parser.parse_args().stage
    develop() if stage=='develop' else validate()
