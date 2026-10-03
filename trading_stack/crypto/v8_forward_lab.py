"""Signal Vault overnight forward lab.

Purpose: generate genuinely new forward evidence overnight instead of pretending
a backtest candidate is already a production strategy.

The lab shadows four predeclared V8 short-only candidates in parallel on live
public Kraken market data. Each candidate has an independent paper ledger.
No exchange credentials are read and no order method is called.

Every completed 1h candle:
- records BTC + pair regime state,
- records exact signal candidates and near-signal diagnostics,
- opens/closes paper shorts independently per candidate,
- persists state atomically,
- tracks mark-to-market P&L between candle closes.

This is useful even if no trades fire because it records why each candidate did
or did not trade on fresh forward data.
"""

from __future__ import annotations

import csv
import json
import os
import signal
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ccxt
import pandas as pd


PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "ADA/USD")
STATE_DIR = Path(os.getenv("FORWARD_LAB_STATE_DIR", "/freqtrade/data/v8-forward-lab"))
STATE_PATH = STATE_DIR / "state.json"
EVENTS_PATH = STATE_DIR / "events.log"
HOURLY_PATH = STATE_DIR / "hourly_diagnostics.csv"
TRADES_PATH = STATE_DIR / "trades.csv"
SUMMARY_PATH = STATE_DIR / "summary.json"

STARTING_BALANCE = 100.0
STAKE = 15.0
MAX_OPEN = 3
FRICTION = 0.0074
POLL_SECONDS = int(os.getenv("FORWARD_LAB_POLL_SECONDS", "60"))
ENTRY_GRACE_MINUTES = int(os.getenv("FORWARD_LAB_ENTRY_GRACE_MINUTES", "10"))
RUNNING = True


@dataclass(frozen=True)
class Candidate:
    name: str
    breakout_hours: int
    target_gross: float
    stop_gross: float
    cooldown_hours: int


CANDIDATES = (
    Candidate("v8_72h_t12_s4_cd24", 72, 0.12, 0.04, 24),
    Candidate("v8_96h_t12_s4_cd24", 96, 0.12, 0.04, 24),
    Candidate("v8_144h_t12_s4_cd24", 144, 0.12, 0.04, 24),
    Candidate("v8_144h_t10_s35_cd48", 144, 0.10, 0.035, 48),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{utcnow().isoformat()} {message}"
    print(line, flush=True)
    with EVENTS_PATH.open("a") as fh:
        fh.write(line + "\n")


def handle_stop(signum, frame) -> None:
    global RUNNING
    RUNNING = False
    log(f"stop requested signal={signum}")


def candidate_state() -> dict[str, Any]:
    return {
        "balance": STARTING_BALANCE,
        "positions": {},
        "cooldowns": {},
        "closed_trades": 0,
        "signals": 0,
        "hours_evaluated": 0,
        "no_signal_hours": 0,
        "realized_pnl": 0.0,
        "max_closed_drawdown_pct": 0.0,
        "peak_balance": STARTING_BALANCE,
    }


def initial_state() -> dict[str, Any]:
    return {
        "version": "V8-FORWARD-LAB-1",
        "started_at": utcnow().isoformat(),
        "status": "RUNNING",
        "last_heartbeat": utcnow().isoformat(),
        "last_processed_closed_ms": None,
        "cycles": 0,
        "candidates": {c.name: candidate_state() for c in CANDIDATES},
    }


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text())
        state["status"] = "RUNNING"
        state["last_heartbeat"] = utcnow().isoformat()
        for c in CANDIDATES:
            state.setdefault("candidates", {}).setdefault(c.name, candidate_state())
    else:
        state = initial_state()
    save_state(state)
    return state


