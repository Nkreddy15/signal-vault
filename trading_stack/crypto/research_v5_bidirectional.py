"""Signal Vault V5 bidirectional research engine.

Offline research simulator for deciding whether a long/short/no-trade regime
approach is worth porting to Freqtrade futures PAPER mode.

Signals use completed 1h candles. Entries occur at the next candle open.
If target and stop are both touched in one candle, stop wins. Every trade pays
a fixed 0.74% round-trip friction deduction. No leverage or funding benefit is
assumed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "ADA/USD")
STARTING_BALANCE = 100.0
STAKE = 15.0
MAX_OPEN_TRADES = 4
ROUND_TRIP_FRICTION = 0.0074
TARGET_GROSS = 0.035
STOP_GROSS = 0.012
REGIME_EXIT_GROSS_FLOOR = -0.004
MAX_HOLD_HOURS = 96


@dataclass
class Position:
    pair: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    stake: float


@dataclass
class Trade:
    pair: str
    side: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    gross_return: float
    net_return: float
    pnl_usd: float
    reason: str
    hold_hours: float


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = frame["close"].shift(1)
    tr = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def load_pair(dirs: Iterable[Path], pair: str) -> pd.DataFrame:
    name = pair.replace("/", "_") + "-1h.feather"
    parts = []
    for directory in dirs:
        path = directory / name
        if not path.exists():
            raise FileNotFoundError(f"Missing research data: {path}")
        part = pd.read_feather(path)
        part["date"] = pd.to_datetime(part["date"], utc=True)
        parts.append(part)
    frame = (
        pd.concat(parts, ignore_index=True)
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )
    if frame.empty:
        raise RuntimeError(f"No candles loaded for {pair}")
    return frame


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    volume = frame["volume"]

    frame["ema20"] = close.ewm(span=20, adjust=False).mean()
    frame["ema50"] = close.ewm(span=50, adjust=False).mean()
    frame["ema200"] = close.ewm(span=200, adjust=False).mean()
    frame["ema50_slope12"] = frame["ema50"].pct_change(12)
    frame["ema200_slope24"] = frame["ema200"].pct_change(24)
    frame["ret3"] = close.pct_change(3)
    frame["ret24"] = close.pct_change(24)
    frame["ret72"] = close.pct_change(72)
    frame["ret168"] = close.pct_change(168)
    frame["rsi14"] = rsi(close)
    frame["atr14"] = atr(frame)
    frame["atr_pct"] = frame["atr14"] / close
    frame["move_capacity"] = frame["atr_pct"] * 4.0
    frame["vol_mean20"] = volume.rolling(20).mean()
    frame["vol_ratio"] = volume / frame["vol_mean20"].replace(0.0, float("nan"))
    frame["recent_long_pullback"] = low.rolling(6).min() <= frame["ema20"] * 1.004
    frame["recent_short_retrace"] = high.rolling(6).max() >= frame["ema20"] * 0.996
    frame["prior_high3"] = high.rolling(3).max().shift(1)
    frame["prior_low3"] = low.rolling(3).min().shift(1)
    return frame


def prepare_dataset(dirs: Iterable[Path]) -> Dict[str, pd.DataFrame]:
    frames = {pair: add_indicators(load_pair(dirs, pair)) for pair in PAIRS}
    btc = frames["BTC/USD"][
        ["date", "close", "ema50", "ema200", "ema200_slope24", "ret24", "ret168"]
    ].copy()
    btc.columns = [
        "date", "btc_close", "btc_ema50", "btc_ema200",
        "btc_ema200_slope24", "btc_ret24", "btc_ret168",
    ]

    for pair in PAIRS:
        frame = frames[pair].merge(btc, on="date", how="left")
        btc_bull = (
            (frame["btc_close"] > frame["btc_ema200"])
            & (frame["btc_ema50"] > frame["btc_ema200"])
            & (frame["btc_ema200_slope24"] > 0.0005)
            & (frame["btc_ret168"] > 0.015)
            & (frame["btc_ret24"] > -0.015)
        )
        btc_bear = (
            (frame["btc_close"] < frame["btc_ema200"])
            & (frame["btc_ema50"] < frame["btc_ema200"])
            & (frame["btc_ema200_slope24"] < -0.0005)
            & (frame["btc_ret168"] < -0.015)
            & (frame["btc_ret24"] < 0.015)
        )

        long_regime = (
            btc_bull
            & (frame["close"] > frame["ema200"] * 1.005)
            & (frame["ema20"] > frame["ema50"])
            & (frame["ema50"] > frame["ema200"])
            & (frame["ema50_slope12"] > 0.0015)
            & (frame["ema200_slope24"] > 0.0)
            & (frame["ret72"] > 0.005)
            & (frame["ret168"] > 0.015)
        )
        short_regime = (
            btc_bear
            & (frame["close"] < frame["ema200"] * 0.995)
            & (frame["ema20"] < frame["ema50"])
            & (frame["ema50"] < frame["ema200"])
            & (frame["ema50_slope12"] < -0.0015)
            & (frame["ema200_slope24"] < 0.0)
            & (frame["ret72"] < -0.005)
            & (frame["ret168"] < -0.015)
        )

        long_trigger = (
            frame["recent_long_pullback"]
            & (frame["close"] > frame["ema20"])
            & (frame["close"] > frame["prior_high3"])
            & (frame["ret3"] > 0.002)
            & (frame["ret24"] > 0.008)
            & frame["rsi14"].between(52, 68)
            & (frame["vol_ratio"] >= 0.80)
        )
        short_trigger = (
            frame["recent_short_retrace"]
            & (frame["close"] < frame["ema20"])
            & (frame["close"] < frame["prior_low3"])
            & (frame["ret3"] < -0.002)
            & (frame["ret24"] < -0.008)
            & frame["rsi14"].between(32, 48)
            & (frame["vol_ratio"] >= 0.80)
        )

        capacity = frame["move_capacity"] >= 0.025
        frame["long_signal"] = long_regime & long_trigger & capacity & (frame["volume"] > 0)
        frame["short_signal"] = short_regime & short_trigger & capacity & (frame["volume"] > 0)
        frame["btc_bull"] = btc_bull
        frame["btc_bear"] = btc_bear
        frame["signal_score"] = (
            frame["ret72"].abs().fillna(0.0)
            + frame["ret168"].abs().fillna(0.0)
            + frame["atr_pct"].fillna(0.0)
        )
        frames[pair] = frame.set_index("date", drop=False)
    return frames


def gross_return(side: str, entry: float, exit_price: float) -> float:
    if side == "long":
        return (exit_price / entry) - 1.0
    return (entry - exit_price) / entry


def close_trade(position: Position, exit_time: pd.Timestamp, exit_price: float, reason: str) -> Trade:
    gross = gross_return(position.side, position.entry_price, exit_price)
    net = gross - ROUND_TRIP_FRICTION
    pnl = position.stake * net
    hold = (exit_time - position.entry_time).total_seconds() / 3600.0
    return Trade(
        pair=position.pair,
        side=position.side,
        entry_time=position.entry_time.isoformat(),
        exit_time=exit_time.isoformat(),
        entry_price=position.entry_price,
        exit_price=float(exit_price),
        gross_return=gross,
        net_return=net,
        pnl_usd=pnl,
        reason=reason,
        hold_hours=hold,
    )


def run_backtest(frames: Dict[str, pd.DataFrame], label: str) -> dict:
    all_dates = sorted(set().union(*(set(df.index) for df in frames.values())))
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    balance = STARTING_BALANCE
    peak_balance = balance
    max_drawdown = 0.0

    for date in all_dates:
        for pair in list(positions):
            frame = frames[pair]
            if date not in frame.index:
                continue
            loc = frame.index.get_loc(date)
            if isinstance(loc, slice) or loc == 0:
                continue
            row = frame.iloc[loc]
            prev = frame.iloc[loc - 1]
            pos = positions[pair]
            current_open = float(row["open"])
            mark_gross = gross_return(pos.side, pos.entry_price, current_open)
            age_hours = (date - pos.entry_time).total_seconds() / 3600.0

            structural_exit = False
            reason = ""
            if pos.side == "long":
                risk_off = not bool(prev["btc_bull"])
                pair_fail = float(prev["close"]) < float(prev["ema50"]) and float(prev["ret24"]) <= 0.0
                if (risk_off or pair_fail) and mark_gross <= REGIME_EXIT_GROSS_FLOOR:
                    structural_exit = True
                    reason = "long_regime_failure"
            else:
                risk_off = not bool(prev["btc_bear"])
                pair_fail = float(prev["close"]) > float(prev["ema50"]) and float(prev["ret24"]) >= 0.0
                if (risk_off or pair_fail) and mark_gross <= REGIME_EXIT_GROSS_FLOOR:
                    structural_exit = True
                    reason = "short_regime_failure"

            if age_hours >= MAX_HOLD_HOURS and not structural_exit:
                if mark_gross > ROUND_TRIP_FRICTION:
                    structural_exit = True
                    reason = "time_profit_exit"
                elif abs(mark_gross) <= ROUND_TRIP_FRICTION:
                    structural_exit = True
                    reason = "time_stale_exit"

            if structural_exit:
                trade = close_trade(pos, date, current_open, reason)
                trades.append(trade)
                balance += trade.pnl_usd
                del positions[pair]

        for pair in list(positions):
            frame = frames[pair]
            if date not in frame.index:
                continue
            row = frame.loc[date]
            pos = positions[pair]
            high = float(row["high"])
            low = float(row["low"])
            if pos.side == "long":
                stop_price = pos.entry_price * (1.0 - STOP_GROSS)
                target_price = pos.entry_price * (1.0 + TARGET_GROSS)
                stop_hit = low <= stop_price
                target_hit = high >= target_price
            else:
                stop_price = pos.entry_price * (1.0 + STOP_GROSS)
                target_price = pos.entry_price * (1.0 - TARGET_GROSS)
                stop_hit = high >= stop_price
                target_hit = low <= target_price

            if stop_hit:
                trade = close_trade(pos, date, stop_price, "hard_stop")
                trades.append(trade)
                balance += trade.pnl_usd
                del positions[pair]
            elif target_hit:
                trade = close_trade(pos, date, target_price, "gross_target")
                trades.append(trade)
                balance += trade.pnl_usd
                del positions[pair]

        peak_balance = max(peak_balance, balance)
        if peak_balance > 0:
            max_drawdown = max(max_drawdown, (peak_balance - balance) / peak_balance)

        available = MAX_OPEN_TRADES - len(positions)
        if available <= 0:
            continue

        candidates: List[Tuple[float, str, str, float]] = []
        for pair, frame in frames.items():
            if pair in positions or date not in frame.index:
                continue
            loc = frame.index.get_loc(date)
            if isinstance(loc, slice) or loc == 0:
                continue
            row = frame.iloc[loc]
            prev = frame.iloc[loc - 1]
            side: Optional[str] = None
            if bool(prev["long_signal"]):
                side = "long"
            elif bool(prev["short_signal"]):
                side = "short"
            if side is None:
                continue
            candidates.append((float(prev["signal_score"]), pair, side, float(row["open"])))

        candidates.sort(reverse=True)
        for _, pair, side, entry_price in candidates[:available]:
            if balance <= 0:
                break
            stake = min(STAKE, max(balance, 0.0))
            if stake <= 0:
                break
            positions[pair] = Position(pair, side, date, entry_price, stake)

    for pair in list(positions):
        pos = positions[pair]
        row = frames[pair].iloc[-1]
        trade = close_trade(pos, pd.Timestamp(row["date"]), float(row["close"]), "end_of_period")
        trades.append(trade)
        balance += trade.pnl_usd
        del positions[pair]

    peak_balance = max(peak_balance, balance)
    if peak_balance > 0:
        max_drawdown = max(max_drawdown, (peak_balance - balance) / peak_balance)

    tdf = pd.DataFrame([asdict(t) for t in trades])
    if tdf.empty:
        return {
            "label": label, "trades": 0, "net_pnl_usd": 0.0, "return_pct": 0.0,
            "profit_factor": 0.0, "expectancy_usd": 0.0, "win_rate_pct": 0.0,
            "max_closed_drawdown_pct": max_drawdown * 100.0,
            "by_side": {}, "by_pair": {}, "by_month": {}, "exit_reasons": {},
            "trade_rows": [],
        }

    wins = tdf[tdf["pnl_usd"] > 0]
    losses = tdf[tdf["pnl_usd"] < 0]
    gross_profit = float(wins["pnl_usd"].sum())
    gross_loss = float(-losses["pnl_usd"].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    tdf["exit_month"] = pd.to_datetime(tdf["exit_time"], utc=True).dt.strftime("%Y-%m")

    def group_stats(group: pd.DataFrame) -> dict:
        return {
            "trades": int(len(group)),
            "pnl_usd": round(float(group["pnl_usd"].sum()), 6),
            "avg_net_return_pct": round(float(group["net_return"].mean() * 100.0), 4),
            "win_rate_pct": round(float((group["pnl_usd"] > 0).mean() * 100.0), 2),
        }

    return {
        "label": label,
        "trades": int(len(tdf)),
        "net_pnl_usd": round(float(tdf["pnl_usd"].sum()), 6),
        "ending_balance": round(float(balance), 6),
        "return_pct": round((balance / STARTING_BALANCE - 1.0) * 100.0, 4),
        "profit_factor": round(float(pf), 4) if pd.notna(pf) else None,
        "expectancy_usd": round(float(tdf["pnl_usd"].mean()), 6),
        "win_rate_pct": round(float((tdf["pnl_usd"] > 0).mean() * 100.0), 2),
        "max_closed_drawdown_pct": round(max_drawdown * 100.0, 4),
        "avg_hold_hours": round(float(tdf["hold_hours"].mean()), 2),
        "by_side": {key: group_stats(group) for key, group in tdf.groupby("side", sort=True)},
        "by_pair": {key: group_stats(group) for key, group in tdf.groupby("pair", sort=True)},
        "by_month": {key: group_stats(group) for key, group in tdf.groupby("exit_month", sort=True)},
        "exit_reasons": {key: group_stats(group) for key, group in tdf.groupby("reason", sort=True)},
        "trade_rows": tdf.drop(columns=["exit_month"]).to_dict(orient="records"),
    }


def print_summary(result: dict) -> None:
    print()
    print(f"=== {result['label']} ===")
    print(
        f"trades={result['trades']}  return={result['return_pct']:.2f}%  "
        f"net_pnl=${result['net_pnl_usd']:.3f}  profit_factor={result['profit_factor']}  "
        f"expectancy=${result['expectancy_usd']:.4f}  win_rate={result['win_rate_pct']:.1f}%  "
        f"max_closed_dd={result['max_closed_drawdown_pct']:.2f}%"
    )
    for heading in ("by_side", "by_pair", "by_month", "exit_reasons"):
        print(heading.replace("_", " ") + ":")
        for key, stats in result[heading].items():
            print(f"  {key}: {stats}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--development-dir", action="append", required=True)
    parser.add_argument("--holdout-dir", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    dev_dirs = [Path(x) for x in args.development_dir]
    holdout_dirs = [Path(x) for x in args.holdout_dir]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    development = run_backtest(prepare_dataset(dev_dirs), "V5 DEVELOPMENT 2026-H1")
    holdout = run_backtest(prepare_dataset(holdout_dirs), "V5 HOLDOUT 2025-Q4")
    print_summary(development)
    print_summary(holdout)

    payload = {
        "assumptions": {
            "starting_balance_usd": STARTING_BALANCE,
            "stake_usd": STAKE,
            "max_open_trades": MAX_OPEN_TRADES,
            "round_trip_friction_pct": ROUND_TRIP_FRICTION * 100.0,
            "gross_target_pct": TARGET_GROSS * 100.0,
            "gross_stop_pct": STOP_GROSS * 100.0,
            "leverage": 1.0,
            "funding_cost_modeled": False,
            "same_candle_target_stop_policy": "stop_first",
            "entry_timing": "next_candle_open",
        },
        "development": development,
        "holdout": holdout,
    }
    output_path = output_dir / "v5-bidirectional-results.json"
    output_path.write_text(json.dumps(payload, indent=2, default=str))
    print()
    print(f"Saved: {output_path}")
    print("Research only. Do not treat a passing backtest as trading authorization.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
