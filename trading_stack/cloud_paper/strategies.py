"""Frozen, explicit experimental rules; chronological closed bars only."""
import math
import statistics
from .store import digest


def ema(values,period):
    result=values[0]; alpha=2/(period+1)
    for value in values[1:]: result += alpha*(value-result)
    return result


def signals(bars,market,symbol,now,config):
    if config.get("strategy_pack")=="swing-v3":
        from .strategies_v3 import signals as alternative
        return alternative(bars,market,symbol,now,config)
    if config.get("strategy_pack")=="regime-v2":
        from .strategies_v2 import signals as alternative
        return alternative(bars,market,symbol,now,config)
    if len(bars)<60: return [],"Insufficient closed history (need 60 hourly bars)"
    if any(b["time"]+3600>now for b in bars): return [],"Unclosed candle refused"
    if any(bars[i]["time"]>=bars[i+1]["time"] for i in range(len(bars)-1)): return [],"Nonchronological history"
    if market=="crypto" and any(bars[i+1]["time"]-bars[i]["time"]!=3600 for i in range(len(bars)-60,len(bars)-1)):
        return [],"Gap in indicator history"
    # Stock session gaps are expected; data freshness is separately gated by live quotes and broker clock.
    if market=="crypto" and now-(bars[-1]["time"]+3600)>3600: return [],"Stale indicator history"
    c=[float(b["close"]) for b in bars]; last=c[-1]
    if any(not math.isfinite(x) or x<=0 for x in c): return [],"Invalid historical prices"
    e20,e50=ema(c,20),ema(c,50)
    prior=bars[-21:-1]; avg=statistics.mean(c[-21:-1]); sd=statistics.pstdev(c[-21:-1])
    atr=statistics.mean(max(bars[i]["high"]-bars[i]["low"],abs(bars[i]["high"]-c[i-1]),abs(bars[i]["low"]-c[i-1])) for i in range(len(bars)-14,len(bars)))
    stop=max(.01*last,2*atr)
    if stop/last>.1: return [],"Volatility exceeds 10% stop-distance bound"
    costs=2*(config["crypto_fee_fraction"] if market=="crypto" else config["stock_fee_fraction"])+2*config["slippage_fraction"]+config["max_spread_fraction"]
    target=max(2*stop,last*(costs+.005))
    if target/last>.2: return [],"Cost-aware target exceeds movement bound"
    regime="UPTREND" if e20>e50*1.002 and c[-1]>e50 else "RANGE" if abs(e20/e50-1)<.006 else "BEARISH"
    found=[]
    def add(family,score,reason,profit_distance=target):
        if family not in config["strategies"]: return
        found.append(dict(market=market,symbol=symbol,strategy=family,score=score,reason=reason,signal_at=bars[-1]["time"]+3600,
             stop_distance=stop,stop=last-stop,target=last+profit_distance,reference=last,
             signal=digest([config["version"],market,symbol,family,bars[-1]["time"]])))
    if regime=="UPTREND" and last>max(b["high"] for b in prior) and bars[-1]["volume"]>=1.2*statistics.mean(b["volume"] for b in prior):
        add("breakout",3,"Closed hourly high exceeded prior 20-hour high with 1.2x volume")
    if regime=="UPTREND" and c[-1]>e20 and c[-1]>c[-4] and last/e20<1.03:
        add("inverse_trend" if symbol in ("SH","PSQ") else "trend",2,
            "EMA20 above EMA50; positive 3-bar momentum; within 3% of EMA20"+("; long inverse ETF, daily-reset product" if symbol in ("SH","PSQ") else ""))
    if regime=="RANGE" and sd>0 and c[-2]<avg-1.5*sd and last>c[-2] and (avg-last)/last>costs+.005:
        add("range_reversion",1,"Range regime, prior close below 1.5 sigma, positive turn and cost-cleared return to mean",avg-last)
    return sorted(found,key=lambda s:(-s["score"],s["strategy"])),("No qualifying signal · "+regime)


def probability_signal(market,quote,estimate,now,config):
    """Require timestamped external probability evidence, not market price as 'edge'."""
    if market.get("market_type")!="binary" or market.get("status") not in ("active","open"):
        return None,"Unsupported contract type or market closed"
    if any(market.get(k) is not None for k in ("settlement_floor_dollars","settlement_cap_dollars")):
        return None,"Settlement-bound contracts unsupported"
    schedule=market.get("verified_fee_schedule",{})
    if schedule.get("type")!="quadratic" or schedule.get("multiplier")!=1 or not 0<=now-schedule.get("checked_at",0)<=90:
        return None,"Standard contract fee schedule not freshly verified"
    if market.get("settlement_bounds_type","default")!="default" or market.get("mve_collection_ticker"):
        return None,"Nonstandard settlement unsupported"
    if not estimate: return None,"Missing independent probability estimate and calibration evidence"
    required=("probability","lower_bound","upper_bound","as_of","expires_at","source","model_version","calibration_report_sha256")
    if any(k not in estimate for k in required): return None,"Incomplete probability provenance"
    p,lo,hi=[float(estimate[k]) for k in ("probability","lower_bound","upper_bound")]
    if not 0<=lo<=p<=hi<=1 or not now-3600<=estimate["as_of"]<=now or now>=estimate["expires_at"]:
        return None,"Stale or invalid probability evidence"
    if len(estimate["calibration_report_sha256"])!=64 or not estimate["source"] or not estimate["model_version"]:
        return None,"Probability provenance missing"
    ask=quote["ask"]; fee=.07*ask*(1-ask)
    if lo-ask-fee<config["kalshi_minimum_edge"]: return None,"Conservative probability edge does not clear fees and 5-cent buffer"
    if quote.get("ask_size",0)<1: return None,"Insufficient contract liquidity"
    return dict(market="kalshi",symbol=market["ticker"],strategy="probability_edge",score=lo-ask-fee,
        reason="Independent probability lower bound clears executable ask, fees and buffer; experimental",
        signal_at=estimate["as_of"],signal=digest([market["ticker"],estimate]),reference=ask,
        stop_distance=ask,stop=None,target=None,contract=dict(market=market,estimate=estimate)),None
