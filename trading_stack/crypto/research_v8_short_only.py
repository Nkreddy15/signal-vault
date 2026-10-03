"""Signal Vault V8 short-only bear breakout tournament.

V7's best development candidate was almost flat after friction, but its long
book was strongly negative while its short book was positive. V8 freezes that
observation into a new hypothesis: only trade downside breakouts during clearly
bearish BTC + pair regimes.

Research only. No exchange/broker orders are submitted.
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
MAX_OPEN_TRADES = 3
ROUND_TRIP_FRICTION = 0.0074


@dataclass(frozen=True)
class Candidate:
    name: str
    breakout_hours: int
    target_gross: float
    stop_gross: float
    cooldown_hours: int
    btc_ret168_max: float
    pair_ret72_max: float
    volume_floor: float
    max_hold_hours: int = 240


@dataclass
class Position:
    pair: str
    entry_time: pd.Timestamp
    entry_price: float
    stake: float


@dataclass
class Trade:
    pair: str
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
    for breakout_hours in (72, 96, 144):
        for target, stop in ((0.10, 0.035), (0.12, 0.04)):
            for cooldown in (24, 48):
                out.append(
                    Candidate(
                        name=(
                            f"short-{breakout_hours}h-"
                            f"t{int(target*100)}-s{int(stop*100)}-cd{cooldown}"
                        ),
                        breakout_hours=breakout_hours,
                        target_gross=target,
                        stop_gross=stop,
                        cooldown_hours=cooldown,
                        btc_ret168_max=-0.04,
                        pair_ret72_max=-0.02,
                        volume_floor=1.15,
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


def _load(dirs: Iterable[Path], pair: str) -> pd.DataFrame:
    filename = pair.replace("/", "_") + "-1h.feather"
    parts = []
    for directory in dirs:
        path = directory / filename
        if not path.exists():
            raise FileNotFoundError(path)
        part = pd.read_feather(path)
        part["date"] = pd.to_datetime(part["date"], utc=True)
        parts.append(part)
    return (
        pd.concat(parts, ignore_index=True)
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )


def _indicators(frame: pd.DataFrame, lookback: int) -> pd.DataFrame:
    frame = frame.copy()
    close = frame["close"]
    volume = frame["volume"]
    frame["ema20"] = close.ewm(span=20, adjust=False).mean()
    frame["ema50"] = close.ewm(span=50, adjust=False).mean()
    frame["ema100"] = close.ewm(span=100, adjust=False).mean()
    frame["ema100_slope24"] = frame["ema100"].pct_change(24)
    frame["ret24"] = close.pct_change(24)
    frame["ret72"] = close.pct_change(72)
    frame["ret168"] = close.pct_change(168)
    frame["rsi14"] = _rsi(close)
    frame["atr14"] = _atr(frame)
    frame["atr_pct"] = frame["atr14"] / close
    frame["vol20"] = volume.rolling(20).mean()
    frame["vol_ratio"] = volume / frame["vol20"].replace(0.0, float("nan"))
    frame["prior_low"] = frame["low"].rolling(lookback).min().shift(1)
    return frame


def _prepare(dirs: Iterable[Path], c: Candidate) -> Dict[str, pd.DataFrame]:
    frames = {pair: _indicators(_load(dirs, pair), c.breakout_hours) for pair in PAIRS}

    btc = frames["BTC/USD"][
        ["date", "close", "ema20", "ema50", "ema100", "ema100_slope24", "ret24", "ret72", "ret168"]
    ].copy()
    btc.columns = [
        "date", "btc_close", "btc_ema20", "btc_ema50", "btc_ema100",
        "btc_ema100_slope24", "btc_ret24", "btc_ret72", "btc_ret168",
    ]

    for pair, base in list(frames.items()):
        f = base.merge(btc, on="date", how="left")

        btc_bear = (
            (f["btc_close"] < f["btc_ema100"])
            & (f["btc_ema20"] < f["btc_ema50"])
            & (f["btc_ema50"] < f["btc_ema100"])
            & (f["btc_ema100_slope24"] < -0.001)
            & (f["btc_ret72"] < -0.02)
            & (f["btc_ret168"] < c.btc_ret168_max)
        )

        pair_bear = (
            (f["close"] < f["ema100"])
            & (f["ema20"] < f["ema50"])
            & (f["ema50"] < f["ema100"])
            & (f["ema100_slope24"] < 0.0)
            & (f["ret72"] < c.pair_ret72_max)
        )

        breakdown = (
            (f["close"] < f["prior_low"])
            & (f["ret24"] < -0.015)
            & (f["rsi14"].between(26, 45))
            & (f["vol_ratio"] >= c.volume_floor)
            & (f["atr_pct"] >= 0.008)
        )

        f["short_signal"] = btc_bear & pair_bear & breakdown & (f["volume"] > 0)
        f["btc_bear"] = btc_bear
        f["pair_bear"] = pair_bear
        f["score"] = (
            f["ret168"].abs().fillna(0.0)
            + f["ret72"].abs().fillna(0.0)
            + f["atr_pct"].fillna(0.0)
        )
        frames[pair] = f.set_index("date", drop=False)

    return frames


def _gross(entry: float, exit_price: float) -> float:
    return (entry - exit_price) / entry


def _close(pos: Position, when: pd.Timestamp, price: float, reason: str) -> Trade:
    gross = _gross(pos.entry_price, price)
    net = gross - ROUND_TRIP_FRICTION
    return Trade(
        pair=pos.pair,
        entry_time=pos.entry_time.isoformat(),
        exit_time=when.isoformat(),
        entry_price=pos.entry_price,
        exit_price=float(price),
        gross_return=gross,
        net_return=net,
        pnl_usd=pos.stake * net,
        reason=reason,
        hold_hours=(when - pos.entry_time).total_seconds() / 3600.0,
    )


def _simulate(frames: Dict[str, pd.DataFrame], c: Candidate, label: str) -> dict:
    all_dates = sorted(set().union(*(set(df.index) for df in frames.values())))
    positions: Dict[str, Position] = {}
    last_exit: Dict[str, pd.Timestamp] = {}
    trades: List[Trade] = []
    balance = STARTING_BALANCE
    peak = balance
    max_dd = 0.0

    for date in all_dates:
        for pair in list(positions):
            f = frames[pair]
            if date not in f.index:
                continue
            loc = f.index.get_loc(date)
            if isinstance(loc, slice) or loc == 0:
                continue
            row = f.iloc[loc]
            prev = f.iloc[loc - 1]
            pos = positions[pair]
            open_price = float(row["open"])
            held = (date - pos.entry_time).total_seconds() / 3600.0
            regime_alive = bool(prev["btc_bear"]) and bool(prev["pair_bear"])

            reason: Optional[str] = None
            if (not regime_alive) and _gross(pos.entry_price, open_price) < -0.01:
                reason = "regime_failure"
            elif held >= c.max_hold_hours:
                reason = "time_exit"

            if reason:
                tr = _close(pos, date, open_price, reason)
                trades.append(tr)
                balance += tr.pnl_usd
                last_exit[pair] = date
                del positions[pair]

        slots = MAX_OPEN_TRADES - len(positions)
        if slots > 0:
            choices: List[Tuple[float, str, float]] = []
            for pair, f in frames.items():
                if pair in positions or date not in f.index:
                    continue
                if pair in last_exit:
                    elapsed = (date - last_exit[pair]).total_seconds() / 3600.0
                    if elapsed < c.cooldown_hours:
                        continue
                loc = f.index.get_loc(date)
                if isinstance(loc, slice) or loc == 0:
                    continue
                row = f.iloc[loc]
                prev = f.iloc[loc - 1]
                if bool(prev["short_signal"]):
                    choices.append((float(prev["score"]), pair, float(row["open"])))

            choices.sort(reverse=True)
            for _, pair, price in choices[:slots]:
                positions[pair] = Position(
                    pair=pair,
                    entry_time=date,
                    entry_price=price,
                    stake=min(STAKE, max(balance, 0.0)),
                )

        # Stop-first if both target and stop are touched in one candle.
        for pair in list(positions):
            f = frames[pair]
            if date not in f.index:
                continue
            row = f.loc[date]
            pos = positions[pair]
            high = float(row["high"])
            low = float(row["low"])
            stop = pos.entry_price * (1.0 + c.stop_gross)
            target = pos.entry_price * (1.0 - c.target_gross)
            stop_hit = high >= stop
            target_hit = low <= target

            if stop_hit:
                tr = _close(pos, date, stop, "hard_stop")
                trades.append(tr)
                balance += tr.pnl_usd
                last_exit[pair] = date
                del positions[pair]
            elif target_hit:
                tr = _close(pos, date, target, "gross_target")
                trades.append(tr)
                balance += tr.pnl_usd
                last_exit[pair] = date
                del positions[pair]

        peak = max(peak, balance)
        if peak > 0:
            max_dd = max(max_dd, (peak - balance) / peak)

    for pair in list(positions):
        pos = positions[pair]
        last = frames[pair].iloc[-1]
        tr = _close(pos, pd.Timestamp(last["date"]), float(last["close"]), "end_of_period")
        trades.append(tr)
        balance += tr.pnl_usd

    tdf = pd.DataFrame([asdict(t) for t in trades])
    if tdf.empty:
        return {
            "candidate": asdict(c), "label": label, "trades": 0,
            "return_pct": 0.0, "profit_factor": 0.0, "expectancy_usd": 0.0,
            "gross_expectancy_pct": 0.0, "max_closed_drawdown_pct": 0.0,
            "positive_months": 0, "monthly_pnl_usd": {}, "by_pair": {},
            "exit_reasons": {},
        }

    wins = tdf[tdf["pnl_usd"] > 0]
    losses = tdf[tdf["pnl_usd"] < 0]
    gp = float(wins["pnl_usd"].sum())
    gl = float(-losses["pnl_usd"].sum())
    pf = gp / gl if gl > 0 else 999.0
    tdf["month"] = pd.to_datetime(tdf["exit_time"], utc=True).dt.strftime("%Y-%m")
    monthly = {m: round(float(g["pnl_usd"].sum()), 6) for m, g in tdf.groupby("month")}

    def group(g: pd.DataFrame) -> dict:
        return {
            "trades": int(len(g)),
            "pnl_usd": round(float(g["pnl_usd"].sum()), 6),
            "gross_expectancy_pct": round(float(g["gross_return"].mean() * 100.0), 4),
            "net_expectancy_pct": round(float(g["net_return"].mean() * 100.0), 4),
            "win_rate_pct": round(float((g["pnl_usd"] > 0).mean() * 100.0), 2),
        }

    return {
        "candidate": asdict(c),
        "label": label,
        "trades": int(len(tdf)),
        "return_pct": round((balance / STARTING_BALANCE - 1.0) * 100.0, 4),
        "net_pnl_usd": round(float(tdf["pnl_usd"].sum()), 6),
        "profit_factor": round(float(pf), 4) if math.isfinite(pf) else 999.0,
        "expectancy_usd": round(float(tdf["pnl_usd"].mean()), 6),
        "gross_expectancy_pct": round(float(tdf["gross_return"].mean() * 100.0), 4),
        "win_rate_pct": round(float((tdf["pnl_usd"] > 0).mean() * 100.0), 2),
        "max_closed_drawdown_pct": round(max_dd * 100.0, 4),
        "positive_months": int(sum(v > 0 for v in monthly.values())),
        "monthly_pnl_usd": monthly,
        "by_pair": {k: group(g) for k, g in tdf.groupby("pair")},
        "exit_reasons": {k: group(g) for k, g in tdf.groupby("reason")},
    }


def _dev_pass(r: dict) -> bool:
    return (
        r["return_pct"] > 2.0
        and r["profit_factor"] > 1.20
        and r["expectancy_usd"] > 0.0
        and r["max_closed_drawdown_pct"] < 8.0
        and r["trades"] >= 18
        and r["positive_months"] >= 4
    )


def _key(r: dict) -> tuple:
    monthly = list(r["monthly_pnl_usd"].values())
    return (
        r["positive_months"],
        r["return_pct"],
        r["profit_factor"],
        median(monthly) if monthly else -999,
        -r["max_closed_drawdown_pct"],
    )


def select_mode(dev_dirs: list[Path], outdir: Path) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for c in candidate_grid():
        r = _simulate(_prepare(dev_dirs, c), c, "2026-H1 development")
        r["passes_development_gate"] = _dev_pass(r)
        results.append(r)
        print(
            f"{c.name}: trades={r['trades']} ret={r['return_pct']:.2f}% "
            f"PF={r['profit_factor']:.2f} exp={r['expectancy_usd']:.4f} "
            f"gross_exp={r['gross_expectancy_pct']:.3f}% "
            f"months+={r['positive_months']} DD={r['max_closed_drawdown_pct']:.2f}% "
            f"{'PASS' if r['passes_development_gate'] else 'FAIL'}"
        )

    passers = [r for r in results if r["passes_development_gate"]]
    selected = max(passers, key=_key) if passers else None
    (outdir / "v8-development-results.json").write_text(json.dumps({"results": results}, indent=2))
    (outdir / "v8-selected.json").write_text(json.dumps({"selected": selected}, indent=2))

    print()
    if selected is None:
        best = max(results, key=_key)
        print("V8 DEVELOPMENT RESULT: no short-only candidate cleared the frozen gate.")
        print("Best short-only candidate (still rejected):")
        print(json.dumps(best, indent=2))
        print("The 2025 Q3 holdout must remain unseen.")
    else:
        print("V8 DEVELOPMENT WINNER:")
        print(json.dumps(selected, indent=2))
        print("The 2025 Q3 holdout may now be consumed exactly once.")
    return 0


def holdout_mode(holdout_dirs: list[Path], selected_json: Path, outdir: Path) -> int:
    payload = json.loads(selected_json.read_text())
    selected = payload.get("selected")
    if not selected:
        raise SystemExit("No V8 winner exists. Holdout must remain unseen.")
    c = Candidate(**selected["candidate"])
    r = _simulate(_prepare(holdout_dirs, c), c, "2025-Q3 cross-venue holdout")
    r["passes_holdout_gate"] = (
        r["return_pct"] > 0.0
        and r["profit_factor"] > 1.20
        and r["expectancy_usd"] > 0.0
        and r["max_closed_drawdown_pct"] < 8.0
        and r["trades"] >= 8
        and r["positive_months"] >= 2
    )
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "v8-holdout-result.json").write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=2))
    print("V8 HOLDOUT RESULT:", "PASS" if r["passes_holdout_gate"] else "FAIL")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("select")
    s.add_argument("--development-dir", action="append", required=True)
    s.add_argument("--output-dir", required=True)

    h = sub.add_parser("holdout")
    h.add_argument("--holdout-dir", action="append", required=True)
    h.add_argument("--selected-json", required=True)
    h.add_argument("--output-dir", required=True)

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
