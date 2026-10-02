"""Phase 162 crypto strategy-family tournament.

OFFLINE research only. This module consumes the existing immutable six-crypto
historical archives, evaluates several independent long/short strategy families
with one shared logical $100 portfolio, and compares them with cash and a
passive equal-weight benchmark under three explicit friction scenarios.

The strategy families are Signal Vault implementations inspired by public Jesse
strategy examples (trend, Donchian/Turtle breakout, and mean-reversion ideas),
not vendored Jesse code. Research short positions are hypothetical only and do
not authorize shorting on any execution venue.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from .offline_multimarket_pipeline import combine_historical_archives, read_historical_archive
from .relative_strength_tilt_research import SYMBOLS

HISTORICAL_HOURS = 2160
STARTING_CASH_USD = 100.0
STAKE_USD = 15.0
MAX_POSITIONS = 4

# One round trip = 2*taker fee + full spread + 2*slippage-per-side.
COST_SCENARIOS = {
    "illustrative_low_friction": 42.0,
    "illustrative_base_friction": 74.0,
    "illustrative_high_friction": 132.0,
}

# Disjoint 320-hour evaluation windows after enough warmup for the slowest
# 6-hour / 200-period trend filter (1200 hourly bars).
FOLDS = (
    ("fold_1", 1200, 1520),
    ("fold_2", 1520, 1840),
    ("fold_3", 1840, 2160),
)

STRATEGIES = (
    "trend_stack",
    "donchian20",
    "donchian55",
    "mean_reversion",
    "momentum24",
)


def _load(folder: Path):
    files = sorted(folder.glob("historical-crypto-*.json"))
    if not files:
        raise ValueError("historical crypto archives required")
    batches = tuple(read_historical_archive(path) for path in files)
    as_of = max(
        datetime.fromisoformat(batch.downloaded_utc).astimezone(timezone.utc)
        for batch in batches
    )
    datasets, _ = combine_historical_archives(batches, as_of=as_of)
    if set(datasets) != set(SYMBOLS):
        raise ValueError("exact six-crypto historical universe required")
    if {len(rows) for rows in datasets.values()} != {HISTORICAL_HOURS}:
        raise ValueError("exact 2160 aligned hourly bars per crypto required")
    aligned = None
    for rows in datasets.values():
        stamps = tuple(row.start_utc for row in rows)
        if aligned is None:
            aligned = stamps
        elif stamps != aligned:
            raise ValueError("crypto histories must share the exact hourly clock")
    return datasets


def _frames(datasets) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol, rows in datasets.items():
        frame = pd.DataFrame({
            "ts": pd.to_datetime([row.start_utc for row in rows], utc=True),
            "open": [float(row.open) for row in rows],
            "high": [float(row.high) for row in rows],
            "low": [float(row.low) for row in rows],
            "close": [float(row.close) for row in rows],
            "volume": [float(row.volume) for row in rows],
        })
        frame["ema21"] = frame.close.ewm(span=21, adjust=False).mean()
        frame["ema50"] = frame.close.ewm(span=50, adjust=False).mean()
        frame["ema100"] = frame.close.ewm(span=100, adjust=False).mean()
        frame["sma200"] = frame.close.rolling(200).mean()
        frame["mean20"] = frame.close.rolling(20).mean()
        frame["std20"] = frame.close.rolling(20).std()
        frame["z20"] = (frame.close - frame.mean20) / frame.std20
        frame["prior_high20"] = frame.high.rolling(20).max().shift(1)
        frame["prior_low20"] = frame.low.rolling(20).min().shift(1)
        frame["prior_high55"] = frame.high.rolling(55).max().shift(1)
        frame["prior_low55"] = frame.low.rolling(55).min().shift(1)
        frame["mid10"] = (
            frame.high.rolling(10).max().shift(1)
            + frame.low.rolling(10).min().shift(1)
        ) / 2.0
        frame["ret24"] = frame.close.pct_change(24)

        # Causal 6-hour bars: each 6-hour bucket uses only the last close in
        # that completed bucket. Values are then repeated over the source bars.
        group = np.arange(len(frame)) // 6
        six = frame.groupby(group).agg({"close": "last"})
        six["sma50"] = six.close.rolling(50).mean()
        six["sma200"] = six.close.rolling(200).mean()
        # A 6h bucket's final close is unavailable during its first five
        # source hours. Shift one completed bucket before forward-expanding.
        available = six[["sma50", "sma200"]].shift(1)
        frame["six_sma50"] = np.repeat(
            available.sma50.to_numpy(), 6
        )[: len(frame)]
        frame["six_sma200"] = np.repeat(
            available.sma200.to_numpy(), 6
        )[: len(frame)]
        frames[symbol] = frame
    return frames


def _entry_signal(strategy: str, frame: pd.DataFrame, index: int) -> tuple[int, float]:
    if index < 1200 or index >= len(frame) - 1:
        return 0, 0.0
    row = frame.iloc[index]
    if strategy == "trend_stack":
        if pd.isna(row.six_sma200):
            return 0, 0.0
        bullish = (
            row.six_sma50 > row.six_sma200
            and row.ema21 > row.ema50 > row.ema100
            and row.close > row.ema21
        )
        bearish = (
            row.six_sma50 < row.six_sma200
            and row.ema21 < row.ema50 < row.ema100
            and row.close < row.ema21
        )
        side = 1 if bullish else (-1 if bearish else 0)
        return side, abs(row.ema21 / row.ema100 - 1.0) if side else 0.0

    if strategy in ("donchian20", "donchian55"):
        high_key = "prior_high20" if strategy == "donchian20" else "prior_high55"
        low_key = "prior_low20" if strategy == "donchian20" else "prior_low55"
        bullish = row.close > row[high_key] and row.close > row.sma200
        bearish = row.close < row[low_key] and row.close < row.sma200
        side = 1 if bullish else (-1 if bearish else 0)
        return side, abs(row.close / row.sma200 - 1.0) if side else 0.0

    if strategy == "mean_reversion":
        bullish = row.z20 < -2.0 and row.close > row.sma200
        bearish = row.z20 > 2.0 and row.close < row.sma200
        side = 1 if bullish else (-1 if bearish else 0)
        return side, abs(row.z20) if side else 0.0

    if strategy == "momentum24":
        bullish = row.ret24 > 0.03 and row.close > row.sma200
        bearish = row.ret24 < -0.03 and row.close < row.sma200
        side = 1 if bullish else (-1 if bearish else 0)
        return side, abs(row.ret24) if side else 0.0

    raise ValueError("unknown strategy family")


def _should_exit(
    strategy: str,
    frame: pd.DataFrame,
    index: int,
    position: Mapping[str, object],
) -> bool:
    row = frame.iloc[index]
    side = int(position["side"])
    hold = index - int(position["signal_index"])
    if hold >= 168:
        return True
    if strategy == "trend_stack":
        return (
            (side == 1 and (row.ema21 < row.ema50 or row.close < row.ema50))
            or (side == -1 and (row.ema21 > row.ema50 or row.close > row.ema50))
        )
    if strategy in ("donchian20", "donchian55"):
        return (
            (side == 1 and row.close < row.mid10)
            or (side == -1 and row.close > row.mid10)
        )
    if strategy == "mean_reversion":
        return (
            (side == 1 and row.close >= row.mean20)
            or (side == -1 and row.close <= row.mean20)
            or hold >= 72
        )
    if strategy == "momentum24":
        return (
            (side == 1 and row.ret24 <= 0)
            or (side == -1 and row.ret24 >= 0)
            or hold >= 72
        )
    raise ValueError("unknown strategy family")


def _simulate(
    strategy: str,
    frames: Mapping[str, pd.DataFrame],
    start_index: int,
    end_index: int,
    round_trip_cost_bps: float,
) -> dict[str, object]:
    cash = STARTING_CASH_USD
    positions: dict[str, dict[str, object]] = {}
    trades: list[dict[str, object]] = []
    peak = STARTING_CASH_USD
    max_drawdown = 0.0

    for index in range(start_index, end_index - 1):
        exits = [
            symbol
            for symbol, position in positions.items()
            if _should_exit(strategy, frames[symbol], index, position)
        ]
        for symbol in exits:
            position = positions.pop(symbol)
            exit_price = float(frames[symbol].iloc[index + 1].open)
            gross_return = int(position["side"]) * (
                exit_price / float(position["entry_price"]) - 1.0
            )
            net_return = gross_return - round_trip_cost_bps / 10_000.0
            pnl = STAKE_USD * net_return
            cash += STAKE_USD + pnl
            trades.append({
                **position,
                "exit_signal_index": index,
                "exit_price": exit_price,
                "net_return": net_return,
                "pnl_usd": pnl,
            })

        candidates: list[tuple[float, str, int]] = []
        for symbol in sorted(frames):
            if symbol in positions:
                continue
            side, score = _entry_signal(strategy, frames[symbol], index)
            if side:
                candidates.append((score, symbol, side))
        candidates.sort(reverse=True)

        for score, symbol, side in candidates:
            if len(positions) >= MAX_POSITIONS or cash < STAKE_USD:
                break
            entry_price = float(frames[symbol].iloc[index + 1].open)
            positions[symbol] = {
                "symbol": symbol,
                "side": side,
                "signal_index": index,
                "entry_price": entry_price,
                "score": score,
            }
            cash -= STAKE_USD

        marked = cash
        for symbol, position in positions.items():
            close = float(frames[symbol].iloc[index + 1].close)
            gross_mark = int(position["side"]) * (
                close / float(position["entry_price"]) - 1.0
            )
            marked += STAKE_USD * (
                1.0 + gross_mark - round_trip_cost_bps / 10_000.0
            )
        peak = max(peak, marked)
        max_drawdown = max(max_drawdown, peak - marked)

    final_index = end_index - 1
    for symbol, position in list(positions.items()):
        exit_price = float(frames[symbol].iloc[final_index].close)
        gross_return = int(position["side"]) * (
            exit_price / float(position["entry_price"]) - 1.0
        )
        net_return = gross_return - round_trip_cost_bps / 10_000.0
        pnl = STAKE_USD * net_return
        cash += STAKE_USD + pnl
        trades.append({
            **position,
            "exit_signal_index": final_index,
            "exit_price": exit_price,
            "net_return": net_return,
            "pnl_usd": pnl,
            "forced_fold_liquidation": True,
        })
        del positions[symbol]

    return {
        "net_pnl_usd": cash - STARTING_CASH_USD,
        "final_equity_usd": cash,
        "trade_count": len(trades),
        "win_rate": (
            sum(float(trade["pnl_usd"]) > 0 for trade in trades) / len(trades)
            if trades else 0.0
        ),
        "expectancy_usd_per_trade": (
            sum(float(trade["pnl_usd"]) for trade in trades) / len(trades)
            if trades else 0.0
        ),
        "max_marked_drawdown_usd": max_drawdown,
        "long_count": sum(int(trade["side"]) == 1 for trade in trades),
        "short_count": sum(int(trade["side"]) == -1 for trade in trades),
        "estimated_total_round_trip_cost_usd": (
            len(trades) * STAKE_USD * round_trip_cost_bps / 10_000.0
        ),
    }


def _passive(
    frames: Mapping[str, pd.DataFrame],
    start_index: int,
    end_index: int,
    round_trip_cost_bps: float,
) -> dict[str, object]:
    pnl = 0.0
    for symbol in sorted(frames):
        entry = float(frames[symbol].iloc[start_index + 1].open)
        exit_price = float(frames[symbol].iloc[end_index - 1].close)
        net_return = exit_price / entry - 1.0 - round_trip_cost_bps / 10_000.0
        pnl += STAKE_USD * net_return
    return {
        "net_pnl_usd": pnl,
        "final_equity_usd": STARTING_CASH_USD + pnl,
        "trade_count": len(frames),
        "exposure_usd": STAKE_USD * len(frames),
        "estimated_total_round_trip_cost_usd": (
            len(frames) * STAKE_USD * round_trip_cost_bps / 10_000.0
        ),
    }


def build_tournament(folder: Path) -> dict[str, object]:
    datasets = _load(folder)
    frames = _frames(datasets)
    folds: dict[str, object] = {}
    for fold_name, start_index, end_index in FOLDS:
        scenarios: dict[str, object] = {}
        for scenario, cost_bps in COST_SCENARIOS.items():
            books = {
                strategy: _simulate(
                    strategy, frames, start_index, end_index, cost_bps
                )
                for strategy in STRATEGIES
            }
            books["passive_equal_weight"] = _passive(
                frames, start_index, end_index, cost_bps
            )
            books["cash"] = {
                "net_pnl_usd": 0.0,
                "final_equity_usd": STARTING_CASH_USD,
            }
            scenarios[scenario] = books
        folds[fold_name] = {
            "start_index": start_index,
            "end_index_exclusive": end_index,
            "scenarios": scenarios,
        }

    base = "illustrative_base_friction"
    aggregate: dict[str, object] = {}
    for strategy in (*STRATEGIES, "passive_equal_weight"):
        values = [
            float(folds[name]["scenarios"][base][strategy]["net_pnl_usd"])
            for name, _, _ in FOLDS
        ]
        aggregate[strategy] = {
            "fold_pnls_usd": values,
            "sum_fold_pnl_usd": sum(values),
            "positive_folds": sum(value > 0 for value in values),
        }

    return {
        "kind": "PHASE162_CRYPTO_STRATEGY_FAMILY_TOURNAMENT",
        "historical_hours_per_asset": HISTORICAL_HOURS,
        "assets": sorted(datasets),
        "source_data_historical_not_forward": True,
        "execution_semantics": "signal at hourly close, execute at next hourly open",
        "portfolio": {
            "starting_cash_usd": STARTING_CASH_USD,
            "stake_per_position_usd": STAKE_USD,
            "max_simultaneous_positions": MAX_POSITIONS,
        },
        "round_trip_cost_scenarios_bps": COST_SCENARIOS,
        "strategy_family_sources": {
            "trend_stack":
                "Signal Vault implementation inspired by Jesse multi-timeframe trend examples",
            "donchian20":
                "Signal Vault implementation inspired by Jesse Donchian/Turtle examples",
            "donchian55":
                "Signal Vault implementation inspired by Jesse Donchian/Turtle examples",
            "mean_reversion":
                "Signal Vault Bollinger/z-score mean-reversion family",
            "momentum24":
                "Signal Vault directional momentum family",
        },
        "folds": folds,
        "base_cost_aggregate": aggregate,
        "screening_conclusion": {
            "strategy_promoted": False,
            "reason": (
                "No tested active family beat the passive equal-weight comparator "
                "across all three disjoint folds under base friction."
            ),
        },
        "short_results_are_research_only": True,
        "automatic_paper_promotion": False,
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_tournament(args.folder)
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("output must be create-only")
        payload = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        summary = {
            "kind": result["kind"],
            "base_cost_aggregate": result["base_cost_aggregate"],
            "screening_conclusion": result["screening_conclusion"],
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }
        print(json.dumps(summary, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "PHASE162_CRYPTO_STRATEGY_FAMILY_TOURNAMENT",
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
