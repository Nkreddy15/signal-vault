"""Signal Vault V8 overnight PAPER observer.

Forward-only, no-order simulator for the current best V8 research candidate:
short-only, 1h candles, 72h downside breakout, 12% gross target, 4% gross
stop, 24h cooldown, BTC+pair bearish alignment, 0.74% modeled round-trip
friction, $15 paper stake, $100 logical wallet, max 3 positions.

Public Kraken market data only. This file never submits an exchange order.
"""

from __future__ import annotations

import csv
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ccxt
import pandas as pd


PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "ADA/USD")
STATE_DIR = Path(os.getenv("V8_STATE_DIR", "/freqtrade/data/v8-overnight"))
STATE_PATH = STATE_DIR / "state.json"
TRADES_PATH = STATE_DIR / "trades.csv"
EVENTS_PATH = STATE_DIR / "events.log"

STARTING_BALANCE = float(os.getenv("V8_STARTING_BALANCE", "100"))
STAKE = float(os.getenv("V8_STAKE_USD", "15"))
MAX_OPEN = int(os.getenv("V8_MAX_OPEN_TRADES", "3"))
FRICTION = float(os.getenv("V8_ROUND_TRIP_FRICTION", "0.0074"))
TARGET = float(os.getenv("V8_TARGET_GROSS", "0.12"))
STOP = float(os.getenv("V8_STOP_GROSS", "0.04"))
COOLDOWN_HOURS = int(os.getenv("V8_COOLDOWN_HOURS", "24"))
MAX_HOLD_HOURS = int(os.getenv("V8_MAX_HOLD_HOURS", "240"))
POLL_SECONDS = int(os.getenv("V8_POLL_SECONDS", "60"))
OVERNIGHT_HOURS = float(os.getenv("V8_OVERNIGHT_HOURS", "8"))
ENTRY_GRACE_MINUTES = int(os.getenv("V8_ENTRY_GRACE_MINUTES", "10"))
RUNNING = True


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat()} {message}"
    print(line, flush=True)
    with EVENTS_PATH.open("a") as fh:
        fh.write(line + "\n")


def handle_stop(signum, frame) -> None:
    global RUNNING
    RUNNING = False
    log(f"stop requested signal={signum}")


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)


def default_state() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "version": "V8-OVERNIGHT-PAPER-1",
        "started_at": now.isoformat(),
        "stop_at_epoch": time.time() + OVERNIGHT_HOURS * 3600.0,
        "balance": STARTING_BALANCE,
        "positions": {},
        "cooldowns": {},
        "last_processed_closed_ms": None,
        "last_heartbeat": now.isoformat(),
        "cycles": 0,
        "status": "RUNNING",
    }


