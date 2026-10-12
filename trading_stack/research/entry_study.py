"""Chronological entry study on checksum-verified archives; never writes a trading account."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import zipfile
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path

from trading_stack.cloud_paper.entry_model import FEATURES,propose,probability

ROOT=Path(__file__).resolve().parent/'entry_study_20261012'
SYMBOLS=('BTCUSD','ETHUSD','SOLUSD','XRPUSD','DOGEUSD','ADAUSD')


def stamp(value):return int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp())
def iso(t):return datetime.fromtimestamp(t,timezone.utc).isoformat().replace('+00:00','Z')
def hashed(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,data):Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def settings(stress=False):
    p=json.loads((ROOT/'protocol.json').read_text())
    return dict(capital=500.,fee=p['fee_per_side'],slip=p['slippage_per_side']*(2 if stress else 1),
        halfspread=p['maximum_spread_fraction']/2*(2 if stress else 1),net_target=.003,
        max_positions=4,risk=.005,max_position=.2,max_exposure=.6,daily_loss=.02,drawdown=.1,
        hold=3600,cooldown=600)


def load_symbol(symbol,months):
    manifest=json.loads((ROOT/'manifest.json').read_text());expected={r['file']:r['sha256'] for r in manifest['files']}
    rows=[]
    for month in months:
        name=f'{symbol}-5m-{month}.zip';raw=(ROOT/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected.get(name):raise ValueError('Archive hash mismatch')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.namelist()!=[name[:-4]+'.csv']:raise ValueError('Unexpected archive member')
            info=archive.infolist()[0]
            if info.file_size>5000000:raise ValueError('Uncompressed archive exceeds bound')
            for r in csv.DictReader(io.StringIO(archive.read(info).decode())):
                t=float(r['open_time']);t=t/1e6 if t>1e14 else t/1000 if t>1e10 else t
                b=dict(time=int(t),**{k:float(r[k]) for k in ('open','high','low','close','volume','quote_volume','taker_buy_base_volume')})
                year,mon=map(int,month.split('-'));following=f'{year+int(mon==12):04d}-{mon%12+1:02d}-01T00:00:00Z'
                if b['time']%300 or not stamp(month+'-01T00:00:00Z')<=b['time']<stamp(following):raise ValueError('Invalid timestamp')
                if not all(math.isfinite(v) for v in b.values()) or not 0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:raise ValueError('Invalid archive OHLC')
                if b['volume']<0 or b['quote_volume']<0 or not 0<=b['taker_buy_base_volume']<=b['volume']+1e-7:raise ValueError('Invalid archive volume')
                rows.append(b)
    rows.sort(key=lambda b:b['time'])
    if any(b['time']<=a['time'] for a,b in zip(rows,rows[1:])):raise ValueError('Duplicate archive timestamps')
    return rows


def levels(c,reference,cfg):
    bid=reference*(1-cfg['halfspread']);entry=reference*(1+cfg['halfspread'])*(1+cfg['slip'])
    stop=bid-c['stop_distance']
    target=entry*(1+cfg['fee']+cfg['net_target'])/((1-cfg['slip'])*(1-cfg['fee']))
    return entry,stop,target


def outcome(rows,index,c,cfg):
    future=rows[index:index+13]
    if len(future)<13 or any(b['time']-a['time']!=300 for a,b in zip(future,future[1:])):return None
    entry,stop,target=levels(c,future[0]['open'],cfg)
    if stop<=0:return None
    for b in future[:12]:
        if b['low']*(1-cfg['halfspread'])<=stop:
            bid=min(b['open']*(1-cfg['halfspread']),stop);reason='STOP'
        elif b['high']*(1-cfg['halfspread'])>=target:bid=target;reason='NET_TARGET'
        else:continue
        exit_price=bid*(1-cfg['slip']);net=exit_price*(1-cfg['fee'])-entry*(1+cfg['fee'])
        return dict(label=int(reason=='NET_TARGET'),net_fraction=net/entry,exit_at=b['time']+299,reason=reason)
    b=future[-1];exit_price=b['open']*(1-cfg['halfspread'])*(1-cfg['slip'])
    return dict(label=0,net_fraction=(exit_price*(1-cfg['fee'])-entry*(1+cfg['fee']))/entry,exit_at=b['time'],reason='TIME')


def scan_symbol(symbol,months):
    rows=load_symbol(symbol,months);events=[];cfg=settings();unlabeled=0
    for i in range(288,len(rows)):
        if rows[i]['time']-rows[i-1]['time']!=300:continue
        cs=propose(rows[i-288:i],rows[i]['time'])
        if not cs:continue
        c=cs[0];label=outcome(rows,i,c,cfg)
        if label is None:unlabeled+=1
        events.append(dict(c,symbol=symbol,at=rows[i]['time'],outcome=label))
    return dict(symbol=symbol,events=events,rows=len(rows),gaps=sum(b['time']-a['time']!=300 for a,b in zip(rows,rows[1:])),unlabeled=unlabeled)


def prepare(months,output):
    results=[]
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(scan_symbol,s,months):s for s in SYMBOLS}
        for f in as_completed(futures):
            r=f.result();results.append(r);print(json.dumps({k:v for k,v in r.items() if k!='events'}|{'proposals':len(r['events'])}),flush=True)
    payload=dict(kind='RESEARCH EVENT LABELS; DECISIONS USE CLOSED FEATURES ONLY',months=months,
        events=sorted([e for r in results for e in r['events']],key=lambda e:(e['at'],e['symbol'])),
        datasets=[{k:v for k,v in r.items() if k!='events'} for r in results],
        feature_source_sha256=hashed(Path(__file__).parents[1]/'cloud_paper/entry_model.py'),protocol_sha256=hashed(ROOT/'protocol.json'))
    (ROOT/output).write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode(),mtime=0))
    return payload


def read_events(filename):return json.loads(gzip.decompress((ROOT/filename).read_bytes()))


def simulate(events,rows,cfg,start,end,threshold,model=None):
    """Portfolio risk and fills are independent of future label metadata."""
    indexed={s:{b['time']:b for b in rs} for s,rs in rows.items()};by_time={}
    for e in events:
        if start<=e['at']<end:by_time.setdefault(e['at'],[]).append(e)
    cash=cfg['capital'];peak=cash;day_equity=cash;positions={};last_exit={};marks={};trades=[];fees=0.;drawdown=0.;daily_halt=False;halt=False;days={};blocks={};gaps_held=0
    def block(why):blocks[why]=blocks.get(why,0)+1
    def equity():return cash+sum(p['qty']*marks.get(s,p['entry'])*(1-cfg['halfspread'])*(1-cfg['slip'])*(1-cfg['fee']) for s,p in positions.items())
    def sell(symbol,bid,t,reason):
        nonlocal cash,fees
        p=positions.pop(symbol);price=bid*(1-cfg['slip']);value=p['qty']*price;exit_fee=value*cfg['fee'];cash+=value-exit_fee;fees+=exit_fee
        trades.append(dict(symbol=symbol,family=p['family'],entry_at=iso(p['at']),exit_at=iso(t),net_pnl=value-exit_fee-p['cost']-p['entry_fee'],
            entry=p['entry'],exit_price=price,quantity=p['qty'],entry_fee=p['entry_fee'],exit_fee=exit_fee,reason=reason,holding_hours=(t-p['at'])/3600))
        last_exit[symbol]=t
    for t in range(start,end,300):
        current={s:ix[t] for s,ix in indexed.items() if t in ix}
        for s,b in current.items():marks[s]=b['open']
        if t==start or t//86400!=(t-300)//86400:day_equity=equity();daily_halt=False
        if equity()<=day_equity*(1-cfg['daily_loss']):daily_halt=True
        if equity()<=peak*(1-cfg['drawdown']):halt=True
        for s,p in list(positions.items()):
            if s not in current:gaps_held+=1;continue
            if halt or daily_halt or t-p['at']>=cfg['hold']:
                sell(s,current[s]['open']*(1-cfg['halfspread']),t,'RISK' if halt or daily_halt else 'TIME')
        for e in sorted(by_time.get(t,[]),key=lambda x:(-x['score'],x['symbol'])):
            s=e['symbol']
            if halt or daily_halt:block('risk_halt');continue
            if any(s not in current for s in positions):block('missing_held_mark');continue
            if s not in current or s in positions or len(positions)>=cfg['max_positions']:continue
            if t-last_exit.get(s,-1e10)<cfg['cooldown']:block('cooldown');continue
            if abs(current[s]['open']/e['reference']-1)>.01:block('entry_gap');continue
            entry,stop,target=levels(e,current[s]['open'],cfg)
            loss=max(0,entry*(1+cfg['fee'])-stop*(1-cfg['slip'])*(1-cfg['fee']))/entry
            if threshold is not None:
                score=probability(model,e['features']);needed=max(threshold,loss/(loss+cfg['net_target'])+.05)
                if score<min(1,needed):block('model_filter');continue
            eq=equity();exposure=sum(p['qty']*marks.get(s,p['entry']) for s,p in positions.items())
            budget=min(cash,eq*cfg['max_position'],eq*cfg['max_exposure']-exposure)
            risk_per_unit=entry*(1+cfg['fee'])-stop*(1-cfg['slip'])*(1-cfg['fee'])
            qty=min(max(0,budget)/(entry*(1+cfg['fee'])),eq*cfg['risk']/risk_per_unit,e['lagged_volume_cap'])
            qty=math.floor(max(0,qty)*1e8)/1e8
            if qty*entry<5:block('size_or_volume');continue
            cost=qty*entry;entry_fee=cost*cfg['fee'];cash-=cost+entry_fee;fees+=entry_fee
            positions[s]=dict(qty=qty,entry=entry,cost=cost,entry_fee=entry_fee,at=t,stop=stop,target=target,family=e['family'])
        for s,p in list(positions.items()):
            if s not in current:continue
            b=current[s];bid_open=b['open']*(1-cfg['halfspread'])
            if b['low']*(1-cfg['halfspread'])<=p['stop']:sell(s,min(bid_open,p['stop']),t+299,'STOP')
            elif b['high']*(1-cfg['halfspread'])>=p['target']:sell(s,p['target'],t+299,'NET_TARGET')
            marks[s]=b['close']
        eq=equity();peak=max(peak,eq);drawdown=max(drawdown,1-eq/peak)
        if eq<=day_equity*(1-cfg['daily_loss']):daily_halt=True
        if eq<=peak*(1-cfg['drawdown']):halt=True
        days[int(t//86400)]=eq
    pnls=[x['net_pnl'] for x in trades];wins=sum(max(0,p) for p in pnls);losses=-sum(min(0,p) for p in pnls)
    return dict(start=iso(start),end=iso(end),final_equity=equity(),net_return=equity()/cfg['capital']-1,closed_trades=len(trades),open_positions=len(positions),
        net_realized=sum(pnls),mean_trade_pnl=statistics.mean(pnls) if pnls else None,wins=sum(p>0 for p in pnls),losses=sum(p<0 for p in pnls),
        modeled_fees=fees,maximum_drawdown=drawdown,drawdown_halted=halt,held_missing_bars=gaps_held,profit_factor=wins/losses if losses else None,
        blocks=blocks,daily_equity=[dict(day=iso(day*86400),equity=value) for day,value in sorted(days.items())],trades=trades)


def fit():
    if (ROOT/'validation_started.json').exists():raise ValueError('Reserved validation was opened; refitting this study is forbidden')
    import numpy as np
    import sklearn
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    payload=read_events('development_events.json.gz')
    if payload['feature_source_sha256']!=hashed(Path(__file__).parents[1]/'cloud_paper/entry_model.py') or payload['protocol_sha256']!=hashed(ROOT/'protocol.json'):raise ValueError('Prepared features or protocol changed; rebuild development events')
    events=payload['events'];cut=stamp('2026-08-16T00:00:00Z');end=stamp('2026-09-01T00:00:00Z')
    training=[e for e in events if e['at']<cut and e['outcome'] is not None and e['outcome']['exit_at']<cut]
    if len(training)<200 or len({e['outcome']['label'] for e in training})<2:raise ValueError('Insufficient training outcomes')
    X=np.array([e['features'] for e in training]);y=np.array([e['outcome']['label'] for e in training]);scaler=StandardScaler();scaled=scaler.fit_transform(X)
    clf=LogisticRegression(C=.5,max_iter=1000,random_state=20261012).fit(scaled,y)
    model=dict(features=list(FEATURES),mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),coefficient=clf.coef_[0].tolist(),intercept=float(clf.intercept_[0]),
        kind='RAW REGULARIZED CLASSIFIER SCORE; NOT A CLAIM OF CALIBRATED EDGE',training_end=iso(cut),training_rows=len(training),positives=int(y.sum()),
        feature_source_sha256=payload['feature_source_sha256'],protocol_sha256=hashed(ROOT/'protocol.json'),library_versions=dict(numpy=np.__version__,sklearn=sklearn.__version__))
    predicted=clf.predict_proba(scaled)[:,1];exported=np.array([probability(model,row.tolist()) for row in X]);assert np.max(abs(predicted-exported))<1e-12
    save(ROOT/'model.json',model)
    rows={s:load_symbol(s,['2026-05','2026-06','2026-07','2026-08']) for s in SYMBOLS};summaries=[]
    for threshold in (None,.55,.65,.75,.85):
        base=simulate(events,rows,settings(),cut,end,threshold,model);stress=simulate(events,rows,settings(True),cut,end,threshold,model)
        eligible=(base['net_return']>0 and stress['net_return']>0 and base['closed_trades']>=20 and stress['closed_trades']>=10 and
            (base['mean_trade_pnl'] or 0)>0 and (stress['mean_trade_pnl'] or 0)>0 and not base['drawdown_halted'] and not stress['drawdown_halted'] and not base['held_missing_bars'] and not stress['held_missing_bars'])
        summaries.append(dict(threshold=threshold,eligible_for_reserved_validation=eligible,base=base,stress=stress))
        print(json.dumps({'threshold':threshold,'base_return':base['net_return'],'base_trades':base['closed_trades'],'stress_return':stress['net_return'],'stress_trades':stress['closed_trades'],'eligible':eligible}),flush=True)
    eligible=[r for r in summaries if r['eligible_for_reserved_validation']]
    selected=max(eligible,key=lambda r:(r['stress']['net_return'],-r['base']['closed_trades'])) if eligible else None
    save(ROOT/'calibration_results.json',dict(kind='DEVELOPMENT SELECTION ONLY; NOT RESERVED VALIDATION',candidates=summaries,selected=selected['threshold'] if selected else None,eligible=bool(selected)))
    freeze=dict(status='FROZEN_FOR_RESERVED_VALIDATION' if selected else 'REJECTED_IN_DEVELOPMENT',threshold=selected['threshold'] if selected else None,
        model_sha256=hashed(ROOT/'model.json'),protocol_sha256=hashed(ROOT/'protocol.json'),feature_source_sha256=model['feature_source_sha256'],
        research_source_sha256=hashed(__file__),manifest_sha256=hashed(ROOT/'manifest.json'),frozen_at=datetime.now(timezone.utc).isoformat(),selection_only_used_development=True)
    save(ROOT/'frozen_selection.json',freeze)
    print(json.dumps({'selection':freeze['status'],'threshold':freeze['threshold'],'training_rows':len(training),'training_targets':int(y.sum())}),flush=True)


def validate():
    selection=json.loads((ROOT/'frozen_selection.json').read_text())
    if selection['status']!='FROZEN_FOR_RESERVED_VALIDATION':raise ValueError('No development candidate qualifies; reserved outcomes stay closed')
    if selection['manifest_sha256']!=hashed(ROOT/'manifest.json'):raise ValueError('Frozen archive identities changed before validation')
    if selection['model_sha256']!=hashed(ROOT/'model.json') or selection['protocol_sha256']!=hashed(ROOT/'protocol.json') or selection['research_source_sha256']!=hashed(__file__) or selection['feature_source_sha256']!=hashed(Path(__file__).parents[1]/'cloud_paper/entry_model.py'):raise ValueError('Frozen study changed before validation')
    save(ROOT/'validation_started.json',dict(at=datetime.now(timezone.utc).isoformat(),selection_sha256=hashed(ROOT/'frozen_selection.json')))
    payload=prepare(['2026-08','2026-09'],'validation_events.json.gz');events=payload['events'];rows={s:load_symbol(s,['2026-08','2026-09']) for s in SYMBOLS}
    model=json.loads((ROOT/'model.json').read_text());start=stamp('2026-09-01T00:00:00Z');end=stamp('2026-10-01T00:00:00Z')
    base=simulate(events,rows,settings(),start,end,selection['threshold'],model);stress=simulate(events,rows,settings(True),start,end,selection['threshold'],model)
    passes=base['net_return']>0 and stress['net_return']>0 and base['closed_trades']>=100 and (base['mean_trade_pnl'] or 0)>0 and (stress['mean_trade_pnl'] or 0)>0 and not base['drawdown_halted'] and not stress['drawdown_halted'] and not base['held_missing_bars'] and not stress['held_missing_bars']
    result=dict(kind='RESERVED HISTORICAL VALIDATION; NOT LIVE OR FORWARD P&L',selection=selection,base=base,stress=stress,passes_historical_gate=passes,
        live_feed_preflight_passed=False,eligible_for_live_money=False,
        limits=['Potential overlap with earlier project histories; not an independently untouched dataset.','Historical spreads, venue minimum orders and order book depth are not verified.','Fees use the published Binance.US Advanced Spot rate; actual account rates and access remain unverified.','Labels are purged at the training cut, candidate choice uses only development, and future label metadata never controls trades.','Cross-asset dependence and repeated development trials prevent a formal confidence claim.','No order, cash balance or fill in the active campaign is changed.'])
    save(ROOT/'validation_results.json',result)
    print(json.dumps({'passes_historical_gate':passes,'base_return':base['net_return'],'base_trades':base['closed_trades'],'stress_return':stress['net_return'],'stress_trades':stress['closed_trades']}),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','fit','validate']);args=parser.parse_args()
    if args.stage=='prepare':
        if (ROOT/'validation_started.json').exists():raise ValueError('Reserved validation already opened')
        prepare(['2026-05','2026-06','2026-07','2026-08'],'development_events.json.gz')
    elif args.stage=='fit':fit()
    else:validate()


if __name__=='__main__':main()
