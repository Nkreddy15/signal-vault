"""Predeclared experimental alternatives; no optimizer or automatic promotion.

ADX selects regime, RSI times pullbacks/reversals, ATR sets risk distances.
Indicators do separate jobs; their agreement is not a calibrated probability.
"""
import math
import statistics
from .store import digest
from .strategies import ema


def indicators(bars, period=14):
    closes=[b['close'] for b in bars]
    tr=[];plus=[];minus=[];gains=[];losses=[]
    for previous,current in zip(bars,bars[1:]):
        up=current['high']-previous['high'];down=previous['low']-current['low']
        tr.append(max(current['high']-current['low'],abs(current['high']-previous['close']),abs(current['low']-previous['close'])))
        plus.append(up if up>down and up>0 else 0)
        minus.append(down if down>up and down>0 else 0)
        change=current['close']-previous['close'];gains.append(max(change,0));losses.append(max(-change,0))
    def wilder(values):
        result=[statistics.mean(values[:period])]
        for v in values[period:]:result.append((result[-1]*(period-1)+v)/period)
        return result
    atr=wilder(tr);pos=wilder(plus);neg=wilder(minus)
    dx=[100*abs(p-m)/(p+m) if p+m else 0 for p,m in zip(pos,neg)]
    gain,loss=wilder(gains),wilder(losses)
    rsi=[100-100/(1+g/l) if l else (100 if g else 50) for g,l in zip(gain,loss)]
    return dict(atr=atr[-1],adx=wilder(dx)[-1],rsi=rsi[-1],prior_rsi=rsi[-2],
                e20=ema(closes,20),e50=ema(closes,50),prior_e20=ema(closes[:-1],20))


def signals(bars,market,symbol,now,config):
    if market not in ('crypto','stocks'):return [],'Unsupported strategy market'
    if len(bars)<100:return [],'Insufficient closed history (need 100 hourly bars)'
    for b in bars:
        if not all(isinstance(b.get(k),(int,float)) and math.isfinite(b[k]) for k in ('time','open','high','low','close','volume')):
            return [],'Invalid historical candle'
        if min(b['open'],b['high'],b['low'],b['close'])<=0 or b['volume']<0 or not b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:
            return [],'Invalid historical candle'
        if b['time']+3600>now:return [],'Unclosed candle refused'
    if any(a['time']>=b['time'] for a,b in zip(bars,bars[1:])):return [],'Nonchronological history'
    if market=='crypto':
        if any(b['time']-a['time']!=3600 for a,b in zip(bars[-100:],bars[-99:])):return [],'Gap in indicator history'
        if now-bars[-1]['time']-3600>3600:return [],'Stale indicator history'
    x=indicators(bars);last=bars[-1]['close'];prev=bars[-2]['close']
    stop=max(last*.01,2*x['atr'])
    if stop/last>.1:return [],'Volatility exceeds 10% stop-distance bound'
    fee=config['crypto_fee_fraction'] if market=='crypto' else config['stock_fee_fraction']
    friction=config['slippage_fraction']+config['max_spread_fraction']/2
    # Exact gross price move needed to break even after modeled entry and exit costs.
    breakeven=(1+friction)*(1+fee)/((1-friction)*(1-fee))-1
    required=last*(breakeven+.01)
    target=3*stop
    if target/last>.2:return [],'Cost-aware target exceeds movement bound'
    trend=x['adx']>=25 and x['e20']>x['e50'] and last>x['e50']
    range_regime=x['adx']<=20 and abs(x['e20']/x['e50']-1)<.01
    found=[]
    def add(family,rank,reason,distance=target):
        if family not in config['strategies']:return
        if distance<required:return
        found.append(dict(market=market,symbol=symbol,strategy=family,score=rank,reason=reason,
            signal_at=bars[-1]['time']+3600,signal=digest([config['version'],market,symbol,family,bars[-1]['time']]),
            stop_distance=stop,stop=last-stop,target=last+distance,reference=last,
            indicators=x.copy(),cost_break_even_fraction=breakeven,target_anchored=(family=='range_reversion')))
    prior=bars[-25:-1]
    if trend and last>max(b['high'] for b in prior) and bars[-1]['volume']>=1.2*statistics.mean(b['volume'] for b in prior) and 50<=x['rsi']<=80:
        add('breakout',3,'24-hour high breakout; ADX trend; elevated volume; RSI below extreme')
    if trend and prev<=x['prior_e20'] and last>x['e20'] and x['rsi']>x['prior_rsi'] and 40<=x['rsi']<=65:
        add('inverse_trend' if symbol in ('SH','PSQ') else 'pullback',2,
            'Closed-bar EMA20 reclaim in ADX uptrend; RSI recovering'+('; long daily-reset inverse ETF' if symbol in ('SH','PSQ') else ''))
    mean=statistics.mean([b['close'] for b in prior]);sd=statistics.pstdev([b['close'] for b in prior])
    if range_regime and sd and prev<mean-1.5*sd and last>prev and x['prior_rsi']<35 and x['rsi']>x['prior_rsi'] and mean-last>=required:
        add('range_reversion',1,'Low ADX range; lower-band reversal; RSI recovering; mean clears costs',mean-last)
    regime='UPTREND' if trend else 'RANGE' if range_regime else 'BEARISH_OR_TRANSITION'
    reason=('Qualified: '+', '.join(c['strategy'] for c in found)) if found else ('No qualifying signal · '+regime)
    return sorted(found,key=lambda c:(-c['score'],c['strategy'])),reason
