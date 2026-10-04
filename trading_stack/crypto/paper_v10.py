"""V10 multi-regime, bidirectional synthetic paper experiment.

Only public Kraken data is read. Entries are prospective, priced at observed
bid/ask after the closed-candle scan. The frozen specification is stored with
the transactional ledger; changing it requires a new version and directory.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import signal
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from paper_final import atomic_json, iso

VERSION = "V10-PAPER-1"
BAR = 900_000
HOUR = 3_600_000
DAY = 24 * HOUR
PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "ADA/USD")
SPEC = dict(starting_balance=100.0, stake=15.0, max_open=3, max_same_side=2,
    session_days=7, daily_entry_cap=12, session_loss=5.0, daily_loss=2.0,
    friction=0.018, taker_fee_per_side=0.008, slippage_per_side=0.001,
    fee_source="https://support.kraken.com/articles/cross-platform-fee-tier-changes",
    fee_checked_on="2026-10-03", max_spread=0.002, cooldown_bars=4, max_hold_hours=8,
    entry_grace_seconds=240, min_atr=0.0007, max_atr=0.02,
    min_target=0.027, max_target=0.06, min_stop=0.008, max_stop=0.02,
    ema_fast=20, ema_slow=60, trend_atr=0.5, slope_atr=0.1,
    momentum=0.0015, min_volume_ratio=0.6, range_z=1.5, net_target_buffer=0.006,
    warmup_bars=160, quote_max_age_ms=90_000)
RUNNING = True


class Ledger:
    def __init__(self, path, now):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS charts (trade_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        row = self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()
        if row:
            self.state = json.loads(row[0])
            if self.state.get("version") != VERSION or self.state.get("spec") != SPEC:
                raise ValueError("Ledger specification differs; records will not be reset")
        else:
            self.state = dict(version=VERSION, spec=SPEC, started_ms=now,
                deadline_ms=now + SPEC["session_days"] * DAY, balance=100.0,
                positions={}, closed=[], cooldowns={}, boundaries={}, next_id=1,
                entries=0, daily_entries=0, risk_day=now // DAY,
                day_start_equity=100.0, daily_halt=False, halt_reason=None,
                peak_equity=100.0, max_drawdown_usd=0.0, cycles=0,
                intervals_evaluated=0, last_interval=None, diagnostics=[],
                activity=None, status="STARTING", last_success_ms=None,
                heartbeat_ms=now, last_quotes={}, errors=[], drain=False)
            self.commit()

    def commit(self, event=None):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES(1, ?)",
                (json.dumps(self.state, allow_nan=False),))
            if event:
                self.db.execute("INSERT INTO events(payload) VALUES(?)",
                    (json.dumps(event, allow_nan=False),))


def indicators(frame):
    f = frame.copy()
    c = f["close"]
    f["fast"] = c.ewm(span=SPEC["ema_fast"], adjust=False).mean()
    f["slow"] = c.ewm(span=SPEC["ema_slow"], adjust=False).mean()
    tr = pd.concat([f.high-f.low, (f.high-c.shift()).abs(), (f.low-c.shift()).abs()], axis=1).max(axis=1)
    f["atr"] = tr.ewm(alpha=1/14, adjust=False).mean() / c
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    f["rsi"] = (100 - 100 / (1 + up / down)).where(down != 0, 100).where((up+down) != 0, 50)
    f["ret4"] = c.pct_change(4)
    f["slope"] = f.slow.pct_change(8)
    f["vol_ratio"] = f.volume / f.volume.shift().rolling(20).median().replace(0, float("nan"))
    f["mean"] = c.rolling(20).mean()
    f["z"] = (c-f["mean"]) / c.rolling(20).std(ddof=0).replace(0, float("nan"))
    f["prior_high"] = f.high.shift().rolling(16).max()
    f["prior_low"] = f.low.shift().rolling(16).min()
    return f


def validate_frame(rows, now, pair):
    expected = now // BAR * BAR - BAR
    f = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    if f.empty:
        raise ValueError(f"{pair}: empty candles")
    f = f.loc[f.ts <= expected].reset_index(drop=True)
    if len(f) < SPEC["warmup_bars"] or int(f.ts.iloc[-1]) != expected:
        raise ValueError(f"{pair}: insufficient or stale closed 15m candles")
    if not all(math.isfinite(x) for x in f.to_numpy(dtype=float).flat):
        raise ValueError(f"{pair}: nonfinite candle")
    if not (f.ts.diff().iloc[1:] == BAR).all():
        raise ValueError(f"{pair}: missing or duplicate 15m candles")
    if not ((f.ts % BAR == 0) & (f.low > 0) & (f.volume >= 0) &
            (f.high >= f[["open", "close", "low"]].max(axis=1)) &
            (f.low <= f[["open", "close"]].min(axis=1))).all():
        raise ValueError(f"{pair}: invalid OHLC values")
    return indicators(f)


def validate_quotes(tickers, now):
    quotes, errors = {}, []
    for pair in PAIRS:
        try:
            t = tickers.get(pair, {})
            bid, ask = float(t.get("bid") or 0), float(t.get("ask") or 0)
            if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask):
                raise ValueError("missing or invalid bid/ask")
            stamp = t.get("timestamp")
            if stamp is not None and not (-5000 <= now-float(stamp) <= SPEC["quote_max_age_ms"]):
                raise ValueError("stale ticker")
            quotes[pair] = dict(bid=bid, ask=ask, observed_ms=now)
        except (ValueError, TypeError) as exc:
            errors.append(f"{pair}: {exc}")
    return quotes, errors


def signal_for(f, index=None):
    """The same causal function is used for runtime and activity diagnostics."""
    i = len(f)-1 if index is None else index
    r, prev = f.iloc[i], f.iloc[i-1]
    atr = float(r.atr)
    out = dict(signal=False, side=None, regime="RANGE", tag=None, score=0.0,
        target_pct=None, stop_pct=None, reason="No confirmed range reversal",
        close=float(r.close), atr_pct=atr, rsi=float(r.rsi),
        momentum_pct=float(r.ret4) if math.isfinite(float(r.ret4)) else None,
        volume_ratio=float(r.vol_ratio) if math.isfinite(float(r.vol_ratio)) else None)
    if not all(math.isfinite(float(r[k])) for k in ("atr", "rsi", "ret4", "slope", "vol_ratio")):
        out["reason"] = "Indicators unavailable or zero recent volume"
        return out
    if not SPEC["min_atr"] <= atr <= SPEC["max_atr"]:
        out["reason"] = "Volatility outside allowed range"
        return out
    gap = float((r.fast-r.slow)/r.close)
    direction = 1 if gap > atr*SPEC["trend_atr"] and r.slope > atr*SPEC["slope_atr"] else (
        -1 if gap < -atr*SPEC["trend_atr"] and r.slope < -atr*SPEC["slope_atr"] else 0)
    out["regime"] = "UPTREND" if direction == 1 else "DOWNTREND" if direction == -1 else "RANGE"
    if r.vol_ratio < SPEC["min_volume_ratio"]:
        out["reason"] = "Volume below 60% of prior median"
        return out
    target = max(SPEC["min_target"], 4*atr)
    stop = min(SPEC["max_stop"], max(SPEC["min_stop"], 2*atr))
    if direction:
        out["side"] = "LONG" if direction == 1 else "SHORT"
        momentum = direction * float(r.ret4)
        aligned = direction * (float(r.close)-float(r.fast)) > 0
        rsi_ok = 42 <= r.rsi <= 72 if direction == 1 else 28 <= r.rsi <= 58
        if momentum < SPEC["momentum"] or not aligned:
            out["reason"] = "Trend present; waiting for price and 1h momentum confirmation"
            return out
        if not rsi_ok:
            out["reason"] = "RSI too stretched for trend entry"
            return out
        breakout = r.close > r.prior_high if direction == 1 else r.close < r.prior_low
        out.update(tag="trend_breakout" if breakout and r.vol_ratio >= 1 else "trend_continuation",
            score=abs(gap)/atr + momentum/atr, reason="Own-asset trend and 1h momentum confirmed")
    else:
        long = math.isfinite(float(prev.z)) and prev.z <= -SPEC["range_z"] and r.close > prev.close and r.close > r.open
        short = math.isfinite(float(prev.z)) and prev.z >= SPEC["range_z"] and r.close < prev.close and r.close < r.open
        if not long and not short:
            return out
        direction = 1 if long else -1
        target = direction * (float(r["mean"])-float(r.close))/float(r.close)
        out["side"] = "LONG" if long else "SHORT"
        if target < SPEC["min_target"]:
            out["reason"] = "Range reversal has insufficient room after costs"
            return out
        out.update(tag="range_reversal", score=abs(float(prev.z)),
            reason="Prior 1.5-sigma stretch reversed; room to rolling mean")
    if target > SPEC["max_target"]:
        out["reason"] = "Required target outside allowed range"
        return out
    out.update(signal=True, target_pct=target, stop_pct=stop)
    return out


def activity_report(frames):
    rows = []
    for pair in PAIRS:
        f = frames.get(pair)
        counts = Counter()
        if f is not None:
            for i in range(SPEC["warmup_bars"]-1, len(f)):
                result = signal_for(f, i)
                if result["signal"]:
                    counts[result["side"]] += 1
        rows.append(dict(pair=pair, long_signals=counts["LONG"], short_signals=counts["SHORT"],
            evaluated_bars=max(0, len(f)-SPEC["warmup_bars"]+1) if f is not None else 0))
    return dict(kind="HISTORICAL_SIGNAL_ACTIVITY_ONLY", rows=rows,
        total_signals=sum(r["long_signals"]+r["short_signals"] for r in rows),
        note="Overlapping raw signals, not trades or validation. No historical P&L is added to the ledger.")


def exit_price(pos, quote):
    return quote["ask"] if pos["is_short"] else quote["bid"]


def trade_row(pos, price, now, reason=None):
    gross = (price-pos["open_rate"])/pos["open_rate"] * (-1 if pos["is_short"] else 1)
    # Entry fee on entry notional, exit fee on exit notional. Open P&L includes
    # the modeled closing fee; closing realizes it once, never charges it twice.
    fee_ratio = SPEC["taker_fee_per_side"]*(1+price/pos["open_rate"])
    slippage_ratio = 2*SPEC["slippage_per_side"]
    net = gross-fee_ratio-slippage_ratio
    out = dict(pos, current_rate=price, profit_ratio=net, profit_abs=pos["stake_amount"]*net,
        fee_usd=pos["stake_amount"]*fee_ratio, slippage_allowance_usd=pos["stake_amount"]*slippage_ratio,
        gross_profit_abs=pos["stake_amount"]*gross, is_open=reason is None,
        price_observed_at=iso(now), timeframe="15m")
    if reason:
        out.update(close_rate=price, close_date=iso(now), close_ms=now, exit_reason=reason)
    return out


def close(ledger, pair, quote, now, reason):
    s = ledger.state
    pos = s["positions"].pop(pair)
    row = trade_row(pos, exit_price(pos, quote), now, reason)
    s["balance"] += row["profit_abs"]
    s["closed"].append(row)
    s["cooldowns"][pair] = now
    ledger.commit(dict(kind="CLOSE", **row))
    print(f"CLOSE {pair} {reason} net=${row['profit_abs']:.4f}", flush=True)


def manage(ledger, quotes, now, frames=None):
    s = ledger.state
    s["last_quotes"].update(quotes)
    marks = dict(s["last_quotes"], **quotes)
    if s["risk_day"] != now // DAY:
        # Resume on the new UTC day only after every held position has a fresh mark.
        if all(p in quotes for p in s["positions"]):
            s.update(risk_day=now//DAY, daily_entries=0, daily_halt=False,
                day_start_equity=s["balance"]+sum(trade_row(p, exit_price(p, quotes[k]), now)["profit_abs"]
                    for k,p in s["positions"].items()))
    equity = s["balance"]+sum(trade_row(p, exit_price(p, marks[k]), now)["profit_abs"]
        for k,p in s["positions"].items() if k in marks)
    s["peak_equity"] = max(s["peak_equity"], equity)
    s["max_drawdown_usd"] = max(s["max_drawdown_usd"], s["peak_equity"]-equity)
    if equity <= SPEC["starting_balance"]-SPEC["session_loss"]:
        s["halt_reason"] = "SESSION_LOSS_LIMIT"
    if now >= s["deadline_ms"] and not s["halt_reason"]:
        s["halt_reason"] = "SESSION_COMPLETE"
    if equity <= s["day_start_equity"]-SPEC["daily_loss"]:
        s["daily_halt"] = True
    for pair,pos in list(s["positions"].items()):
        q = quotes.get(pair)
        if q is None or now-q["observed_ms"] > SPEC["quote_max_age_ms"]:
            continue
        price = exit_price(pos, q)
        pos["price_history"] = (pos.get("price_history", [])+[price])[-80:]
        reason = s["halt_reason"] or ("DAILY_LOSS_LIMIT" if s["daily_halt"] else None)
        short = pos["is_short"]
        if not reason and (price >= pos["stop_price"] if short else price <= pos["stop_price"]):
            reason = "HARD_STOP"
        if not reason and (price <= pos["target_price"] if short else price >= pos["target_price"]):
            reason = "GROSS_TARGET"
        if not reason and now-pos["open_ms"] >= SPEC["max_hold_hours"]*HOUR:
            reason = "TIME_EXIT"
        f = (frames or {}).get(pair)
        if not reason and f is not None and int(f.ts.iloc[-1]) >= pos["signal_ms"]+2*BAR:
            r = f.iloc[-1]
            reversed_trend = (r.fast > r.slow and r.close > r.fast) if short else (r.fast < r.slow and r.close < r.fast)
            if reversed_trend:
                reason = "TREND_REVERSAL"
        if reason:
            close(ledger, pair, q, now, reason)


def evaluate(ledger, frames, quotes, now):
    s = ledger.state
    expected = now // BAR*BAR-BAR
    scans, candidates = [], []
    diagnostics = {r["pair"]: r for r in s["diagnostics"]}
    for pair in PAIRS:
        f = frames.get(pair)
        if f is None or int(f.ts.iloc[-1]) != expected:
            diagnostics[pair] = dict(pair=pair, signal=False, reason="Waiting for valid closed candles")
            continue
        if s["boundaries"].get(pair, -1) >= expected:
            continue
        first = pair not in s["boundaries"]
        result = dict(signal_for(f), pair=pair, candle=iso(expected), execution="WAITING")
        diagnostics[pair] = result
        s["boundaries"][pair] = expected
        scans.append(dict(result, first_scan=first))
        reason = None
        if first:
            reason = "Forward boundary set; entries begin next 15m close"
        elif s["halt_reason"] or s["daily_halt"] or s["drain"]:
            reason = s["halt_reason"] or ("DAILY_LOSS_LIMIT" if s["daily_halt"] else "DRAINING")
        elif s["risk_day"] != now//DAY:
            reason = "Waiting for held-position marks before UTC-day reset"
        elif now-(expected+BAR) > SPEC["entry_grace_seconds"]*1000:
            reason = "Missed entry window; no late fill"
        elif result["signal"]:
            candidates.append(result)
        if reason:
            result["execution"] = reason
    s["diagnostics"] = [diagnostics[p] for p in PAIRS if p in diagnostics]
    if not scans:
        return
    if any(not r["first_scan"] for r in scans) and s["last_interval"] != expected:
        s["intervals_evaluated"] += 1
        s["last_interval"] = expected
    # Consume each signal before its possible fill, preventing duplicates on restart.
    ledger.commit(dict(kind="SCAN", candle=iso(expected), rows=scans))
    for result in sorted(candidates, key=lambda r:r["score"], reverse=True):
        pair = result["pair"]
        q = quotes.get(pair)
        reason = None
        short = result["side"] == "SHORT"
        if pair in s["positions"]:
            reason = "Position already open"
        elif now-s["cooldowns"].get(pair, 0) < SPEC["cooldown_bars"]*BAR:
            reason = "1h cooldown after exit"
        elif len(s["positions"]) >= SPEC["max_open"]:
            reason = "Portfolio position cap"
        elif sum(p["is_short"] == short for p in s["positions"].values()) >= SPEC["max_same_side"]:
            reason = "Same-direction exposure cap"
        elif s["daily_entries"] >= SPEC["daily_entry_cap"]:
            reason = "Daily entry cap"
        elif q is None or now-q["observed_ms"] > SPEC["quote_max_age_ms"]:
            reason = "No fresh bid/ask"
        else:
            spread = q["ask"]/q["bid"]-1
            midpoint = (q["ask"]+q["bid"])/2
            drift = abs(midpoint/result["close"]-1)
            reserved = sum(p["stake_amount"] for p in s["positions"].values())
            if spread > SPEC["max_spread"]:
                reason = "Spread above 0.20%"
            elif drift > max(0.006, 2*result["atr_pct"]):
                reason = "Price moved too far from signal candle"
            elif result["target_pct"] < (SPEC["taker_fee_per_side"]*(2+(-1 if short else 1)*result["target_pct"])
                    +2*SPEC["slippage_per_side"]+spread+SPEC["net_target_buffer"]):
                reason = "Target has insufficient room after costs"
            elif s["balance"]-reserved < SPEC["stake"]*(1+SPEC["friction"]):
                reason = "Insufficient unreserved paper balance"
        result["execution"] = reason or "OPENED"
        if reason:
            continue
        price = q["bid"] if short else q["ask"]
        sign = -1 if short else 1
        target, stop = result["target_pct"], result["stop_pct"]
        pos = dict(trade_id=f"v10-{s['next_id']}", pair=pair, is_short=short,
            stake_amount=SPEC["stake"], amount=SPEC["stake"]/price,
            open_rate=price, open_date=iso(now), open_ms=now, signal_ms=expected,
            target_price=price*(1+sign*target), stop_price=price*(1-sign*stop),
            enter_tag=result["tag"], regime=result["regime"], price_history=[price],
            target_rule=f"{target:.2%} gross / {target-SPEC['friction']:.2%} before future spread",
            risk_reward=target/stop, signal_reason=result["reason"],
            exit_logic="ATR target/stop, own-asset trend reversal, 8h time exit, daily/session loss limit or 7-day session end. Simulated exits use observed quotes and can gap.")
        s["positions"][pair] = pos
        s["entries"] += 1
        s["daily_entries"] += 1
        s["next_id"] += 1
        ledger.commit(dict(kind="OPEN", **pos))
        print(f"OPEN SYNTHETIC_{result['side']} {pair} {result['tag']} price={price} stake=$15", flush=True)
    ledger.commit()


def candle_rows(f):
    return [dict(time=iso(int(r.ts)), open=float(r.open), high=float(r.high),
        low=float(r.low), close=float(r.close), volume=float(r.volume)) for r in f.itertuples()]


def archive_charts(ledger, frames):
    """Preserve genuine candle data for inspecting older trades after cache rolls."""
    s = ledger.state
    with ledger.db:
        for p in list(s["positions"].values())+s["closed"]:
            f = frames.get(p["pair"])
            if f is None:
                continue
            start = p["open_ms"]//BAR*BAR-20*BAR
            end = (p.get("close_ms") or int(f.ts.iloc[-1]))+BAR
            subset = f.loc[(f.ts >= start) & (f.ts <= end)]
            if subset.empty or int(subset.ts.iloc[0]) > start:
                continue  # Never overwrite an older archive with unrelated new candles.
            ledger.db.execute("INSERT OR REPLACE INTO charts VALUES(?, ?)",
                (p["trade_id"], json.dumps(candle_rows(subset), allow_nan=False)))


def publish(ledger, directory, now):
    s = ledger.state
    rows = []
    for pair,pos in s["positions"].items():
        q = s["last_quotes"].get(pair)
        if q:
            row = trade_row(pos, exit_price(pos,q), q["observed_ms"])
            row["mark_stale"] = now-q["observed_ms"] > SPEC["quote_max_age_ms"]
            rows.append(row)
        else:
            rows.append(dict(pos, current_rate=None, profit_ratio=None, profit_abs=None,
                is_open=True, mark_stale=True, price_observed_at=None, timeframe="15m"))
    stale = any(r["mark_stale"] for r in rows)
    unrealized = None if any(r["profit_abs"] is None for r in rows) else sum(r["profit_abs"] for r in rows)
    status = "STALE_MARKS" if stale else s["status"]
    next_scan = max(s["boundaries"].values())+2*BAR if s["boundaries"] else now//BAR*BAR+BAR
    crypto = dict(bot_state=status, config=dict(strategy=VERSION+" / adaptive regimes",
        exchange="Kraken public data", timeframe="15m", runmode="SYNTHETIC PAPER", dry_run=True),
        open_pnl_usd=unrealized, closed_pnl_usd=s["balance"]-100,
        marked_equity=None if unrealized is None else s["balance"]+unrealized, marks_stale=stale,
        open_exposure_usd=sum(p["stake_amount"] for p in rows),
        open_trade_count=len(rows), closed_trade_count=len(s["closed"]),
        open_trades=rows, closed_trades=list(reversed(s["closed"])),
        profit=dict(closed_trade_count=len(s["closed"])), errors=s["errors"])
    payload = dict(version=VERSION, status=status, mode="SYNTHETIC_PAPER_ONLY",
        timestamp=iso(now), heartbeat_ms=s["heartbeat_ms"], last_success_ms=s["last_success_ms"],
        started_at=iso(s["started_ms"]), ends_at=iso(s["deadline_ms"]),
        next_evaluation_at=iso(next_scan), cycles=s["cycles"],
        intervals_evaluated=s["intervals_evaluated"], diagnostics=s["diagnostics"],
        activity=s["activity"], entries=s["entries"], daily_entries=s["daily_entries"],
        max_drawdown_usd=s["max_drawdown_usd"], crypto=crypto,
        note="Unvalidated V10 experiment. Synthetic long/short fills; no broker orders. 0.80% taker fee each side, 0.10% slippage allowance each side, plus observed bid/ask spread. Borrow/funding excluded.",
        safety=dict(live_trading=False, crypto_max_open_trades=SPEC["max_open"],
            crypto_stake_usd=15, crypto_stoploss="0.8–2% gross ATR stop",
            crypto_roi_reference="2.7–6% gross target, range requires room to mean",
            crypto_drawdown_lock="$2 UTC-day / $5 session loss triggers; gaps can exceed them",
            max_same_direction=2, daily_entry_cap=12, max_hold_hours=8,
            session_days=7, friction_allowance="~1.8% round trip + observed spread",
            fee_reference=SPEC["fee_source"]))
    atomic_json(Path(directory)/"summary.json", payload)
    return payload


class Runner:
    def __init__(self, ledger, directory, exchange):
        self.ledger, self.directory, self.exchange = ledger, Path(directory), exchange
        self.frames = {}

    def fresh_quotes(self):
        start = time.monotonic()
        ticks = self.exchange.fetch_tickers(list(PAIRS))
        now = int(time.time()*1000)
        if time.monotonic()-start > 15:
            raise ValueError("Quote response took more than 15 seconds")
        quotes, errors = validate_quotes(ticks, now)
        self.ledger.state["errors"].extend(errors)
        if not quotes:
            raise ValueError("No valid public bid/ask quotes")
        self.ledger.state["last_quotes"].update(quotes)
        return quotes, now

    def cycle(self):
        s = self.ledger.state
        s["errors"] = []
        s["drain"] = (self.directory/"drain").exists()
        try:
            quotes, now = self.fresh_quotes()
            manage(self.ledger, quotes, now)
            expected = now//BAR*BAR-BAR
            changed = False
            # Per-asset failures do not veto other assets or quote-based stops.
            for pair in PAIRS:
                cached = self.frames.get(pair)
                if cached is not None and int(cached.ts.iloc[-1]) == expected:
                    continue
                try:
                    rows = self.exchange.fetch_ohlcv(pair, "15m", limit=720)
                    self.frames[pair] = validate_frame(rows, now, pair)
                    changed = True
                except Exception as exc:
                    self.frames.pop(pair, None)
                    s["errors"].append(f"{pair}: {type(exc).__name__}: {str(exc)[:120]}")
            if changed:
                atomic_json(self.directory/"candles.json", dict(timestamp=iso(now),
                    timeframe="15m", pairs={p:candle_rows(f) for p,f in self.frames.items()}))
                quotes, now = self.fresh_quotes()
            manage(self.ledger, quotes, now, self.frames)
            evaluate(self.ledger, self.frames, quotes, now)
            archive_charts(self.ledger, self.frames)
            if s["activity"] is None and len(self.frames) == len(PAIRS):
                s["activity"] = activity_report(self.frames)
            s["cycles"] += 1
            s["last_success_ms"] = now
            s["status"] = s["halt_reason"] or ("DAILY_LOSS_LIMIT" if s["daily_halt"] else
                "DRAINING" if s["drain"] else "DEGRADED" if s["errors"] else "RUNNING")
        except Exception as exc:
            s["status"] = "DEGRADED"
            s["errors"].append(f"{type(exc).__name__}: {str(exc)[:200]}")
        now = int(time.time()*1000)
        s["heartbeat_ms"] = now
        self.ledger.commit()
        if s["errors"]:
            print("; ".join(s["errors"]), flush=True)
        return publish(self.ledger, self.directory, now)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="One public-data cycle; first scan never fills")
    parser.add_argument("--check-activity", action="store_true", help="Print historical raw signal counts")
    parser.add_argument("--state-dir", default=os.getenv("PAPER_V10_STATE_DIR", "/freqtrade/data/paper-v10"))
    args = parser.parse_args()
    directory = Path(args.state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory/"runtime.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger = Ledger(directory/"ledger.sqlite3", int(time.time()*1000))
    import ccxt
    exchange = ccxt.kraken({"enableRateLimit": True, "timeout": 10000})
    runner = Runner(ledger, directory, exchange)
    def stop(*_):
        global RUNNING
        RUNNING = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"START {VERSION} | seven-day synthetic PAPER | public data only", flush=True)
    try:
        while RUNNING:
            result = runner.cycle()
            if args.check_activity and result.get("activity"):
                print(json.dumps(result["activity"], indent=2), flush=True)
            if args.once:
                return 0 if result["status"] == "RUNNING" else 2
            for _ in range(30):
                if not RUNNING:
                    break
                time.sleep(1)
        ledger.state["status"] = "STOPPED"
        ledger.state["heartbeat_ms"] = int(time.time()*1000)
        ledger.commit()
        publish(ledger, directory, ledger.state["heartbeat_ms"])
        return 0
    finally:
        ledger.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