def ensure_csvs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not TRADES_PATH.exists():
        with TRADES_PATH.open("w", newline="") as fh:
            csv.writer(fh).writerow([
                "exit_time_utc", "candidate", "pair", "side", "entry_time_utc",
                "entry_price", "exit_price", "gross_return_pct",
                "net_return_pct", "pnl_usd", "reason", "hold_hours",
            ])
    if not HOURLY_PATH.exists():
        with HOURLY_PATH.open("w", newline="") as fh:
            csv.writer(fh).writerow([
                "closed_candle_utc", "candidate", "pair", "btc_bear",
                "pair_bear", "breakdown", "signal", "close", "ret24_pct",
                "ret72_pct", "ret168_pct", "rsi14", "vol_ratio", "atr_pct",
                "distance_to_breakout_pct",
            ])


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    close = f["close"]
    vol = f["volume"]
    f["ema20"] = close.ewm(span=20, adjust=False).mean()
    f["ema50"] = close.ewm(span=50, adjust=False).mean()
    f["ema100"] = close.ewm(span=100, adjust=False).mean()
    f["ema100_slope24"] = f["ema100"].pct_change(24)
    f["ret24"] = close.pct_change(24)
    f["ret72"] = close.pct_change(72)
    f["ret168"] = close.pct_change(168)
    f["rsi14"] = rsi(close)
    prev_close = close.shift(1)
    tr = pd.concat([
        f["high"] - f["low"],
        (f["high"] - prev_close).abs(),
        (f["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    f["atr14"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    f["atr_pct"] = f["atr14"] / close
    f["vol20"] = vol.rolling(20).mean()
    f["vol_ratio"] = vol / f["vol20"].replace(0.0, float("nan"))
    for lookback in (72, 96, 144):
        f[f"prior_low_{lookback}"] = f["low"].rolling(lookback).min().shift(1)
    return f


def fetch_frames(exchange: ccxt.Exchange) -> dict[str, pd.DataFrame]:
    frames = {}
    for pair in PAIRS:
        rows = exchange.fetch_ohlcv(pair, timeframe="1h", limit=300)
        if not rows or len(rows) < 250:
            raise RuntimeError(f"{pair}: insufficient 1h candles")
        frame = pd.DataFrame(
            rows, columns=["ts", "open", "high", "low", "close", "volume"]
        )
        frame["date"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
        frames[pair] = add_indicators(frame)
    return frames


def closed_index(frame: pd.DataFrame, now_ms: int) -> int:
    eligible = frame.index[frame["ts"] <= now_ms - 3600_000]
    if len(eligible) == 0:
        raise RuntimeError("no fully closed candle")
    return int(eligible[-1])


def btc_bear(frame: pd.DataFrame, idx: int) -> bool:
    r = frame.iloc[idx]
    return (
        float(r["close"]) < float(r["ema100"])
        and float(r["ema20"]) < float(r["ema50"])
        and float(r["ema50"]) < float(r["ema100"])
        and float(r["ema100_slope24"]) < -0.001
        and float(r["ret72"]) < -0.02
        and float(r["ret168"]) < -0.04
    )


def pair_bear(frame: pd.DataFrame, idx: int) -> bool:
    r = frame.iloc[idx]
    return (
        float(r["close"]) < float(r["ema100"])
        and float(r["ema20"]) < float(r["ema50"])
        and float(r["ema50"]) < float(r["ema100"])
        and float(r["ema100_slope24"]) < 0.0
        and float(r["ret72"]) < -0.02
    )


def breakdown(frame: pd.DataFrame, idx: int, lookback: int) -> bool:
    r = frame.iloc[idx]
    prior = float(r[f"prior_low_{lookback}"])
    return (
        float(r["close"]) < prior
        and float(r["ret24"]) < -0.015
        and 26 <= float(r["rsi14"]) <= 45
        and float(r["vol_ratio"]) >= 1.15
        and float(r["atr_pct"]) >= 0.008
    )


def short_gross(entry: float, price: float) -> float:
    return (entry - price) / entry


def cooldown_active(cs: dict[str, Any], pair: str, hours: int) -> bool:
    value = cs["cooldowns"].get(pair)
    if not value:
        return False
    return (utcnow() - datetime.fromisoformat(value)).total_seconds() < hours * 3600


def close_position(
    state: dict[str, Any],
    c: Candidate,
    pair: str,
    price: float,
    reason: str,
) -> None:
    cs = state["candidates"][c.name]
    pos = cs["positions"][pair]
    gross = short_gross(float(pos["entry_price"]), price)
    net = gross - FRICTION
    pnl = float(pos["stake"]) * net
    now = utcnow()
    hold = (now - datetime.fromisoformat(pos["entry_time"])).total_seconds() / 3600.0

    cs["balance"] = float(cs["balance"]) + pnl
    cs["realized_pnl"] = float(cs["realized_pnl"]) + pnl
    cs["closed_trades"] = int(cs["closed_trades"]) + 1
    cs["cooldowns"][pair] = now.isoformat()
    del cs["positions"][pair]
    cs["peak_balance"] = max(float(cs["peak_balance"]), float(cs["balance"]))
    peak = float(cs["peak_balance"])
    if peak > 0:
        dd = 100.0 * (peak - float(cs["balance"])) / peak
        cs["max_closed_drawdown_pct"] = max(float(cs["max_closed_drawdown_pct"]), dd)

    with TRADES_PATH.open("a", newline="") as fh:
        csv.writer(fh).writerow([
            now.isoformat(), c.name, pair, "SHORT", pos["entry_time"],
            pos["entry_price"], price, gross*100.0, net*100.0, pnl, reason, hold,
        ])
    log(
        f"{c.name} CLOSE {pair} reason={reason} gross_pct={gross*100:.3f} "
        f"net_pct={net*100:.3f} pnl_usd={pnl:.4f}"
    )


def manage_open_positions(
    exchange: ccxt.Exchange,
    state: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    idxs: dict[str, int],
) -> None:
    btc_ok = btc_bear(frames["BTC/USD"], idxs["BTC/USD"])
    for c in CANDIDATES:
        cs = state["candidates"][c.name]
        for pair in list(cs["positions"]):
            ticker = exchange.fetch_ticker(pair)
            price = float(ticker.get("last") or ticker.get("close"))
            pos = cs["positions"][pair]
            entry = float(pos["entry_price"])
            gross = short_gross(entry, price)
            held = (utcnow() - datetime.fromisoformat(pos["entry_time"])).total_seconds()/3600.0

            if price >= entry * (1.0 + c.stop_gross):
                close_position(state, c, pair, price, "paper_hard_stop")
            elif price <= entry * (1.0 - c.target_gross):
                close_position(state, c, pair, price, "paper_gross_target")
            elif held >= 240:
                close_position(state, c, pair, price, "paper_time_exit")
            elif (not btc_ok or not pair_bear(frames[pair], idxs[pair])) and gross < -0.01:
                close_position(state, c, pair, price, "paper_regime_failure")


def write_hourly_diagnostics(
    closed_time: str,
    c: Candidate,
    pair: str,
    frame: pd.DataFrame,
    idx: int,
    btc_ok: bool,
    pair_ok: bool,
    breakout_ok: bool,
) -> None:
    r = frame.iloc[idx]
    prior = float(r[f"prior_low_{c.breakout_hours}"])
    distance = ((float(r["close"]) / prior) - 1.0) * 100.0 if prior else 0.0
    with HOURLY_PATH.open("a", newline="") as fh:
        csv.writer(fh).writerow([
            closed_time, c.name, pair, btc_ok, pair_ok, breakout_ok,
            btc_ok and pair_ok and breakout_ok, float(r["close"]),
            float(r["ret24"])*100.0, float(r["ret72"])*100.0,
            float(r["ret168"])*100.0, float(r["rsi14"]),
            float(r["vol_ratio"]), float(r["atr_pct"])*100.0, distance,
        ])


def evaluate_new_closed_hour(
    exchange: ccxt.Exchange,
    state: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    idxs: dict[str, int],
) -> None:
    btc_frame = frames["BTC/USD"]
    btc_idx = idxs["BTC/USD"]
    closed_ms = int(btc_frame.iloc[btc_idx]["ts"])
    closed_time = pd.to_datetime(closed_ms, unit="ms", utc=True).isoformat()

    if state["last_processed_closed_ms"] is None:
        state["last_processed_closed_ms"] = closed_ms
        log("forward boundary initialized; no historical signals backfilled")
        return
    if closed_ms <= int(state["last_processed_closed_ms"]):
        return

    hour_open_ms = closed_ms + 3600_000
    age_minutes = (int(time.time()*1000) - hour_open_ms) / 60_000.0
    state["last_processed_closed_ms"] = closed_ms

    btc_ok = btc_bear(btc_frame, btc_idx)
    for c in CANDIDATES:
        cs = state["candidates"][c.name]
        cs["hours_evaluated"] = int(cs["hours_evaluated"]) + 1
        signals = []
        for pair in PAIRS:
            po = pair_bear(frames[pair], idxs[pair])
            bo = breakdown(frames[pair], idxs[pair], c.breakout_hours)
            write_hourly_diagnostics(
                closed_time, c, pair, frames[pair], idxs[pair], btc_ok, po, bo
            )
            if btc_ok and po and bo:
                r = frames[pair].iloc[idxs[pair]]
                score = abs(float(r["ret168"])) + abs(float(r["ret72"])) + float(r["atr_pct"])
                signals.append((score, pair))

        if not signals:
            cs["no_signal_hours"] = int(cs["no_signal_hours"]) + 1
            continue

        cs["signals"] = int(cs["signals"]) + len(signals)
        if age_minutes > ENTRY_GRACE_MINUTES:
            log(
                f"{c.name} fresh signals={len(signals)} but entry window stale "
                f"age_minutes={age_minutes:.1f}; no simulated fill"
            )
            continue

        slots = MAX_OPEN - len(cs["positions"])
        if slots <= 0:
            continue

        signals.sort(reverse=True)
        for _, pair in signals:
            if slots <= 0:
                break
            if pair in cs["positions"] or cooldown_active(cs, pair, c.cooldown_hours):
                continue
            ticker = exchange.fetch_ticker(pair)
            price = float(ticker.get("last") or ticker.get("close"))
            stake = min(STAKE, max(float(cs["balance"]), 0.0))
            cs["positions"][pair] = {
                "entry_time": utcnow().isoformat(),
                "entry_price": price,
                "stake": stake,
                "target_price": price * (1.0 - c.target_gross),
                "stop_price": price * (1.0 + c.stop_gross),
            }
            slots -= 1
            log(
                f"{c.name} OPEN {pair} PAPER_SHORT entry={price:.8f} "
                f"stake_usd={stake:.2f} target={price*(1-c.target_gross):.8f} "
                f"stop={price*(1+c.stop_gross):.8f}"
            )


def mark_to_market(
    exchange: ccxt.Exchange,
    state: dict[str, Any],
) -> dict[str, Any]:
    price_cache = {}
    summary = {
        "timestamp": utcnow().isoformat(),
        "status": state["status"],
        "cycles": state["cycles"],
        "last_heartbeat": state["last_heartbeat"],
        "candidates": {},
    }
    for c in CANDIDATES:
        cs = state["candidates"][c.name]
        unrealized = 0.0
        open_rows = []
        for pair, pos in cs["positions"].items():
            if pair not in price_cache:
                ticker = exchange.fetch_ticker(pair)
                price_cache[pair] = float(ticker.get("last") or ticker.get("close"))
            price = price_cache[pair]
            gross = short_gross(float(pos["entry_price"]), price)
            net = gross - FRICTION
            pnl = float(pos["stake"]) * net
            unrealized += pnl
            open_rows.append({
                "pair": pair,
                "entry_price": pos["entry_price"],
                "mark_price": price,
                "net_return_pct": round(net*100.0, 4),
                "unrealized_pnl_usd": round(pnl, 6),
                "target_price": pos["target_price"],
                "stop_price": pos["stop_price"],
            })
        summary["candidates"][c.name] = {
            "realized_balance": round(float(cs["balance"]), 6),
            "realized_pnl_usd": round(float(cs["realized_pnl"]), 6),
            "unrealized_pnl_usd": round(unrealized, 6),
            "marked_equity": round(float(cs["balance"]) + unrealized, 6),
            "closed_trades": int(cs["closed_trades"]),
            "signals": int(cs["signals"]),
            "hours_evaluated": int(cs["hours_evaluated"]),
            "no_signal_hours": int(cs["no_signal_hours"]),
            "max_closed_drawdown_pct": round(float(cs["max_closed_drawdown_pct"]), 4),
            "open_positions": open_rows,
        }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> int:
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    ensure_csvs()
    state = load_state()

    exchange = ccxt.kraken({"enableRateLimit": True, "timeout": 30000})
    exchange.load_markets()
    missing = [p for p in PAIRS if p not in exchange.symbols]
    if missing:
        raise SystemExit(f"Kraken public symbols unavailable: {missing}")

    log(
        "START forward lab | public Kraken only | "
        f"candidates={','.join(c.name for c in CANDIDATES)} | "
        f"poll_seconds={POLL_SECONDS}"
    )

    while RUNNING:
        try:
            now_ms = int(time.time() * 1000)
            frames = fetch_frames(exchange)
            idxs = {pair: closed_index(f, now_ms) for pair, f in frames.items()}
            manage_open_positions(exchange, state, frames, idxs)
            evaluate_new_closed_hour(exchange, state, frames, idxs)
            state["cycles"] = int(state["cycles"]) + 1
            state["last_heartbeat"] = utcnow().isoformat()
            state["status"] = "RUNNING"
            save_state(state)
            mark_to_market(exchange, state)
        except Exception as exc:
            state["last_heartbeat"] = utcnow().isoformat()
            state["last_error"] = repr(exc)
            save_state(state)
            log(f"ERROR {type(exc).__name__}: {exc}")

        for _ in range(POLL_SECONDS):
            if not RUNNING:
                break
            time.sleep(1)

    state["status"] = "STOPPED_BY_SIGNAL"
    state["last_heartbeat"] = utcnow().isoformat()
    save_state(state)
    try:
        mark_to_market(exchange, state)
    except Exception:
        pass
    log("STOP forward lab")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
