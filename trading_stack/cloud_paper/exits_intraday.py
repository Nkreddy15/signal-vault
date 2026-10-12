"""Bounded long-only paper exits. Gross gains are never counted as net profit."""
import math
from .strategies import ema


def net_target_bid(position, config):
    """Bid needed to net the declared fraction after fees and exit slippage."""
    remaining=position['quantity']
    if remaining<=0: return None
    cost=position['cost']
    needed=cost*(1+config['crypto_net_take_profit_fraction'])+position['entry_fee']+position['exit_fee']-position['proceeds']
    return needed/(remaining*(1-config['slippage_fraction'])*(1-config['crypto_fee_fraction']))


def trend_invalidated(strategy, opened_at, bars, now, confirmation=2):
    if strategy not in ('slow_breakout','slow_pullback') or len(bars)<60+confirmation:
        return False
    bars=bars[-120:]
    for b in bars:
        if not all(isinstance(b.get(k),(int,float)) and math.isfinite(b[k]) for k in ('time','open','high','low','close','volume')):
            return False
        if b['time']%900 or b['time']+900>now or b['volume']<0 or not 0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:
            return False
    if any(b['time']-a['time']!=900 for a,b in zip(bars,bars[1:])) or not 0<=now-bars[-1]['time']-900<900:
        return False
    closes=[b['close'] for b in bars]
    for i in range(confirmation):
        history=closes[:len(closes)-i]
        if bars[-1-i]['time']+900<=opened_at or not (history[-1]<ema(history,50) and ema(history,20)<ema(history,50)):
            return False
    return True


def reason(position, bars, bid, config, now):
    if now-position['opened_at']>=config['crypto_max_hold_hours']*3600:
        return 'INTRADAY_TIME_EXIT'
    target=net_target_bid(position,config)
    if target is not None and bid>=target:
        return 'INTRADAY_NET_TARGET'
    if trend_invalidated(position['strategy'],position['opened_at'],bars,now,config['crypto_exit_confirmation_bars']):
        return 'INTRADAY_TREND_INVALIDATED'
    return None
