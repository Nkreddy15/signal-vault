"""Closed-bar features and frozen logistic inference; no network or order authority."""
import math
import statistics

FEATURES=('return1','return3','return12','return36','ema9_gap','ema20_gap','ema20_50_gap','ema20_slope',
    'rsi14','rsi_change','adx14','atr_fraction','volume_ratio','band_z','vwap_gap','higher_trend_gap',
    'higher_slope','candle_body_atr','close_location','taker_buy_ratio','utc_hour_sin','utc_hour_cos',
    'is_weekend','family_trend','family_retest','family_range')
FAMILIES=('trend_continuation','breakout_retest','vwap_recovery')


def finite_ema(values,period,length=144):
    values=values[-length:]
    if len(values)<length:raise ValueError('Insufficient EMA history')
    a=2/(period+1);result=values[0]
    for v in values[1:]:result+=a*(v-result)
    return result


def check_history(bars,now):
    if len(bars)<288:return False
    bars=bars[-288:]
    for b in bars:
        if not all(isinstance(b.get(k),(int,float)) and math.isfinite(b[k]) for k in ('time','open','high','low','close','volume','quote_volume','taker_buy_base_volume')):return False
        if b['time']%300 or b['time']+300>now or b['volume']<0 or b['quote_volume']<0 or not 0<=b['taker_buy_base_volume']<=b['volume']+1e-8:return False
        if not 0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:return False
    return all(b['time']-a['time']==300 for a,b in zip(bars,bars[1:])) and 0<=now-bars[-1]['time']-300<300


def _rsi(changes):
    gain=sum(max(v,0) for v in changes[-14:]);loss=sum(max(-v,0) for v in changes[-14:])
    return 100*gain/(gain+loss) if gain+loss else 50


