"""Causal multi-strategy research with shared cash, compounding and explicit fills.

No network or order submission. Inputs are closed 15m Kraken research candles.
Development results do not activate any forward engine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

BAR = 900_000
DAY = 96 * BAR
PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "ADA/USD")
FAMILIES = ("breakout", "pullback", "range_reversal", "rotation", "blend")
VERSION = "MULTI-STRATEGY-LAB-1"
# Kraken spot tiers checked October 3, 2026. Only trading volume is modeled;
# account assets/futures volumes are not available in this offline experiment.
TIERS = ((0, .008), (2500, .006), (10000, .0038), (25000, .0035),
         (50000, .003), (100000, .0025), (250000, .0022), (500000, .002),
         (1000000, .0018), (2500000, .0015), (5000000, .0012),
         (10000000, .001), (50000000, .0009), (100000000, .0008),
         (250000000, .0007), (400000000, .0006), (500000000, .0005))
FEE_PROFILES = {
    "kraken_spot": TIERS,
    # A fee-rate sensitivity on Kraken candles, not Alpaca venue/fill evidence.
    "alpaca_rate_sensitivity": ((0, .0025), (100000, .0022), (500000, .002),
        (1000000, .0018), (10000000, .0015), (25000000, .0013),
        (50000000, .0012), (100000000, .001)),
}
SOURCES = {
    "spot_fees": "https://support.kraken.com/articles/cross-platform-fee-tier-changes",
    "time_series_momentum": "https://www.nber.org/papers/w24877",
    "relative_strength": "https://www.nber.org/papers/w25882",
    "reversal_costs": "https://arxiv.org/abs/2608.21888",
    "overfitting": "https://scholarworks.wmich.edu/math_pubs/42/",
    "execution": "https://www.freqtrade.io/en/stable/backtesting/",
}


@dataclass(frozen=True)
class Config:
    family: str = "blend"
    risk: str = "balanced"
    mode: str = "long_only"
    spread_bps: float = 5
    execution: str = "trigger"
    slippage: float = .001
    short_carry_per_day: float = .0003  # sensitivity assumption, not a quote
    starting_balance: float = 100
    daily_operating_cost_usd: float = 0
    fee_profile: str = "kraken_spot"

    @property
    def risk_fraction(self):
        return .01 if self.risk == "balanced" else .03

    @property
    def drawdown_limit(self):
        return .25 if self.risk == "balanced" else .50

    @property
    def daily_loss_limit(self):
        return .10 if self.risk == "balanced" else .20


@dataclass(frozen=True)
class Signal:
    family: str
    side: int
    score: float
    stop: float
    target: float | None
    hold_bars: int
    signal_ms: int
    reference_price: float | None = None
    atr: float = 0
    trailing: bool = True
    trailing_distance: float | None = None


class Fees:
    def __init__(self, profile="kraken_spot"):
        self.tiers = FEE_PROFILES[profile]
        self.fills = deque()
        self.volume = 0.0

    def rate(self, now):
        while self.fills and self.fills[0][0] <= now - 30 * DAY:
            self.volume -= self.fills.popleft()[1]
        self.volume = max(0.0, self.volume)
        return next(rate for threshold, rate in reversed(self.tiers) if self.volume >= threshold)

    def record(self, now, notional):
        self.fills.append((now, notional))
        self.volume += notional


def normalized(frame):
    f = frame.copy()
    if "ts" not in f:
        dates = pd.to_datetime(f["date"], utc=True).astype("datetime64[ns, UTC]")
        f["ts"] = dates.astype("int64") // 1_000_000
    f = f[["ts", "open", "high", "low", "close", "volume"]].sort_values("ts").reset_index(drop=True)
    if f.empty or f.ts.duplicated().any():
        raise ValueError("Empty or duplicate candles; refusing to silently repair inputs")
    if not np.isfinite(f.to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite candles")
    if not ((f.ts % BAR == 0) & (f.open > 0) & (f.low > 0) & (f.volume >= 0) &
            (f.high >= f[["open", "close", "low"]].max(axis=1)) &
            (f.low <= f[["open", "close"]].min(axis=1))).all():
        raise ValueError("Invalid OHLC or 15m timestamps")
    return f


def features(frame):
    f = normalized(frame)
    blocks = (f.ts.diff().fillna(BAR) != BAR).cumsum()
    pieces = []
    for _, part in f.groupby(blocks):
        p = part.copy()
        c = p.close
        for span in (20, 60, 200):
            p[f"ema{span}"] = c.ewm(span=span, adjust=False).mean()
        tr = pd.concat([p.high-p.low, (p.high-c.shift()).abs(), (p.low-c.shift()).abs()], axis=1).max(axis=1)
        p["atr"] = tr.ewm(alpha=1/14, adjust=False).mean() / c
        up, down = p.high.diff(), -p.low.diff()
        plus = up.where((up > down) & (up > 0), 0).ewm(alpha=1/14, adjust=False).mean()
        minus = down.where((down > up) & (down > 0), 0).ewm(alpha=1/14, adjust=False).mean()
        p["adx"] = (100*(plus-minus).abs()/(plus+minus).replace(0, np.nan)).ewm(alpha=1/14, adjust=False).mean()
        delta = c.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        p["rsi"] = (100-100/(1+gain/loss)).where(loss != 0, 100).where(gain+loss != 0, 50)
        p["ret16"] = c.pct_change(16, fill_method=None)
        p["ret96"] = c.pct_change(96, fill_method=None)
        p["vol_ratio"] = p.volume / p.volume.shift().rolling(20).median().replace(0, np.nan)
        p["hi96"] = p.high.shift().rolling(96).max()
        p["lo96"] = p.low.shift().rolling(96).min()
        p["mean96"] = c.rolling(96).mean()
        p["z96"] = (c-p.mean96)/c.rolling(96).std(ddof=0).replace(0, np.nan)
        p["prev_close"] = c.shift()
        p["prev_fast"] = p.ema20.shift()
        p["prev_z"] = p.z96.shift()
        p["age"] = range(1, len(p)+1)
        pieces.append(p)
    return pd.concat(pieces, ignore_index=True)


def signals(p):
    """All masks are backward-looking; entries are compiled for the next bar."""
    valid = (p.age >= 256) & p.atr.between(.0007, .04) & (p.volume > 0)
    bull = (p.ema60 > p.ema200) & (p.close > p.ema200)
    bear = (p.ema60 < p.ema200) & (p.close < p.ema200)
    flags = {
        ("breakout", 1): valid & bull & (p.close > p.hi96) & (p.vol_ratio >= 1.2),
        ("breakout", -1): valid & bear & (p.close < p.lo96) & (p.vol_ratio >= 1.2),
        ("pullback", 1): valid & bull & (p.adx >= 20) & (p.prev_close <= p.prev_fast) &
            (p.close > p.ema20) & (p.ret16 > 0) & p.rsi.between(35, 72),
        ("pullback", -1): valid & bear & (p.adx >= 20) & (p.prev_close >= p.prev_fast) &
            (p.close < p.ema20) & (p.ret16 < 0) & p.rsi.between(28, 65),
        ("range_reversal", 1): valid & (p.adx < 20) & (p.prev_z < -2) &
            (p.close > p.prev_close) & (p.close > p.open),
        ("range_reversal", -1): valid & (p.adx < 20) & (p.prev_z > 2) &
            (p.close < p.prev_close) & (p.close < p.open),
        ("rotation", 1): valid & bull & (p.ret96 > .02) & (p.ts % DAY == DAY-BAR),
        ("rotation", -1): valid & bear & (p.ret96 < -.02) & (p.ts % DAY == DAY-BAR),
    }
    out = {}
    for (family, side), mask in flags.items():
        for i in np.flatnonzero(mask.to_numpy()):
            r = p.iloc[i]
            if family == "breakout":
                stop, target, hold = max(.015, 3*r.atr), max(.06, 9*r.atr), 384
                score = abs(r.ret16)/r.atr + 2
            elif family == "pullback":
                stop, target, hold = max(.015, 2.5*r.atr), max(.05, 7.5*r.atr), 288
                score = abs(r.ret16)/r.atr + 1
            elif family == "range_reversal":
                stop, target, hold = max(.01, 2*r.atr), side*(r.mean96/r.close-1), 96
                score = abs(r.prev_z)
                if target <= 0:
                    continue
            else:
                stop, target, hold = max(.03, 3*r.atr), max(.10, 9*r.atr), 192
                score = abs(r.ret96)/r.atr
            # Large volatility is represented, but no unlimited position risk.
            if stop > .12 or target > .36:
                continue
            out.setdefault(int(r.ts), []).append(Signal(family, side, float(score), float(stop),
                float(target), hold, int(r.ts), float(r.close), float(r.atr)))
    return out


def compile_market(frames):
    compiled = {}
    for pair, raw in frames.items():
        f = features(raw)
        candidates = signals(f)
        for r in f[["ts", "open", "high", "low", "close", "atr", "age"]].itertuples(index=False, name=None):
            now = int(r[0])
            compiled.setdefault(now, {})[pair] = (tuple(float(x) for x in r[1:6]),
                candidates.get(now-BAR, []))
    return sorted(compiled.items())


def slots(equity):
    # Entry fees must not immediately collapse two slots at $100 into one.
    return min(6, max(1, math.ceil(max(0, equity)/50)))


def entry_price(mid, side, cfg):
    return mid*(1+side*cfg.spread_bps/20_000)*(1+side*cfg.slippage)


def exit_price(mid, side, cfg):
    return mid*(1-side*cfg.spread_bps/20_000)*(1-side*cfg.slippage)


def bar_exit(pos, bar, cfg):
    """Market-trigger approximation; worse gap opens and stop-first ambiguity.

    Extrema mode replaces intrabar trigger fills with candle extreme prices.
    Targets also pay taker fees and slippage; no guaranteed maker fills.
    """
    o, h, l, _, _ = bar
    side = pos["side"]
    def executable(mid):
        return mid*(1-side*cfg.spread_bps/20_000)
    opening, high, low = executable(o), executable(h), executable(l)
    stop, target = pos["stop_price"], pos["target_price"]
    stop_hit = low <= stop if side == 1 else high >= stop
    target_hit = target is not None and (high >= target if side == 1 else low <= target)
    gap_stop = opening <= stop if side == 1 else opening >= stop
    gap_target = target is not None and (opening >= target if side == 1 else opening <= target)
    if gap_stop:
        raw, reason = opening, "GAP_STOP"
    elif gap_target:
        raw, reason = opening, "GAP_TARGET"
    elif stop_hit:
        raw = (low if side == 1 else high) if cfg.execution == "extrema" else stop
        reason = "STOP"
    elif target_hit:
        raw = (high if side == 1 else low) if cfg.execution == "extrema" else target
        reason = "TARGET"
    else:
        return None
    return raw*(1-side*cfg.slippage), reason, bool(stop_hit and target_hit)


def simulate(market, cfg, start=None, end=None, family_schedule=None, allowed_families=FAMILIES,
        scheduled_exits=None):
    if cfg.family not in allowed_families or cfg.risk not in ("balanced", "aggressive"):
        raise ValueError("Unknown strategy or risk profile")
    if cfg.mode not in ("long_only", "synthetic_long_short") or cfg.execution not in ("trigger", "extrema"):
        raise ValueError("Unknown execution or side mode")
    if (not all(math.isfinite(x) for x in (cfg.spread_bps, cfg.slippage,
            cfg.starting_balance, cfg.short_carry_per_day, cfg.daily_operating_cost_usd)) or
            not 0 <= cfg.spread_bps <= 100 or not 0 <= cfg.slippage <= .05 or
            not 0 <= cfg.short_carry_per_day <= .05 or cfg.starting_balance <= 0 or
            cfg.daily_operating_cost_usd < 0):
        raise ValueError("Invalid costs or starting capital")
    if cfg.fee_profile not in FEE_PROFILES:
        raise ValueError("Unknown fee scenario")
    fees, balance, positions, trades = Fees(cfg.fee_profile), cfg.starting_balance, {}, []
    peak, max_dd, day_start, risk_day = balance, 0.0, balance, None
    halted, daily_halt, last, counts, curve = False, False, {}, Counter(), []
    max_slots, max_reserved, max_exposure, min_fee = 0, 0.0, 0.0, fees.tiers[0][1]
    first, finish, last_now = None, None, None
    operating_cost = 0.0
    pending_exits = {}
    exit_times = iter(sorted((scheduled_exits or {}).items()))
    next_exit = next(exit_times, None)

    def pnl(pos, price, now, fee_rate):
        gross = pos["stake"]*(price/pos["entry_price"]-1)*pos["side"]
        exit_fee = pos["stake"]*price/pos["entry_price"]*fee_rate
        carry = pos["stake"]*cfg.short_carry_per_day*max(0, now-pos["entry_ms"])/DAY if pos["side"] == -1 else 0
        return gross, exit_fee, carry

    def equity(now):
        total = balance
        rate = fees.rate(now)
        for pair, pos in positions.items():
            gross, fee, carry = pnl(pos, exit_price(last[pair], pos["side"], cfg), now, rate)
            total += gross-fee-carry
        return total

    def close(pair, price, now, reason, ambiguous=False):
        nonlocal balance, min_fee
        pos = positions.pop(pair)
        pending_exits.pop(pair, None)
        rate = fees.rate(now)
        min_fee = min(min_fee, rate)
        gross, fee, carry = pnl(pos, price, now, rate)
        balance += gross-fee-carry
        fees.record(now, pos["stake"]*price/pos["entry_price"])
        trades.append(dict(pos, pair=pair, exit_ms=now, exit_price=price, reason=reason,
            ambiguous_bar=ambiguous, gross_pnl=gross, exit_fee=fee, carry=carry,
            pnl=gross-pos["entry_fee"]-fee-carry))

    for now, rows in market:
        if (start is not None and now < start) or (end is not None and now >= end):
            continue
        first = now if first is None else first
        elapsed = BAR if last_now is None else now-last_now
        cost = cfg.daily_operating_cost_usd*elapsed/DAY
        balance -= cost
        operating_cost += cost
        last_now, finish = now, now+BAR
        for pair, (bar, _) in rows.items():
            last[pair] = bar[0]
        marked = equity(now)
        fresh = all(pair in rows for pair in positions)
        if risk_day != now//DAY and fresh:
            risk_day, day_start, daily_halt = now//DAY, marked, False
        peak = max(peak, marked)
        max_dd = max(max_dd, 1-marked/peak)
        halted = halted or marked <= 0 or marked <= peak*(1-cfg.drawdown_limit)
        daily_halt = daily_halt or marked <= day_start*(1-cfg.daily_loss_limit)
        # Existing positions see the opening quote before new orders reserve cash.
        while next_exit is not None and next_exit[0] <= now:
            scheduled_ms, routes_by_pair = next_exit
            for pair, routes in routes_by_pair.items():
                for exit_family, (signal_ms, reason, desired_side) in routes.items():
                    if signal_ms != scheduled_ms-BAR or desired_side not in (-1, 0, 1):
                        raise ValueError("Exit instruction must use the previous closed candle and a valid side")
                    if (pair in positions and positions[pair]["family"] == exit_family and
                            positions[pair]["side"] != desired_side):
                        pending_exits.setdefault(pair, (signal_ms, reason))
            next_exit = next(exit_times, None)
        for pair, pos in list(positions.items()):
            if pair not in rows:
                counts["missing_held_candle"] += 1
                continue
            if halted or daily_halt or now-pos["entry_ms"] >= pos["hold_bars"]*BAR:
                close(pair, exit_price(rows[pair][0][0], pos["side"], cfg), now,
                      "DRAWDOWN_HALT" if halted else "DAILY_HALT" if daily_halt else "TIME_EXIT")
            elif pair in pending_exits:
                signal_ms, reason = pending_exits[pair]
                pos["exit_signal_ms"] = signal_ms
                close(pair, exit_price(rows[pair][0][0], pos["side"], cfg), now, reason)
        month = pd.Timestamp(now, unit="ms", tz="UTC").strftime("%Y-%m")
        family = cfg.family if family_schedule is None else family_schedule.get(month)
        opportunities = []
        if not halted and not daily_halt and family:
            for pair, (_, candidates) in rows.items():
                eligible = [s for s in candidates if (family == "blend" or s.family == family)
                    and (cfg.mode != "long_only" or s.side == 1)]
                counts["raw_signals"] += len(eligible)
                if len({s.side for s in eligible}) > 1:
                    counts["conflicting_sides"] += 1
                    continue
                if eligible:
                    opportunities.append((max(eligible, key=lambda s:s.score), pair))
            for sig, pair in sorted(opportunities, key=lambda x:(-x[0].score, x[1])):
                if sig.signal_ms != now-BAR:
                    raise ValueError("Entry signal is not the previous closed candle")
                marked = equity(now)
                capacity = slots(marked)
                if pair in positions or len(positions) >= capacity:
                    counts["occupied_or_capacity"] += 1
                    continue
                rate = fees.rate(now)
                mid = rows[pair][0][0]
                if sig.reference_price is not None and abs(mid/sig.reference_price-1) > max(.01, 3*sig.atr)+1e-12:
                    counts["opening_price_drift"] += 1
                    continue
                price = entry_price(mid, sig.side, cfg)
                target = sig.target
                if sig.family == "range_reversal" and sig.reference_price is not None:
                    mean_anchor = sig.reference_price*(1+sig.side*sig.target)
                    target = sig.side*(mean_anchor/price-1)
                if target is not None and target <= 2*rate+2*cfg.slippage+cfg.spread_bps/10_000+.01:
                    counts["target_below_cost_buffer"] += 1
                    continue
                reserved = sum(p["stake"] for p in positions.values())
                free = max(0, balance-reserved)
                stake = min(marked*cfg.risk_fraction/(sig.stop+2*rate+2*cfg.slippage),
                    .8*marked/capacity, max(0, .8*marked-reserved), free/(1+rate))
                if family == "blend":
                    family_stake = sum(p["stake"] for p in positions.values() if p["family"] == sig.family)
                    stake = min(stake, max(0, .5*marked-family_stake))
                if stake < 5:
                    counts["insufficient_cash_or_family_budget"] += 1
                    continue
                entry_fee = stake*rate
                balance -= entry_fee
                fees.record(now, stake)
                min_fee = min(min_fee, rate)
                positions[pair] = dict(family=sig.family, side=sig.side, stake=stake,
                    entry_ms=now, signal_ms=sig.signal_ms, entry_price=price,
                    entry_fee=entry_fee, stop_price=price*(1-sig.side*sig.stop),
                    target_price=None if target is None else price*(1+sig.side*target), hold_bars=sig.hold_bars,
                    initial_stop=sig.stop, peak_price=price)
                positions[pair]["trailing"] = sig.trailing
                positions[pair]["trailing_distance"] = sig.trailing_distance
                counts["opened"] += 1
                max_slots = max(max_slots, len(positions))
                reserved += stake
                max_reserved = max(max_reserved, reserved)
                max_exposure = max(max_exposure, reserved/marked)
        for pair, pos in list(positions.items()):
            if pair not in rows:
                continue
            result = bar_exit(pos, rows[pair][0], cfg)
            if result:
                price, reason, ambiguous = result
                # The bar's exact trigger time is unknown; conservatively age
                # cost/volume records to its end, never to an invented tick.
                close(pair, price, now+BAR-1, reason, ambiguous)
                continue
            o, h, l, c, atr = rows[pair][0]
            # Trailing levels take effect next bar; this bar cannot see its own
            # future favorable extreme before checking its old stop.
            if pos["family"] != "range_reversal" and pos.get("trailing", True):
                if pos["side"] == 1:
                    pos["peak_price"] = max(pos["peak_price"], h)
                    if pos["peak_price"] >= pos["entry_price"]*(1+pos["initial_stop"]):
                        distance = pos.get("trailing_distance") or max(.01, 3*atr)
                        pos["stop_price"] = max(pos["stop_price"], pos["peak_price"]*(1-distance))
                else:
                    pos["peak_price"] = min(pos["peak_price"], l)
                    if pos["peak_price"] <= pos["entry_price"]*(1-pos["initial_stop"]):
                        distance = pos.get("trailing_distance") or max(.01, 3*atr)
                        pos["stop_price"] = min(pos["stop_price"], pos["peak_price"]*(1+distance))
        for pair, (bar, _) in rows.items():
            last[pair] = bar[3]
        marked = equity(now+BAR-1)
        peak = max(peak, marked)
        max_dd = max(max_dd, 1-marked/peak)
        halted = halted or marked <= 0 or marked <= peak*(1-cfg.drawdown_limit)
        daily_halt = daily_halt or marked <= day_start*(1-cfg.daily_loss_limit)
        if halted or daily_halt:
            for pair, pos in list(positions.items()):
                if pair in rows:
                    close(pair, exit_price(last[pair], pos["side"], cfg), now+BAR-1,
                          "DRAWDOWN_HALT" if halted else "DAILY_HALT")
            marked = equity(now+BAR-1)
            max_dd = max(max_dd, 1-marked/peak)
        if now % DAY == DAY-BAR or now == market[-1][0] or (end is not None and now+BAR >= end):
            curve.append(dict(ts=now+BAR, equity=marked))
    if last_now is None:
        raise ValueError("No candles in simulation window")
    final_rows = next(rows for now, rows in reversed(market) if now == last_now)
    for pair, pos in list(positions.items()):
        if pair in final_rows:
            close(pair, exit_price(final_rows[pair][0][3], pos["side"], cfg), finish-1, "WINDOW_END")
    ending = equity(finish-1)
    max_dd = max(max_dd, 1-ending/peak)
    if not curve or curve[-1]["ts"] != finish:
        curve.append(dict(ts=finish, equity=ending))
    else:
        curve[-1]["equity"] = ending
    wins = sum(t["pnl"] > 0 for t in trades)
    profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    summary = dict(start_ms=first, end_ms=finish, starting_balance=cfg.starting_balance,
        ending_equity=ending, return_pct=100*(ending/cfg.starting_balance-1),
        realized_pnl=balance-cfg.starting_balance, trades=len(trades), wins=wins,
        operating_cost_usd=operating_cost,
        win_rate_pct=100*wins/len(trades) if trades else None,
        profit_factor=profit/loss if loss else None, max_drawdown_pct=100*max_dd,
        fees=sum(t["entry_fee"]+t["exit_fee"] for t in trades)+sum(p["entry_fee"] for p in positions.values()),
        short_carry=sum(t["carry"] for t in trades), pending_positions=len(positions),
        ruined=ending <= 0, halted=halted, max_concurrent=max_slots,
        max_reserved_notional=max_reserved, max_exposure_pct=100*max_exposure,
        lowest_taker_fee_pct=100*min_fee, ambiguous_bars=sum(t["ambiguous_bar"] for t in trades),
        peak_equity=peak, recorded_fill_gross_pnl=sum(t["gross_pnl"] for t in trades),
        exit_reasons=dict(Counter(t["reason"] for t in trades)),
        median_hold_hours=float(np.median([(t["exit_ms"]-t["entry_ms"])/3_600_000 for t in trades])) if trades else None,
        by_strategy={f:dict(trades=sum(t["family"] == f for t in trades),
            pnl=sum(t["pnl"] for t in trades if t["family"] == f))
            for f in sorted(set(allowed_families)-{"blend"} | {t["family"] for t in trades})},
        diagnostics=dict(counts))
    return dict(config=asdict(cfg), summary=summary, trades=trades, equity_curve=curve)


def month_windows(market):
    start, end = market[0][0], market[-1][0]+BAR
    first = pd.Timestamp(start, unit="ms", tz="UTC")
    cursor = pd.Timestamp(year=first.year, month=first.month, day=1, tz="UTC")
    windows = []
    while cursor.value//1_000_000 < end:
        following = cursor+pd.offsets.MonthBegin(1)
        lo, hi = max(start, cursor.value//1_000_000), min(end, following.value//1_000_000)
        windows.append((cursor.strftime("%Y-%m"), int(lo), int(hi),
            lo != cursor.value//1_000_000 or hi != following.value//1_000_000))
        cursor = following
    return windows


def buy_and_hold(market, cfg):
    """Costed BTC and equal-weight spot baselines, fully allocated once."""
    first, last = {}, {}
    for now, rows in market:
        for pair, (bar, _) in rows.items():
            first.setdefault(pair, (now, bar[0]))
            last[pair] = (now+BAR, bar[3])
    returns = {}
    for pair, (now, opening) in first.items():
        rate = FEE_PROFILES[cfg.fee_profile][0][1]
        stake = 100/(1+rate)
        entry = entry_price(opening, 1, cfg)
        exit = exit_price(last[pair][1], 1, cfg)
        proceeds = stake*exit/entry*(1-rate)
        returns[pair] = dict(start_ms=now, end_ms=last[pair][0], ending_equity=proceeds,
            return_pct=proceeds-100)
    return dict(btc=returns.get("BTC/USD"), equal_weight_ending_equity=
        sum(r["ending_equity"] for r in returns.values())/len(returns), by_asset=returns)


def prior_month_schedule(windows, monthly_by_family):
    schedule = {windows[0][0]: None}
    for i in range(1, len(windows)):
        best, family = max(((months[i-1], family) for family, months in monthly_by_family.items()),
                           key=lambda x:x[0]["return_pct"])
        schedule[windows[i][0]] = family if best["return_pct"] > 0 and not best["pending_positions"] else None
    return schedule


def load_frames(directories):
    frames, manifest = {}, []
    for pair in PAIRS:
        parts = []
        for directory in directories:
            path = Path(directory)/(pair.replace("/", "_")+"-15m.feather")
            raw = path.read_bytes()
            f = normalized(pd.read_feather(path))
            manifest.append(dict(pair=pair, path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                bars=len(f), gaps=int((f.ts.diff().dropna() != BAR).sum()),
                start_ms=int(f.ts.iloc[0]), end_ms=int(f.ts.iloc[-1])+BAR))
            parts.append(f)
        frames[pair] = normalized(pd.concat(parts, ignore_index=True))
    return frames, manifest


LIMITATIONS = [
    "Q1/Q2 have already been used for development. No result is an unseen holdout or permission to trade.",
    "Custom hypotheses are inspired by strategy families; published papers do not validate these exact rules.",
    "15m OHLC cannot reconstruct quote polling, liquidity, queues or intrabar portfolio equity. No leverage is modeled.",
    "Trigger fills assume executable market triggers; gap opens are honored, ambiguous bars stop first. Compare extrema stress fills.",
    "Drawdown halts are triggers, not guaranteed loss ceilings. Sampling, gaps and missing held candles can overshoot them.",
    "Long-only uses spot accounting. Synthetic shorts reserve full notional but are not executable spot shorts; carry is an assumed 0.03% per day.",
    "Slippage is an assumption of 0.10% per side. Published spot taker tiers use simulated rolling volume, not account eligibility.",
    "Calendar-month experiments reset to $100. The separate continuous experiment compounds without resets.",
    "Multiple strategy comparisons can overfit development data. Past-month selection is descriptive and does not make reused data unseen.",
    "Operating costs default to zero; set --daily-operating-cost-usd to charge a user-supplied running-cost estimate.",
]


def save_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, allow_nan=False)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--families", nargs="+", choices=FAMILIES, default=list(FAMILIES))
    parser.add_argument("--risks", nargs="+", choices=("balanced", "aggressive"), default=["balanced", "aggressive"])
    parser.add_argument("--modes", nargs="+", choices=("long_only", "synthetic_long_short"), default=["long_only", "synthetic_long_short"])
    parser.add_argument("--spreads", nargs="+", type=float, default=[5, 15])
    parser.add_argument("--executions", nargs="+", choices=("trigger", "extrema"), default=["trigger", "extrema"])
    parser.add_argument("--daily-operating-cost-usd", type=float, default=0)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frames, manifest = load_frames(args.data_dir)
    market = compile_market(frames)
    # Shared indicators need a contiguous warmup; gaps restart each asset.
    market = market[256:]
    if len(market) < 96:
        raise ValueError("Insufficient data after warmup")
    windows = month_windows(market)
    rows, monthly_lookup = [], {}
    combinations = [(f, r, m, s, e) for f in args.families for r in args.risks
                    for m in args.modes for s in args.spreads for e in args.executions]
    print(f"{VERSION}: {len(combinations)} frozen configurations; no forward activation.", flush=True)
    for index, (family, risk, mode, spread, execution) in enumerate(combinations, 1):
        cfg = Config(family, risk, mode, spread, execution,
            daily_operating_cost_usd=args.daily_operating_cost_usd)
        name = f"{family}-{risk}-{mode}-{spread:g}bps-{execution}"
        print(f"[{index}/{len(combinations)}] {name}", flush=True)
        result = simulate(market, cfg)
        monthly = []
        for month, lo, hi, partial in windows:
            month_result = simulate(market, cfg, lo, hi)
            monthly.append(dict(month=month, partial=partial, **month_result["summary"]))
        full = [m for m in monthly if not m["partial"]]
        result["monthly_independent_100"] = monthly
        result["limitations"] = LIMITATIONS
        result["sources"] = SOURCES
        result["input_manifest"] = manifest
        save_json(output/(name+".json"), result)
        if result["trades"]:
            pd.DataFrame(result["trades"]).to_csv(output/(name+"-trades.csv"), index=False)
        pd.DataFrame(result["equity_curve"]).to_csv(output/(name+"-equity.csv"), index=False)
        row = dict(name=name, config=asdict(cfg), **result["summary"],
            full_months=len(full), profitable_full_months=sum(m["return_pct"] > 0 for m in full),
            median_month_return_pct=float(np.median([m["return_pct"] for m in full])) if full else None,
            best_month_ending_equity=max(m["ending_equity"] for m in full) if full else None,
            worst_month_ending_equity=min(m["ending_equity"] for m in full) if full else None,
            months_ending_at_least_1000=sum(m["ending_equity"] >= 1000 for m in full),
            goal_observed=False if not full else any(m["ending_equity"] >= 1000 for m in full))
        row["development_screen_pass"] = bool(mode == "long_only" and len(full) >= 4 and
            row["return_pct"] > 0 and row["median_month_return_pct"] > 0 and
            row["profitable_full_months"] >= math.ceil(.6*len(full)) and
            row["trades"] >= 20 and row["profit_factor"] is not None and row["profit_factor"] >= 1.1 and
            row["max_drawdown_pct"] <= 100*cfg.drawdown_limit and
            not row["pending_positions"])
        rows.append(row)
        monthly_lookup[(risk, mode, spread, execution, family)] = monthly
        print(f"  End ${row['ending_equity']:.2f} | median month {row['median_month_return_pct']}% | trades {row['trades']} | DD {row['max_drawdown_pct']:.2f}%", flush=True)
        save_json(output/"multi-strategy-progress.json", dict(version=VERSION, completed=len(rows), total=len(combinations), reports=rows))
    adaptive = []
    for risk in args.risks:
        for mode in args.modes:
            for spread in args.spreads:
                for execution in args.executions:
                    schedule = prior_month_schedule(windows,
                        {f:monthly_lookup[(risk, mode, spread, execution, f)] for f in args.families})
                    cfg = Config("blend", risk, mode, spread, execution,
                        daily_operating_cost_usd=args.daily_operating_cost_usd)
                    result = simulate(market, cfg, family_schedule=schedule)
                    name = f"past-month-selector-{risk}-{mode}-{spread:g}bps-{execution}"
                    result.update(schedule=schedule, limitations=LIMITATIONS, sources=SOURCES, input_manifest=manifest)
                    save_json(output/(name+".json"), result)
                    adaptive.append(dict(name=name, config=asdict(cfg), schedule=schedule, **result["summary"]))
    robust = []
    for family in args.families:
        for risk in args.risks:
            group = [r for r in rows if r["config"]["family"] == family and
                r["config"]["risk"] == risk and r["config"]["mode"] == "long_only"]
            scenarios = {(r["config"]["spread_bps"], r["config"]["execution"]) for r in group}
            if {(5, "trigger"), (15, "trigger"), (5, "extrema"), (15, "extrema")} <= scenarios and all(
                    r["development_screen_pass"] for r in group):
                robust.append(f"{family}-{risk}-long_only")
    baselines = {f"{spread:g}bps":buy_and_hold(market, Config(spread_bps=spread)) for spread in args.spreads}
    payload = dict(version=VERSION, status="DEVELOPMENT_ONLY_NO_ACTIVATION", sources=SOURCES,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=LIMITATIONS, input_manifest=manifest, reports=rows, past_month_selectors=adaptive,
        robust_development_candidates=robust, buy_and_hold_baselines=baselines,
        goal="$100 to $1000 within a complete calendar month",
        required_compounded_daily_return_pct=100*(10**(1/30)-1))
    save_json(output/"multi-strategy-summary.json", payload)
    lines = ["# Multi-strategy development results", "", "No forward activation. Q1/Q2 are reused development data.", "",
        "| Configuration | End equity | Trades | Max DD | Median month | Months ending at $1000+ |", "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        median = "n/a" if r["median_month_return_pct"] is None else f"{r['median_month_return_pct']:.2f}%"
        lines.append(f"| {r['name']} | ${r['ending_equity']:.2f} | {r['trades']} | {r['max_drawdown_pct']:.2f}% | {median} | {r['months_ending_at_least_1000']}/{r['full_months']} |")
    lines.extend(["", "Robust development candidates: "+(", ".join(robust) if robust else "NONE"), "", *LIMITATIONS])
    (output/"multi-strategy-results.md").write_text("\n".join(lines)+"\n")
    print("Completed. Summary: multi-strategy-summary.json; readable table: multi-strategy-results.md", flush=True)


if __name__ == "__main__":
    main()
