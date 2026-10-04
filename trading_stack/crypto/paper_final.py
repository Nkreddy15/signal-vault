"""V9 overnight runtime, frozen V8 72h hypothesis, synthetic PAPER shorts only.

This is an operational release, not a newly validated strategy. Public market
data only; no credentials, broker methods, borrowing or funding are modeled.
SQLite commits the ledger and each event together. JSON is only a projection.
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
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from v8_forward_lab import PAIRS, add_indicators, btc_bear, pair_bear, breakdown

VERSION = "V9-OVERNIGHT-1"
HOUR = 3_600_000
SPEC = dict(candidate="v8_72h_t12_s4_cd24", starting_balance=100.0,
            stake=15.0, max_open=3, max_entries=6, friction=0.0074,
            target=0.12, stop=0.04, cooldown_hours=24, session_hours=8,
            loss_limit=3.0, max_spread=0.005)
RUNNING = True


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as fh:
        json.dump(value, fh, allow_nan=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class Ledger:
    def __init__(self, path, now):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        row = self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()
        if row:
            self.state = json.loads(row[0])
            if self.state.get("version") != VERSION or self.state.get("spec") != SPEC:
                raise ValueError("Existing session has a different frozen specification")
        else:
            self.state = dict(version=VERSION, spec=SPEC, started_ms=now,
                deadline_ms=now + SPEC["session_hours"] * HOUR, balance=100.0,
                positions={}, closed=[], cooldowns={}, next_id=1, entries=0,
                boundary=None, cycles=0, hours_evaluated=0, diagnostics=[],
                status="STARTING", last_success_ms=None, heartbeat_ms=now,
                quote_ms=None, errors=[], halt_reason=None, peak_equity=100.0,
                max_drawdown_usd=0.0)
            self.commit()

    def commit(self, event=None):
        # A process crash can never record a fill without its resulting ledger.
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (1, ?)",
                            (json.dumps(self.state, allow_nan=False),))
            if event:
                self.db.execute("INSERT INTO events(payload) VALUES (?)",
                                (json.dumps(event, allow_nan=False),))


def validate_quotes(tickers, now):
    quotes = {}
    for pair in PAIRS:
        t = tickers.get(pair, {})
        bid, ask = float(t.get("bid") or 0), float(t.get("ask") or 0)
        if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask):
            raise ValueError(f"{pair}: missing or invalid bid/ask")
        stamp = t.get("timestamp")
        if stamp is not None and not (-5000 <= now - float(stamp) <= 90_000):
            raise ValueError(f"{pair}: stale ticker")
        quotes[pair] = dict(bid=bid, ask=ask, observed_ms=now)
    return quotes


def validated_frames(exchange, now):
    frames, candles = {}, {}
    expected = now // HOUR * HOUR - HOUR
    for pair in PAIRS:
        rows = exchange.fetch_ohlcv(pair, "1h", limit=300)
        f = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        if f.empty:
            raise ValueError(f"{pair}: empty candles")
        f = f.loc[f.ts <= expected].reset_index(drop=True)
        if len(f) < 250 or int(f.ts.iloc[-1]) != expected:
            raise ValueError(f"{pair}: insufficient or stale closed candles")
        values = f.to_numpy(dtype=float)
        if not all(math.isfinite(x) for x in values.flat):
            raise ValueError(f"{pair}: nonfinite candle")
        if not (f.ts.diff().iloc[1:] == HOUR).all():
            raise ValueError(f"{pair}: missing or duplicate hourly candles")
        if not ((f.ts % HOUR == 0) & (f.low > 0) & (f.volume >= 0) &
                (f.high >= f[["open", "close", "low"]].max(axis=1)) &
                (f.low <= f[["open", "close"]].min(axis=1))).all():
            raise ValueError(f"{pair}: invalid OHLC values")
        frames[pair] = add_indicators(f)
        candles[pair] = [dict(time=iso(int(r.ts)), open=float(r.open), high=float(r.high),
            low=float(r.low), close=float(r.close), volume=float(r.volume))
            for r in f.itertuples()]
    return frames, candles, expected


def trade_row(pos, price, now, reason=None):
    gross = (pos["open_rate"] - price) / pos["open_rate"]
    net = gross - SPEC["friction"]
    out = dict(pos, current_rate=price, profit_ratio=net,
               profit_abs=pos["stake_amount"] * net, is_open=reason is None,
               price_observed_at=iso(now), timeframe="1h")
    if reason:
        out.update(close_rate=price, close_date=iso(now), exit_reason=reason)
    return out


def close(ledger, pair, quote, now, reason):
    s = ledger.state
    pos = s["positions"].pop(pair)
    row = trade_row(pos, quote["ask"], now, reason)
    s["balance"] += row["profit_abs"]
    s["closed"].append(row)
    s["cooldowns"][pair] = now
    ledger.commit(dict(kind="CLOSE", **row))
    print(f"CLOSE {pair} {reason} net=${row['profit_abs']:.4f}", flush=True)


def manage(ledger, quotes, now, frames=None):
    s = ledger.state
    open_pnl = sum(trade_row(p, quotes[pair]["ask"], now)["profit_abs"]
                   for pair, p in s["positions"].items())
    equity = s["balance"] + open_pnl
    s["peak_equity"] = max(s["peak_equity"], equity)
    s["max_drawdown_usd"] = max(s["max_drawdown_usd"], s["peak_equity"] - equity)
    if equity <= 100 - SPEC["loss_limit"]:
        s["halt_reason"] = "SESSION_LOSS_LIMIT"
    if now >= s["deadline_ms"] and not s["halt_reason"]:
        s["halt_reason"] = "SESSION_COMPLETE"
    for pair, pos in list(s["positions"].items()):
        price = quotes[pair]["ask"]
        reason = s["halt_reason"]
        if not reason and price >= pos["stop_price"]:
            reason = "HARD_STOP"
        if not reason and price <= pos["target_price"]:
            reason = "GROSS_TARGET"
        if not reason and frames is not None:
            btc = frames["BTC/USD"]
            f = frames[pair]
            regime = btc_bear(btc, len(btc)-1) and pair_bear(f, len(f)-1)
            if not regime and (pos["open_rate"] - price) / pos["open_rate"] < -0.01:
                reason = "REGIME_FAILURE"
        if reason:
            close(ledger, pair, quotes[pair], now, reason)


def evaluate(ledger, frames, quotes, closed_ms, now):
    s = ledger.state
    if s["halt_reason"]:
        return
    # The first scan records a boundary, never a retrospective paper trade.
    first = s["boundary"] is None
    if not first and closed_ms <= s["boundary"]:
        return
    if now // HOUR * HOUR - HOUR != closed_ms:
        raise ValueError("Candle boundary advanced during fetch; retry")
    btc = frames["BTC/USD"]
    btc_ok = btc_bear(btc, len(btc)-1)
    signals, diagnostics = [], []
    for pair in PAIRS:
        f = frames[pair]
        r = f.iloc[-1]
        po, bo = pair_bear(f, len(f)-1), breakdown(f, len(f)-1, 72)
        reason = "SIGNAL" if btc_ok and po and bo else (
            "BTC regime not bearish" if not btc_ok else
            "Pair regime not bearish" if not po else "No confirmed 72h breakdown")
        diagnostics.append(dict(pair=pair, signal=bool(btc_ok and po and bo),
            reason=reason, candle=iso(closed_ms), close=float(r["close"])))
        if btc_ok and po and bo:
            signals.append((abs(float(r.ret168)) + abs(float(r.ret72)) + float(r.atr_pct), pair))
    s["diagnostics"] = diagnostics
    s["boundary"] = closed_ms
    s["hours_evaluated"] += 0 if first else 1
    # Consume the candle before opening: restart can miss a fill, never duplicate it.
    ledger.commit(dict(kind="SCAN", candle=iso(closed_ms), first_scan=first, diagnostics=diagnostics))
    if first or now - (closed_ms + HOUR) > 10 * 60_000:
        return
    for _, pair in sorted(signals, reverse=True):
        if len(s["positions"]) >= SPEC["max_open"] or s["entries"] >= SPEC["max_entries"]:
            break
        if pair in s["positions"] or now - s["cooldowns"].get(pair, 0) < 24 * HOUR:
            continue
        q = quotes[pair]
        if now - q["observed_ms"] > 90_000 or q["ask"] / q["bid"] - 1 > SPEC["max_spread"]:
            continue
        reserved = sum(p["stake_amount"] for p in s["positions"].values())
        if s["balance"] - reserved < SPEC["stake"] * (1 + SPEC["friction"]):
            continue
        price = q["bid"]  # Short opens at bid; buy-to-cover always uses ask.
        pos = dict(trade_id=f"v9-{s['next_id']}", pair=pair, is_short=True,
            stake_amount=SPEC["stake"], amount=SPEC["stake"] / price,
            open_rate=price, open_date=iso(now), target_price=price * 0.88,
            stop_price=price * 1.04, enter_tag=SPEC["candidate"],
            target_rule="12% gross short target", risk_reward=3.0,
            signal_reason="BTC and pair bear regimes plus closed 72h breakdown; experimental hypothesis.",
            exit_logic="12% gross target, 4% stop, regime failure, $3 session loss trigger, or 8h session end. Poll-based simulated exits can gap.")
        s["positions"][pair] = pos
        s["entries"] += 1
        s["next_id"] += 1
        ledger.commit(dict(kind="OPEN", **pos))
        print(f"OPEN SYNTHETIC_SHORT {pair} bid={price} stake=$15", flush=True)


def publish(ledger, directory, quotes, now):
    s = ledger.state
    rows = []
    for pair, pos in s["positions"].items():
        quote = quotes.get(pair) or s.get("last_quotes", {}).get(pair)
        if quote:
            rows.append(trade_row(pos, quote["ask"], quote["observed_ms"]))
    stale = not s["quote_ms"] or now - s["quote_ms"] > 90_000
    status = s["status"]
    if stale and s["positions"]:
        status = "STALE_MARKS"
    unrealized = sum(r["profit_abs"] for r in rows)
    crypto = dict(bot_state=status, config=dict(strategy=VERSION + " / " + SPEC["candidate"],
        exchange="Kraken public data", timeframe="1h", runmode="SYNTHETIC PAPER", dry_run=True),
        open_pnl_usd=unrealized, closed_pnl_usd=s["balance"]-100,
        open_exposure_usd=sum(r["stake_amount"] for r in rows),
        open_trade_count=len(rows), closed_trade_count=len(s["closed"]),
        open_trades=rows, closed_trades=list(reversed(s["closed"])),
        profit=dict(closed_trade_count=len(s["closed"])), errors=s["errors"],
        marked_equity=s["balance"]+unrealized, marks_stale=stale)
    payload = dict(version=VERSION, mode="SYNTHETIC_PAPER_ONLY", timestamp=iso(now),
        heartbeat_ms=s["heartbeat_ms"], last_success_ms=s["last_success_ms"],
        started_at=iso(s["started_ms"]), ends_at=iso(s["deadline_ms"]),
        status=status, cycles=s["cycles"], hours_evaluated=s["hours_evaluated"],
        diagnostics=s["diagnostics"], crypto=crypto,
        note="Unvalidated V8 hypothesis; synthetic shorts, no broker orders. 0.74% round-trip cost allowance plus observed bid/ask spread. Borrow/funding excluded.",
        safety=dict(live_trading=False, crypto_max_open_trades=3, crypto_stake_usd=15,
            crypto_stoploss="4% gross (short)", crypto_roi_reference="12% gross (short)",
            crypto_drawdown_lock="$3 session loss trigger; gaps can exceed it",
            session_entry_cap=6, session_hours=8, friction_allowance="0.74% + spread"))
    atomic_json(Path(directory) / "summary.json", payload)
    return payload


class Runner:
    def __init__(self, ledger, directory, exchange):
        self.ledger, self.directory, self.exchange = ledger, Path(directory), exchange
        self.frames = None
        self.frame_hour = None
        self.quotes = {}

    def cycle(self):
        s = self.ledger.state
        s["errors"] = []
        try:
            started = time.monotonic()
            tickers = self.exchange.fetch_tickers(list(PAIRS))
            now = int(time.time()*1000)
            if time.monotonic() - started > 15:
                raise ValueError("Quote response too slow")
            self.quotes = validate_quotes(tickers, now)
            s["last_quotes"] = self.quotes
            s["quote_ms"] = now
            # Stops and session expiry work even when candle downloads fail.
            manage(self.ledger, self.quotes, now)
            expected = now // HOUR * HOUR - HOUR
            if not s["halt_reason"]:
                if self.frame_hour != expected:
                    self.frames, candles, self.frame_hour = validated_frames(self.exchange, now)
                    atomic_json(self.directory / "candles.json", dict(timestamp=iso(now), pairs=candles))
                    # A fill must use a quote observed after the signal scan.
                    started = time.monotonic()
                    tickers = self.exchange.fetch_tickers(list(PAIRS))
                    now = int(time.time()*1000)
                    if time.monotonic() - started > 15:
                        raise ValueError("Quote response too slow after candle scan")
                    self.quotes = validate_quotes(tickers, now)
                    s["last_quotes"] = self.quotes
                    s["quote_ms"] = now
                now = int(time.time()*1000)
                if now - s["quote_ms"] > 90_000:
                    raise ValueError("Quotes expired during candle fetch")
                manage(self.ledger, self.quotes, now, self.frames)
                evaluate(self.ledger, self.frames, self.quotes, self.frame_hour, now)
            s["cycles"] += 1
            s["last_success_ms"] = now
            s["status"] = s["halt_reason"] or "RUNNING"
        except Exception as exc:
            s["status"] = "DEGRADED"
            s["errors"] = [f"{type(exc).__name__}: {str(exc)[:250]}"]
            print(s["errors"][0], flush=True)
        now = int(time.time()*1000)
        s["heartbeat_ms"] = now
        self.ledger.commit()
        return publish(self.ledger, self.directory, self.quotes, now)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Public-data preflight; no history is backfilled")
    parser.add_argument("--state-dir", default=os.getenv("PAPER_FINAL_STATE_DIR", "/freqtrade/data/paper-final-v9"))
    args = parser.parse_args()
    directory = Path(args.state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory / "runtime.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger = Ledger(directory / "ledger.sqlite3", int(time.time()*1000))
    import ccxt
    exchange = ccxt.kraken({"enableRateLimit": True, "timeout": 10000})
    runner = Runner(ledger, directory, exchange)
    def stop(*_):
        global RUNNING
        RUNNING = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"START {VERSION} | synthetic PAPER only | frozen V8 hypothesis | no credentials", flush=True)
    while RUNNING:
        summary = runner.cycle()
        if args.once:
            return 0 if summary["status"] == "RUNNING" else 2
        for _ in range(30):
            if not RUNNING:
                break
            time.sleep(1)
    ledger.state["status"] = "STOPPED"
    ledger.state["heartbeat_ms"] = int(time.time()*1000)
    ledger.commit()
    publish(ledger, directory, runner.quotes, ledger.state["heartbeat_ms"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