def _closed_higher(bars):
    groups={}
    for b in bars:groups.setdefault(int(b['time']//900)*900,[]).append(b)
    return [rows[-1]['close'] for t,rows in sorted(groups.items()) if len(rows)==3 and [b['time'] for b in rows]==[t,t+300,t+600]]


def extract(bars,now):
    """The training scanner calls this same function for every proposed entry."""
    if not check_history(bars,now):return None
    bars=bars[-288:];closes=[b['close'] for b in bars];last=closes[-1]
    e9,e20,e50=(finite_ema(closes,p) for p in (9,20,50))
    prior_e9=finite_ema(closes[:-1],9);prior_e20=finite_ema(closes[:-3],20)
    tr=[];plus=[];minus=[];changes=[]
    for a,b in zip(bars,bars[1:]):
        tr.append(max(b['high']-b['low'],abs(b['high']-a['close']),abs(b['low']-a['close'])))
        up=b['high']-a['high'];down=a['low']-b['low']
        plus.append(up if up>down and up>0 else 0);minus.append(down if down>up and down>0 else 0)
        changes.append(b['close']-a['close'])
    atr=statistics.mean(tr[-14:]);dx=[]
    for i in range(len(plus)-14,len(plus)):
        p=sum(plus[i-13:i+1]);m=sum(minus[i-13:i+1]);dx.append(100*abs(p-m)/(p+m) if p+m else 0)
    adx=statistics.mean(dx);rsi=_rsi(changes);prior_rsi=_rsi(changes[:-1])
    mean=statistics.mean(closes[-25:-1]);sd=statistics.pstdev(closes[-25:-1])
    volume=statistics.mean(b['volume'] for b in bars[-21:-1]);vol=sum(b['volume'] for b in bars[-72:])
    if atr<=0 or volume<=0 or vol<=0:return None
    vwap=sum(b['quote_volume'] for b in bars[-72:])/vol
    higher=_closed_higher(bars)
    if len(higher)<67:return None
    h20=finite_ema(higher,20,64);h50=finite_ema(higher,50,64);hp20=finite_ema(higher[:-3],20,64)
    v20=sum(b['volume'] for b in bars[-20:]);hour=(now%86400)/3600
    features=[last/closes[-1-n]-1 for n in (1,3,12,36)]
    features += [last/e9-1,last/e20-1,e20/e50-1,e20/prior_e20-1,rsi/100,(rsi-prior_rsi)/100,
        adx/100,atr/last,min(10,bars[-1]['volume']/volume),(last-mean)/sd if sd else 0,last/vwap-1,
        h20/h50-1,h20/hp20-1,(bars[-1]['close']-bars[-1]['open'])/atr,
        (last-bars[-1]['low'])/(bars[-1]['high']-bars[-1]['low']) if bars[-1]['high']>bars[-1]['low'] else .5,
        sum(b['taker_buy_base_volume'] for b in bars[-20:])/v20 if v20 else .5,
        math.sin(2*math.pi*hour/24),math.cos(2*math.pi*hour/24),float(int(now//86400+3)%7>=5),0.,0.,0.]
    return dict(features=features,reference=last,atr=atr,rsi=rsi,prior_rsi=prior_rsi,adx=adx,
        ema9=e9,prior_ema9=prior_e9,ema20=e20,ema50=e50,ema20_slope=e20/prior_e20-1,
        higher_trend=h20/h50-1,higher_slope=h20/hp20-1,volume_ratio=bars[-1]['volume']/volume,
        mean=mean,sd=sd,vwap=vwap,daily_quote_volume=sum(b['quote_volume'] for b in bars))


def propose(bars,now):
    x=extract(bars,now)
    if x is None or x['daily_quote_volume']<500000 or x['volume_ratio']<.8:return []
    last=x['reference'];previous=bars[-2]['close'];stop=max(last*.002,1.25*x['atr'])
    if stop/last>.03:return []
    trend=x['ema20']>x['ema50'] and x['ema20_slope']>0 and x['higher_trend']>0 and x['higher_slope']>0
    families=[]
    if trend and last>x['ema9'] and last>bars[-4]['close'] and 40<=x['rsi']<=70 and (last-x['ema9'])/x['atr']<=1.5:
        families.append('trend_continuation')
    level=max(b['high'] for b in bars[-14:-2]);prior_volume=statistics.mean(b['volume'] for b in bars[-22:-2])
    if trend and previous>level and bars[-2]['volume']>=1.5*prior_volume and bars[-1]['low']<=level+.25*x['atr'] and last>level and last>x['ema20']:
        families.append('breakout_retest')
    if x['adx']<=20 and abs(x['higher_slope'])<.003 and x['sd']>0 and previous<x['mean']-1.5*x['sd'] and last>previous and x['rsi']>x['prior_rsi'] and 25<=x['rsi']<=50 and x['vwap']/last-1>=.006:
        families.append('vwap_recovery')
    proposals=[]
    for family in families:
        f=x['features'][:];f[-3:]=[float(family==name) for name in FAMILIES]
        proposals.append(dict(family=family,features=f,reference=last,stop_distance=stop,signal_at=now,
            score=3-FAMILIES.index(family),daily_quote_volume=x['daily_quote_volume'],lagged_volume_cap=.01*bars[-1]['volume']))
    return proposals


def probability(model,features):
    """Frozen raw classifier score. No claim of calibrated probability is implied."""
    if model.get('features')!=list(FEATURES) or len(features)!=len(FEATURES):raise ValueError('Feature schema mismatch')
    if not all(math.isfinite(v) for v in features):raise ValueError('Nonfinite model feature')
    if any(len(model[k])!=len(FEATURES) for k in ('mean','scale','coefficient')) or any(s<=0 for s in model['scale']):raise ValueError('Invalid model scale or dimensions')
    if not all(math.isfinite(v) for k in ('mean','scale','coefficient') for v in model[k]) or not math.isfinite(model['intercept']):raise ValueError('Nonfinite model parameter')
    z=model['intercept']+sum(w*(v-m)/s for v,m,s,w in zip(features,model['mean'],model['scale'],model['coefficient']))
    if not math.isfinite(z):raise ValueError('Nonfinite inference result')
    return 1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))