def load_state() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        state = default_state()
    else:
        state = json.loads(STATE_PATH.read_text())
        state["stop_at_epoch"] = time.time() + OVERNIGHT_HOURS * 3600.0
        state["status"] = "RUNNING"
        state["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return state


def ensure_trade_csv() -> None:
    if TRADES_PATH.exists():
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with TRADES_PATH.open("w", newline="") as fh:
        csv.writer(fh).writerow([
            "exit_time_utc", "pair", "side", "entry_time_utc", "entry_price",
            "exit_price", "gross_return_pct", "net_return_pct", "pnl_usd",
            "reason", "hold_hours",
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
    f["prior_low72"] = f["low"].rolling(72).min().shift(1)
    return f


def fetch_frames(exchange: ccxt.Exchange) -> dict[str, pd.DataFrame]:
    frames = {}
    for pair in PAIRS:
        rows = exchange.fetch_ohlcv(pair, timeframe="1h", limit=260)
        if not rows or len(rows) < 220:
            raise RuntimeError(f"{pair}: insufficient 1h candles")
        frame = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        frame["date"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
        frames[pair] = add_indicators(frame)
    return frames


def closed_index(frame: pd.DataFrame, now_ms: int) -> int:
    eligible = frame.index[frame["ts"] <= now_ms - 3600_000]
    if len(eligible) == 0:
        raise RuntimeError("no fully closed candle available")
    return int(eligible[-1])


def pair_bearish(frame: pd.DataFrame, idx: int) -> bool:
    r = frame.iloc[idx]
    return (
        float(r["close"]) < float(r["ema100"])
        and float(r["ema20"]) < float(r["ema50"])
        and float(r["ema50"]) < float(r["ema100"])
        and float(r["ema100_slope24"]) < 0.0
        and float(r["ret72"]) < -0.02
    )


def breakdown_signal(frame: pd.DataFrame, idx: int) -> bool:
    r = frame.iloc[idx]
    return (
        float(r["close"]) < float(r["prior_low72"])
        and float(r["ret24"]) < -0.015
        and 26 <= float(r["rsi14"]) <= 45
        and float(r["vol_ratio"]) >= 1.15
        and float(r["atr_pct"]) >= 0.008
    )


def btc_bearish(frame: pd.DataFrame, idx: int) -> bool:
    r = frame.iloc[idx]
    return (
        float(r["close"]) < float(r["ema100"])
        and float(r["ema20"]) < float(r["ema50"])
        and float(r["ema50"]) < float(r["ema100"])
        and float(r["ema100_slope24"]) < -0.001
        and float(r["ret72"]) < -0.02
        and float(r["ret168"]) < -0.04
    )


def short_gross(entry: float, price: float) -> float:
    return (entry - price) / entry


def record_close(state: dict[str, Any], pair: str, price: float, reason: str) -> None:
    pos = state["positions"][pair]
    gross = short_gross(float(pos["entry_price"]), price)
    net = gross - FRICTION
    pnl = float(pos["stake"]) * net
    now = datetime.now(timezone.utc)
    entered = datetime.fromisoformat(pos["entry_time"])
    hold = (now - entered).total_seconds() / 3600.0
    state["balance"] = float(state["balance"]) + pnl
    state["cooldowns"][pair] = now.isoformat()
    del state["positions"][pair]

    ensure_trade_csv()
    with TRADES_PATH.open("a", newline="") as fh:
        csv.writer(fh).writerow([
            now.isoformat(), pair, "SHORT", pos["entry_time"], pos["entry_price"],
            price, gross * 100.0, net * 100.0, pnl, reason, hold,
        ])
    log(
        f"CLOSE {pair} SHORT reason={reason} price={price:.8f} "
        f"gross={gross*100:.3f}% net={net*100:.3f}% "
        f"pnl_usd={pnl:.4f} balance_usd={state['balance']:.4f}"
    )


def cooldown_active(state: dict[str, Any], pair: str) -> bool:
    value = state["cooldowns"].get(pair)
    if not value:
        return False
    last = datetime.fromisoformat(value)
    return (datetime.now(timezone.utc) - last).total_seconds() < COOLDOWN_HOURS * 3600


def manage_positions(
    exchange: ccxt.Exchange,
    state: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    idxs: dict[str, int],
) -> None:
    btc_ok = btc_bearish(frames["BTC/USD"], idxs["BTC/USD"])
    for pair in list(state["positions"]):
        ticker = exchange.fetch_ticker(pair)
        price = float(ticker.get("last") or ticker.get("close"))
        pos = state["positions"][pair]
        entry = float(pos["entry_price"])
        gross = short_gross(entry, price)

        if price >= entry * (1.0 + STOP):
            record_close(state, pair, price, "paper_hard_stop")
            continue
        if price <= entry * (1.0 - TARGET):
            record_close(state, pair, price, "paper_gross_target")
            continue

        entered = datetime.fromisoformat(pos["entry_time"])
        held = (datetime.now(timezone.utc) - entered).total_seconds() / 3600.0
        if held >= MAX_HOLD_HOURS:
            record_close(state, pair, price, "paper_time_exit")
            continue
        if (not btc_ok or not pair_bearish(frames[pair], idxs[pair])) and gross < -0.01:
            record_close(state, pair, price, "paper_regime_failure")


def evaluate_new_hour(
    exchange: ccxt.Exchange,
    state: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    idxs: dict[str, int],
) -> None:
    btc_idx = idxs["BTC/USD"]
    btc_frame = frames["BTC/USD"]
    closed_ms = int(btc_frame.iloc[btc_idx]["ts"])

    if state["last_processed_closed_ms"] is None:
        state["last_processed_closed_ms"] = closed_ms
        log("forward boundary initialized; historical signals will not be backfilled")
        return

    if closed_ms <= int(state["last_processed_closed_ms"]):
        return

    current_hour_open_ms = closed_ms + 3600_000
    age_minutes = (int(time.time() * 1000) - current_hour_open_ms) / 60_000.0
    state["last_processed_closed_ms"] = closed_ms
    if age_minutes > ENTRY_GRACE_MINUTES:
        log(f"new candle detected but entry window stale age_minutes={age_minutes:.1f}; skip")
        return

    if not btc_bearish(btc_frame, btc_idx):
        log("new hour: BTC bear regime false -> no new paper shorts")
        return

    slots = MAX_OPEN - len(state["positions"])
    if slots <= 0:
        log("new hour: max paper positions already open")
        return

    choices = []
    for pair in PAIRS:
        if pair in state["positions"] or cooldown_active(state, pair):
            continue
        if not pair_bearish(frames[pair], idxs[pair]):
            continue
        if not breakdown_signal(frames[pair], idxs[pair]):
            continue
        row = frames[pair].iloc[idxs[pair]]
        score = abs(float(row["ret168"])) + abs(float(row["ret72"])) + float(row["atr_pct"])
        choices.append((score, pair))

    choices.sort(reverse=True)
    if not choices:
        log("new hour: no V8 short breakout signal")
        return

    for _, pair in choices[:slots]:
        ticker = exchange.fetch_ticker(pair)
        price = float(ticker.get("last") or ticker.get("close"))
        now = datetime.now(timezone.utc)
        stake = min(STAKE, max(float(state["balance"]), 0.0))
        state["positions"][pair] = {
            "side": "SHORT",
            "entry_time": now.isoformat(),
            "entry_price": price,
            "stake": stake,
            "target_price": price * (1.0 - TARGET),
            "stop_price": price * (1.0 + STOP),
        }
        log(
            f"OPEN {pair} PAPER SHORT price={price:.8f} stake_usd={stake:.2f} "
            f"target={price*(1-TARGET):.8f} stop={price*(1+STOP):.8f}"
        )


def main() -> int:
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    ensure_trade_csv()
    state = load_state()

    exchange = ccxt.kraken({"enableRateLimit": True, "timeout": 30000})
    exchange.load_markets()
    missing = [p for p in PAIRS if p not in exchange.symbols]
    if missing:
        raise SystemExit(f"Kraken public market symbols missing: {missing}")

    log(
        f"START V8 overnight PAPER duration_hours={OVERNIGHT_HOURS} "
        f"poll_seconds={POLL_SECONDS} target_pct={TARGET*100:.1f} "
        f"stop_pct={STOP*100:.1f} friction_pct={FRICTION*100:.2f} "
        f"max_open={MAX_OPEN}"
    )

    while RUNNING and time.time() < float(state["stop_at_epoch"]):
        try:
            now_ms = int(time.time() * 1000)
            frames = fetch_frames(exchange)
            idxs = {pair: closed_index(frame, now_ms) for pair, frame in frames.items()}
            manage_positions(exchange, state, frames, idxs)
            evaluate_new_hour(exchange, state, frames, idxs)
            state["cycles"] = int(state.get("cycles", 0)) + 1
            state["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
            state["status"] = "RUNNING"
            save_state(state)
        except Exception as exc:
            state["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
            state["last_error"] = repr(exc)
            save_state(state)
            log(f"ERROR {type(exc).__name__}: {exc}")

        for _ in range(POLL_SECONDS):
            if not RUNNING or time.time() >= float(state["stop_at_epoch"]):
                break
            time.sleep(1)

    state["status"] = "STOPPED_AFTER_OVERNIGHT_WINDOW" if RUNNING else "STOPPED_BY_SIGNAL"
    state["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    log(
        f"STOP V8 overnight PAPER status={state['status']} "
        f"balance_usd={float(state['balance']):.4f} "
        f"open_positions={len(state['positions'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
