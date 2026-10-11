"""Frozen native 15m hypotheses; interval revision, no demonstrated edge. A target is an exit rule, never estimated expected value."""
from datetime import datetime, timezone
from decimal import Decimal
import math
import statistics

from .store import digest
from .strategies import ema
from .vendor.omniquant.regime import SimpleRegimeDetector
from .vendor.omniquant.models import MarketBar

FAMILIES = ("slow_breakout", "slow_pullback", "range_reclaim")


def signals(bars, market, symbol, now, config):
    if market != "crypto":
        from .strategies_v2 import signals as stock_signals
        return stock_signals(bars, market, symbol, now, config)
    step = 900
    if len(bars) < 120:
        return [], "Need 120 complete 15m bars"
    bars = bars[-120:]
    for b in bars:
        if not all(isinstance(b.get(k), (int, float)) and math.isfinite(b[k]) for k in ("time", "open", "high", "low", "close", "volume")):
            return [], "Invalid 15m candle"
        if b["time"] % step or b["time"] + step > now or b["volume"] < 0 or not 0 < b["low"] <= min(b["open"], b["close"]) <= max(b["open"], b["close"]) <= b["high"]:
            return [], "Invalid or unclosed 15m candle"
    if any(b["time"] - a["time"] != step for a, b in zip(bars, bars[1:])):
        return [], "Gap or duplicate in 15m history"
    if not 0 <= now - bars[-1]["time"] - step < step:
        return [], "Stale 15m history"
    closes = [b["close"] for b in bars]
    last, previous = closes[-1], closes[-2]
    e20, e50, e100 = [ema(closes, n) for n in (20, 50, 100)]
    atr = statistics.mean(max(b["high"] - b["low"], abs(b["high"] - a["close"]), abs(b["low"] - a["close"])) for a, b in zip(bars[-21:-1], bars[-20:]))
    omni_bars = [MarketBar(symbol, datetime.fromtimestamp(b["time"], timezone.utc), *(Decimal(str(b[k])) for k in ("open", "high", "low", "close", "volume"))) for b in bars[-12:]]
    regime = SimpleRegimeDetector().detect(omni_bars).value
    if atr <= 0 or regime == "volatile":
        return [], "OmniQuant volatile regime or zero ATR"
    stop = max(last * .03, 3 * atr)
    if stop / last > .15:
        return [], "15m volatility exceeds risk distance bound"
    fee = config["crypto_fee_fraction"]
    friction = config["slippage_fraction"] + config["max_spread_fraction"] / 2
    breakeven = (1 + friction) * (1 + fee) / ((1 - friction) * (1 - fee)) - 1
    required = last * (breakeven + .015)
    trend = e20 > e50 > e100 and last > e100 and e100 > ema(closes[:-6], 100)
    prior = bars[-56:-1]
    found = []

    def add(family, score, reason, target, anchored=False):
        if family not in config["strategies"] or target - last < required:
            return
        found.append(dict(market=market, symbol=symbol, strategy=family, score=score, reason=reason,
            signal_at=bars[-1]["time"] + step, signal=digest([config["version"], market, symbol, family, bars[-1]["time"]]),
            stop_distance=stop, stop=last-stop, target=target, reference=last,
            cost_break_even_fraction=breakeven, target_anchored=anchored,
            indicators=dict(ema20=e20, ema50=e50, ema100=e100, atr20=atr, omniquant_regime=regime),
            trailing_activation_multiple=2, trailing_distance_multiple=1.5))

    if trend and last > max(b["high"] for b in prior) and bars[-1]["volume"] >= statistics.mean(b["volume"] for b in prior[-20:]):
        add("slow_breakout", 3, "15m 55-bar breakout above rising EMA100; volume confirmation", last+4*stop)
    if trend and previous <= ema(closes[:-1], 20) and last > e20 and last > previous:
        add("slow_pullback", 2, "15m EMA20 reclaim inside rising EMA20/50/100 trend", last+4*stop)
    mean = statistics.mean(closes[-31:-1]); sd = statistics.pstdev(closes[-31:-1])
    if regime == "ranging" and abs(e20/e50-1) < .015 and last >= .95*e100 and sd and previous < mean-2*sd and last > previous:
        add("range_reclaim", 1, "15m lower-band recovery in OmniQuant ranging regime; prior mean clears modeled costs", mean, True)
    return sorted(found, key=lambda c: (-c["score"], c["strategy"])), "OmniQuant " + regime + ("; uptrend" if trend else "; no uptrend")
