"""Signal Vault V6 strategy-family tournament.

V6 stops hand-tuning one strategy at a time. It evaluates a small, predeclared
set of long/short strategy families on 2026 H1 development data using the same
conservative execution assumptions, and only consumes the 2025 Q3 holdout if a
candidate clears the development gate.

Research only. No broker/exchange orders are submitted.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD", "ADA/USD")
STARTING_BALANCE = 100.0
STAKE = 15.0
MAX_OPEN_TRADES = 4
ROUND_TRIP_FRICTION = 0.0074


@dataclass(frozen=True)
class Candidate:
    name: str
    timeframe_hours: int
    family: str
    strict: bool
    target_gross: float
    stop_gross: float
    min_capacity: float
    max_hold_bars: int


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


def candidate_grid() -> list[Candidate]:
    out: list[Candidate] = []
    for timeframe_hours in (1, 4):
        for family in ("trend_momentum", "breakout", "pullback"):
            for strict in (False, True):
                for target, stop in ((0.05, 0.02), (0.07, 0.025)):
                    name = (
                        f"{timeframe_hours}h-{family}-"
                        f"{'strict' if strict else 'base'}-"
                        f"t{int(target*1000)}-s{int(stop*1000)}"
                    )
                    out.append(
                        Candidate(
                            name=name,
                            timeframe_hours=timeframe_hours,
                            family=family,
                            strict=strict,
                            target_gross=target,
                            stop_gross=stop,
                            min_capacity=0.03 if strict else 0.025,
                            max_hold_bars=18 if timeframe_hours == 4 else 72,
                        )
                    )
    return out


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
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


def _load_1h(dirs: Iterable[Path], pair: str) -> pd.DataFrame:
    filename = pair.replace("/", "_") + "-1h.feather"
    parts = []
    for directory in dirs:
        path = directory / filename
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
    return frame[["date", "open", "high", "low", "close", "volume"]]


def _resample(frame: pd.DataFrame, hours: int) -> pd.DataFrame:
    if hours == 1:
        return frame.copy()
    out = (
        frame.set_index("date")
        .resample(f"{hours}h", label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return out


def _add_indicators(frame: pd.DataFrame, hours: int) -> pd.DataFrame:
    frame = frame.copy()
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    volume = frame["volume"]

    bars6 = max(1, round(6 / hours))
    bars24 = max(2, round(24 / hours))
    bars72 = max(3, round(72 / hours))
    bars168 = max(4, round(168 / hours))

    frame["ema20"] = close.ewm(span=20, adjust=False).mean()
    frame["ema50"] = close.ewm(span=50, adjust=False).mean()
    frame["ema100"] = close.ewm(span=100, adjust=False).mean()
    frame["ema50_slope6"] = frame["ema50"].pct_change(6)
    frame["ema100_slope6"] = frame["ema100"].pct_change(6)
    frame["ret6h"] = close.pct_change(bars6)
    frame["ret24h"] = close.pct_change(bars24)
    frame["ret72h"] = close.pct_change(bars72)
    frame["ret168h"] = close.pct_change(bars168)
    frame["rsi14"] = _rsi(close)
    frame["atr14"] = _atr(frame)
    frame["atr_pct"] = frame["atr14"] / close
    frame["move_capacity"] = frame["atr_pct"] * 4.0
    frame["vol_mean20"] = volume.rolling(20).mean()
    frame["vol_ratio"] = volume / frame["vol_mean20"].replace(0.0, float("nan"))
    frame["prior_high20"] = high.rolling(20).max().shift(1)
    frame["prior_low20"] = low.rolling(20).min().shift(1)
    frame["recent_pullback"] = low.rolling(5).min() <= frame["ema20"] * 1.005
    frame["recent_retrace"] = high.rolling(5).max() >= frame["ema20"] * 0.995
    return frame


def _prepare_frames(
    dirs: Iterable[Path],
    candidate: Candidate,
) -> Dict[str, pd.DataFrame]:
    frames = {
        pair: _add_indicators(
            _resample(_load_1h(dirs, pair), candidate.timeframe_hours),
            candidate.timeframe_hours,
        )
        for pair in PAIRS
    }

    btc = frames["BTC/USD"][
        [
            "date", "close", "ema20", "ema50", "ema100",
            "ema100_slope6", "ret24h", "ret72h", "ret168h",
        ]
    ].copy()
    btc.columns = [
        "date", "btc_close", "btc_ema20", "btc_ema50", "btc_ema100",
        "btc_ema100_slope6", "btc_ret24h", "btc_ret72h", "btc_ret168h",
    ]

    for pair, base in list(frames.items()):
        frame = base.merge(btc, on="date", how="left")

        btc_bull = (
            (frame["btc_close"] > frame["btc_ema100"])
            & (frame["btc_ema20"] > frame["btc_ema50"])
            & (frame["btc_ema50"] > frame["btc_ema100"])
            & (frame["btc_ema100_slope6"] > 0.0)
            & (frame["btc_ret72h"] > (0.02 if candidate.strict else 0.005))
            & (frame["btc_ret168h"] > (0.04 if candidate.strict else 0.01))
        )
        btc_bear = (
            (frame["btc_close"] < frame["btc_ema100"])
            & (frame["btc_ema20"] < frame["btc_ema50"])
            & (frame["btc_ema50"] < frame["btc_ema100"])
            & (frame["btc_ema100_slope6"] < 0.0)
            & (frame["btc_ret72h"] < (-0.02 if candidate.strict else -0.005))
            & (frame["btc_ret168h"] < (-0.04 if candidate.strict else -0.01))
        )

        pair_bull = (
            (frame["close"] > frame["ema100"])
            & (frame["ema20"] > frame["ema50"])
            & (frame["ema50"] > frame["ema100"])
            & (frame["ema50_slope6"] > 0.0)
            & (frame["ret72h"] > (0.015 if candidate.strict else 0.0))
        )
        pair_bear = (
            (frame["close"] < frame["ema100"])
            & (frame["ema20"] < frame["ema50"])
            & (frame["ema50"] < frame["ema100"])
            & (frame["ema50_slope6"] < 0.0)
            & (frame["ret72h"] < (-0.015 if candidate.strict else 0.0))
        )

        vol_floor = 1.0 if candidate.strict else 0.80
        if candidate.family == "trend_momentum":
            long_trigger = (
                (frame["ret24h"] > (0.025 if candidate.strict else 0.012))
                & (frame["ret6h"] > 0.0)
                & frame["rsi14"].between(52, 70)
                & (frame["vol_ratio"] >= vol_floor)
            )
            short_trigger = (
                (frame["ret24h"] < (-0.025 if candidate.strict else -0.012))
                & (frame["ret6h"] < 0.0)
                & frame["rsi14"].between(30, 48)
                & (frame["vol_ratio"] >= vol_floor)
            )
        elif candidate.family == "breakout":
            long_trigger = (
                (frame["close"] > frame["prior_high20"])
                & (frame["ret24h"] > 0.0)
                & (frame["rsi14"] < 75)
                & (frame["vol_ratio"] >= (1.20 if candidate.strict else 1.0))
            )
            short_trigger = (
                (frame["close"] < frame["prior_low20"])
                & (frame["ret24h"] < 0.0)
                & (frame["rsi14"] > 25)
                & (frame["vol_ratio"] >= (1.20 if candidate.strict else 1.0))
            )
        else:
            long_trigger = (
                frame["recent_pullback"]
                & (frame["close"] > frame["ema20"])
                & (frame["ret6h"] > 0.0)
                & (frame["ret24h"] > (0.015 if candidate.strict else 0.006))
                & frame["rsi14"].between(50, 67)
                & (frame["vol_ratio"] >= vol_floor)
            )
            short_trigger = (
                frame["recent_retrace"]
                & (frame["close"] < frame["ema20"])
                & (frame["ret6h"] < 0.0)
                & (frame["ret24h"] < (-0.015 if candidate.strict else -0.006))
                & frame["rsi14"].between(33, 50)
                & (frame["vol_ratio"] >= vol_floor)
            )

        capacity = frame["move_capacity"] >= candidate.min_capacity
        frame["long_signal"] = (
            btc_bull & pair_bull & long_trigger & capacity & (frame["volume"] > 0)
        )
        frame["short_signal"] = (
            btc_bear & pair_bear & short_trigger & capacity & (frame["volume"] > 0)
        )
        frame["btc_bull"] = btc_bull
        frame["btc_bear"] = btc_bear
        frame["pair_bull"] = pair_bull
        frame["pair_bear"] = pair_bear
        frame["signal_score"] = (
            frame["ret72h"].abs().fillna(0.0)
            + frame["ret168h"].abs().fillna(0.0)
            + frame["atr_pct"].fillna(0.0)
        )
        frames[pair] = frame.set_index("date", drop=False)

    return frames


def _gross_return(side: str, entry: float, exit_price: float) -> float:
    if side == "long":
        return (exit_price / entry) - 1.0
    return (entry - exit_price) / entry


def _close_trade(
    pos: Position,
    exit_time: pd.Timestamp,
    exit_price: float,
    reason: str,
) -> Trade:
    gross = _gross_return(pos.side, pos.entry_price, exit_price)
    net = gross - ROUND_TRIP_FRICTION
    return Trade(
        pair=pos.pair,
        side=pos.side,
        entry_time=pos.entry_time.isoformat(),
        exit_time=exit_time.isoformat(),
        entry_price=pos.entry_price,
        exit_price=float(exit_price),
        gross_return=gross,
        net_return=net,
        pnl_usd=pos.stake * net,
        reason=reason,
        hold_hours=(exit_time - pos.entry_time).total_seconds() / 3600.0,
    )


def _simulate(frames: Dict[str, pd.DataFrame], c: Candidate, label: str) -> dict:
    all_dates = sorted(set().union(*(set(df.index) for df in frames.values())))
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    balance = STARTING_BALANCE
    peak = balance
    max_dd = 0.0

    for date in all_dates:
        # Exit carried positions at the new bar open if the completed previous
        # bar says the controlling regime has failed and the trade is already
        # adversely beyond half the modeled round-trip friction.
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
            open_price = float(row["open"])
            gross = _gross_return(pos.side, pos.entry_price, open_price)
            bars_held = int(round(
                (date - pos.entry_time).total_seconds()
                / (3600.0 * c.timeframe_hours)
            ))

            if pos.side == "long":
                regime_alive = bool(prev["btc_bull"]) and bool(prev["pair_bull"])
            else:
                regime_alive = bool(prev["btc_bear"]) and bool(prev["pair_bear"])

            reason: Optional[str] = None
            if not regime_alive and gross <= -(ROUND_TRIP_FRICTION / 2.0):
                reason = "regime_failure"
            elif bars_held >= c.max_hold_bars:
                reason = "time_exit"

            if reason is not None:
                tr = _close_trade(pos, date, open_price, reason)
                trades.append(tr)
                balance += tr.pnl_usd
                del positions[pair]

        # Signals are from the previous completed candle. Enter at this open.
        available = MAX_OPEN_TRADES - len(positions)
        if available > 0:
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
                if side:
                    candidates.append(
                        (float(prev["signal_score"]), pair, side, float(row["open"]))
                    )

            candidates.sort(reverse=True)
            for _, pair, side, entry_price in candidates[:available]:
                positions[pair] = Position(
                    pair=pair,
                    side=side,
                    entry_time=date,
                    entry_price=entry_price,
                    stake=min(STAKE, max(balance, 0.0)),
                )

        # Entry-candle and carried-position intrabar target/stop handling.
        # If both are touched in one bar, stop wins.
        for pair in list(positions):
            frame = frames[pair]
            if date not in frame.index:
                continue
            row = frame.loc[date]
            pos = positions[pair]
            high = float(row["high"])
            low = float(row["low"])

            if pos.side == "long":
                stop_price = pos.entry_price * (1.0 - c.stop_gross)
                target_price = pos.entry_price * (1.0 + c.target_gross)
                stop_hit = low <= stop_price
                target_hit = high >= target_price
            else:
                stop_price = pos.entry_price * (1.0 + c.stop_gross)
                target_price = pos.entry_price * (1.0 - c.target_gross)
                stop_hit = high >= stop_price
                target_hit = low <= target_price

            if stop_hit:
                tr = _close_trade(pos, date, stop_price, "hard_stop")
                trades.append(tr)
                balance += tr.pnl_usd
                del positions[pair]
            elif target_hit:
                tr = _close_trade(pos, date, target_price, "gross_target")
                trades.append(tr)
                balance += tr.pnl_usd
                del positions[pair]

        peak = max(peak, balance)
        if peak > 0:
            max_dd = max(max_dd, (peak - balance) / peak)

    for pair in list(positions):
        pos = positions[pair]
        last = frames[pair].iloc[-1]
        tr = _close_trade(
            pos,
            pd.Timestamp(last["date"]),
            float(last["close"]),
            "end_of_period",
        )
        trades.append(tr)
        balance += tr.pnl_usd
        del positions[pair]

    peak = max(peak, balance)
    if peak > 0:
        max_dd = max(max_dd, (peak - balance) / peak)

    tdf = pd.DataFrame([asdict(t) for t in trades])
    if tdf.empty:
        return {
            "label": label,
            "candidate": asdict(c),
            "trades": 0,
            "return_pct": 0.0,
            "net_pnl_usd": 0.0,
            "profit_factor": 0.0,
            "expectancy_usd": 0.0,
            "win_rate_pct": 0.0,
            "max_closed_drawdown_pct": round(max_dd * 100.0, 4),
            "positive_months": 0,
            "monthly_returns_usd": {},
            "by_side": {},
            "by_pair": {},
            "exit_reasons": {},
        }

    wins = tdf[tdf["pnl_usd"] > 0]
    losses = tdf[tdf["pnl_usd"] < 0]
    gross_profit = float(wins["pnl_usd"].sum())
    gross_loss = float(-losses["pnl_usd"].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    tdf["month"] = pd.to_datetime(tdf["exit_time"], utc=True).dt.strftime("%Y-%m")
    monthly = {
        key: round(float(group["pnl_usd"].sum()), 6)
        for key, group in tdf.groupby("month", sort=True)
    }

    def group_stats(group: pd.DataFrame) -> dict:
        return {
            "trades": int(len(group)),
            "pnl_usd": round(float(group["pnl_usd"].sum()), 6),
            "avg_net_return_pct": round(float(group["net_return"].mean() * 100.0), 4),
            "win_rate_pct": round(float((group["pnl_usd"] > 0).mean() * 100.0), 2),
        }

    return {
        "label": label,
        "candidate": asdict(c),
        "trades": int(len(tdf)),
        "return_pct": round((balance / STARTING_BALANCE - 1.0) * 100.0, 4),
        "net_pnl_usd": round(float(tdf["pnl_usd"].sum()), 6),
        "ending_balance": round(float(balance), 6),
        "profit_factor": round(float(pf), 4) if math.isfinite(pf) else 999.0,
        "expectancy_usd": round(float(tdf["pnl_usd"].mean()), 6),
        "win_rate_pct": round(float((tdf["pnl_usd"] > 0).mean() * 100.0), 2),
        "max_closed_drawdown_pct": round(max_dd * 100.0, 4),
        "positive_months": int(sum(value > 0 for value in monthly.values())),
        "monthly_returns_usd": monthly,
        "by_side": {
            key: group_stats(group) for key, group in tdf.groupby("side", sort=True)
        },
        "by_pair": {
            key: group_stats(group) for key, group in tdf.groupby("pair", sort=True)
        },
        "exit_reasons": {
            key: group_stats(group) for key, group in tdf.groupby("reason", sort=True)
        },
    }


def _passes_development(result: dict) -> bool:
    return (
        result["return_pct"] > 0.0
        and result["profit_factor"] > 1.10
        and result["expectancy_usd"] > 0.0
        and result["max_closed_drawdown_pct"] < 10.0
        and result["trades"] >= 30
        and result["positive_months"] >= 4
    )


def _selection_key(result: dict) -> tuple:
    monthly = list(result["monthly_returns_usd"].values())
    monthly_median = median(monthly) if monthly else -999.0
    return (
        result["positive_months"],
        result["return_pct"],
        result["profit_factor"],
        monthly_median,
        -result["max_closed_drawdown_pct"],
    )


def select_mode(dev_dirs: list[Path], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    cache: dict[int, dict[str, pd.DataFrame]] = {}

    for c in candidate_grid():
        # Build indicators separately per candidate because strictness/family
        # affect signal columns, while keeping the universe fixed.
        frames = _prepare_frames(dev_dirs, c)
        result = _simulate(frames, c, "2026-H1 development")
        result["passes_development_gate"] = _passes_development(result)
        results.append(result)
        print(
            f"{c.name}: trades={result['trades']} "
            f"ret={result['return_pct']:.2f}% PF={result['profit_factor']:.2f} "
            f"exp={result['expectancy_usd']:.4f} "
            f"months+={result['positive_months']} "
            f"DD={result['max_closed_drawdown_pct']:.2f}% "
            f"{'PASS' if result['passes_development_gate'] else 'FAIL'}"
        )

    passers = [r for r in results if r["passes_development_gate"]]
    selected = max(passers, key=_selection_key) if passers else None

    (output_dir / "v6-development-results.json").write_text(
        json.dumps({"results": results}, indent=2)
    )
    (output_dir / "v6-selected.json").write_text(
        json.dumps({"selected": selected}, indent=2)
    )

    print()
    if selected is None:
        print("V6 DEVELOPMENT RESULT: no candidate cleared the frozen gate.")
        print("The 2025 Q3 holdout must remain unseen.")
    else:
        print("V6 DEVELOPMENT WINNER:")
        print(json.dumps(selected, indent=2))
        print("Holdout may now be consumed exactly once.")
    return 0


def holdout_mode(holdout_dirs: list[Path], selected_path: Path, output_dir: Path) -> int:
    payload = json.loads(selected_path.read_text())
    selected = payload.get("selected")
    if not selected:
        raise SystemExit("No development winner exists; holdout must remain unseen.")

    c = Candidate(**selected["candidate"])
    result = _simulate(
        _prepare_frames(holdout_dirs, c),
        c,
        "2025-Q3 cross-venue holdout",
    )

    monthly_positive = result["positive_months"] >= 2
    holdout_pass = (
        result["return_pct"] > 0.0
        and result["profit_factor"] > 1.20
        and result["expectancy_usd"] > 0.0
        and result["max_closed_drawdown_pct"] < 8.0
        and result["trades"] >= 15
        and monthly_positive
    )
    result["passes_holdout_gate"] = holdout_pass

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "v6-holdout-result.json").write_text(
        json.dumps(result, indent=2)
    )
    print(json.dumps(result, indent=2))
    print()
    print("V6 HOLDOUT RESULT:", "PASS" if holdout_pass else "FAIL")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    select = sub.add_parser("select")
    select.add_argument("--development-dir", action="append", required=True)
    select.add_argument("--output-dir", required=True)

    holdout = sub.add_parser("holdout")
    holdout.add_argument("--holdout-dir", action="append", required=True)
    holdout.add_argument("--selected-json", required=True)
    holdout.add_argument("--output-dir", required=True)

    args = parser.parse_args()
    if args.command == "select":
        return select_mode(
            [Path(x) for x in args.development_dir],
            Path(args.output_dir),
        )
    return holdout_mode(
        [Path(x) for x in args.holdout_dir],
        Path(args.selected_json),
        Path(args.output_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
