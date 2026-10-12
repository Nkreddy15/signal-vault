"""Fixed long-only 5m hypotheses. Price headroom is not expected profit."""
import math
import statistics
from .store import digest
from .strategies import ema
from .strategies_v2 import indicators

FAMILIES=('scalp_pullback','scalp_rebound','scalp_range')


def required_reference_ratio(config):
    fee=config['crypto_fee_fraction']
    friction=config['slippage_fraction']+config['max_spread_fraction']/2
    net=config['crypto_net_take_profit_fraction']
    return (1+friction)*(1+fee+net)/((1-friction)*(1-fee))


def signals(bars,market,symbol,now,config):
    if market!='crypto':return [],'Scalp hypotheses cover crypto internal simulation only'
    if len(bars)<72:return [],'Need 72 complete native 5m bars'
    bars=bars[-72:]
    for b in bars:
        if not all(isinstance(b.get(k),(int,float)) and math.isfinite(b[k]) for k in ('time','open','high','low','close','volume')):
            return [],'Invalid native 5m candle'
        if b['time']%300 or b['time']+300>now or b['volume']<0 or not 0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:
            return [],'Invalid or unclosed native 5m candle'
    if any(b['time']-a['time']!=300 for a,b in zip(bars,bars[1:])):return [],'Gap or duplicate in native 5m history'
    if not 0<=now-bars[-1]['time']-300<300:return [],'Stale native 5m history'
    closes=[b['close'] for b in bars];last,previous=closes[-1],closes[-2]
    x=indicators(bars);e9=ema(closes,9);prior_e9=ema(closes[:-1],9)
    stop=max(.005*last,1.5*x['atr'])
    if stop/last>.05 or x['atr']<=0:return [],'5m volatility exceeds stop bound'
    ratio=required_reference_ratio(config);required=last*(ratio+.001)
    average_volume=statistics.mean(b['volume'] for b in bars[-21:-1])
    if average_volume<=0 or bars[-1]['volume']<.8*average_volume:return [],'Insufficient closed-bar volume confirmation'
    high=max(b['high'] for b in bars[:-1]);mean=statistics.mean(closes[-25:-1]);sd=statistics.pstdev(closes[-25:-1])
    found=[];patterns=[]
    def add(family,score,reason,target):
        if family not in config['strategies']:return
        patterns.append(family)
        if target<required:return
        fee=config['crypto_fee_fraction'];friction=config['slippage_fraction']+config['max_spread_fraction']/2
        breakeven=(1+friction)*(1+fee)/((1-friction)*(1-fee))-1
        found.append(dict(market=market,symbol=symbol,strategy=family,score=score,reason=reason,
            signal_at=bars[-1]['time']+300,signal=digest([config['version'],market,symbol,family,bars[-1]['time']]),
            reference=last,stop_distance=stop,stop=last-stop,target=target,target_anchored=True,
            cost_break_even_fraction=breakeven,minimum_net_profit_fraction=config['crypto_net_take_profit_fraction'],
            indicators=dict(x,ema9=e9,prior_ema9=prior_e9,required_reference_move=ratio-1,observed_headroom=target/last-1),
            trailing_activation_multiple=10,trailing_distance_multiple=1))
    if e9>x['e20'] and last>x['e20'] and x['e20']>ema(closes[:-3],20) and previous<=prior_e9 and last>e9 and last>previous and 40<=x['rsi']<=75 and x['rsi']>x['prior_rsi']:
        add('scalp_pullback',3,'5m EMA9 reclaim in a rising short trend; RSI and volume confirm; prior high clears costs',high)
    if x['prior_rsi']<35 and x['rsi']>=x['prior_rsi']+2 and last>previous>closes[-3]:
        add('scalp_rebound',2,'5m oversold recovery with two rising closes, improving RSI and volume; prior high clears costs',high)
    if x['adx']<=25 and sd>0 and previous<mean-1.5*sd and last>previous and x['rsi']>x['prior_rsi']:
        add('scalp_range',1,'5m lower-band recovery with low ADX; previous mean clears all modeled costs',mean)
    explanation='Scalp pattern lacks headroom after fees' if patterns and not found else 'No confirmed 5m pullback, rebound or range recovery'
    return sorted(found,key=lambda c:(-c['score'],c['strategy'])),('Qualified: '+', '.join(c['strategy'] for c in found)) if found else explanation
