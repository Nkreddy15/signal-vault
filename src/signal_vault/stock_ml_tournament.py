"""Phase 162 long-horizon US-equity ML tournament.

Consumes only the existing SHA-verified long-horizon IEX research bundle. The
six-stock common XNYS core-hour clock is treated as a sequence of completed
market bars; overnight/weekend/holiday gaps are never fabricated.

Models estimate fixed future *core-bar* returns, select entry thresholds on the
chronological validation fold only, then report an untouched descriptive test
fold under three equity-friction assumptions. Long and short directions are
research semantics only; no shortability or broker permission is assumed.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .ci_historical_equities import EQUITY_ESTIMATED_COST_SCENARIOS, SYMBOLS
from .offline_equity_walk_forward import _reload_phase48_verified_source
from .offline_long_equity_validation import validate_long_equity_history

MIN_CORE_BARS = 240
LOOKBACK = 48
HORIZONS = (6, 12, 24)
THRESHOLDS = (0.002, 0.003, 0.005, 0.0075, 0.010, 0.015, 0.020)
MIN_VALIDATION_TRADES = 10
STARTING_CASH_USD = 100.0
STAKE_USD = 15.0
MAX_POSITIONS = 4

FEATURES = (
    "ret_1",
    "ret_3",
    "ret_6",
    "ret_12",
    "ret_24",
    "ret_48",
    "ema6_over_ema18_minus1",
    "ema12_over_ema36_minus1",
    "vol_6",
    "vol_24",
    "range_1",
    "volume_z_24",
    "cross_section_rank_6",
    "session_bucket_sin",
    "session_bucket_cos",
)

MODEL_NAMES = (
    "ridge_v1",
    "random_forest_v1",
    "extra_trees_v1",
    "hist_gradient_boosting_v1",
)


def _round_trip_bps(raw: dict[str, str]) -> float:
    return (
        2.0 * float(raw["taker_fee_bps"])
        + float(raw["full_spread_bps"])
        + 2.0 * float(raw["slippage_per_side_bps"])
    )


COST_SCENARIOS = {
    name: _round_trip_bps(values)
    for name, values in EQUITY_ESTIMATED_COST_SCENARIOS.items()
}


def _load(root: Path, *, as_of: datetime):
    baseline = validate_long_equity_history(root, as_of=as_of)
    datasets, timeline = _reload_phase48_verified_source(
        root,
        baseline=baseline,
        as_of=as_of,
    )
    if set(datasets) != set(SYMBOLS):
        raise ValueError("exact six-stock verified universe required")
    if len(timeline) < MIN_CORE_BARS:
        raise ValueError("long stock history is too short for ML tournament")
    if any(len(datasets[symbol]) != len(timeline) for symbol in SYMBOLS):
        raise ValueError("stock datasets must share exact verified core-bar clock")
    return datasets, tuple(timeline), baseline


def _build_rows(datasets, timeline):
    frames: dict[str, pd.DataFrame] = {}
    n = len(timeline)
    symbols = tuple(SYMBOLS)
    for symbol in symbols:
        rows = datasets[symbol]
        frame = pd.DataFrame({
            "ts": pd.to_datetime([bar.start_utc for bar in rows], utc=True),
            "open": [float(bar.open) for bar in rows],
            "high": [float(bar.high) for bar in rows],
            "low": [float(bar.low) for bar in rows],
            "close": [float(bar.close) for bar in rows],
            "volume": [float(bar.volume) for bar in rows],
        })
        for horizon in (1, 3, 6, 12, 24, 48):
            frame[f"ret_{horizon}"] = frame.close.pct_change(horizon)
        frame["ema6"] = frame.close.ewm(span=6, adjust=False).mean()
        frame["ema18"] = frame.close.ewm(span=18, adjust=False).mean()
        frame["ema12"] = frame.close.ewm(span=12, adjust=False).mean()
        frame["ema36"] = frame.close.ewm(span=36, adjust=False).mean()
        frame["ema6_over_ema18_minus1"] = frame.ema6 / frame.ema18 - 1.0
        frame["ema12_over_ema36_minus1"] = frame.ema12 / frame.ema36 - 1.0
        one_bar = frame.close.pct_change()
        frame["vol_6"] = one_bar.rolling(6).std()
        frame["vol_24"] = one_bar.rolling(24).std()
        frame["range_1"] = (frame.high - frame.low) / frame.close
        frame["volume_z_24"] = (
            (frame.volume - frame.volume.rolling(24).mean())
            / frame.volume.rolling(24).std()
        )

        # Existing conservative collector keeps six complete core-hour buckets
        # per ordinary full XNYS session. Encode intraday location without ever
        # fabricating overnight bars. Early closes simply end the actual grid.
        bucket = np.arange(n) % 6
        frame["session_bucket_sin"] = np.sin(2 * np.pi * bucket / 6.0)
        frame["session_bucket_cos"] = np.cos(2 * np.pi * bucket / 6.0)
        frames[symbol] = frame

    for index in range(n):
        values = {symbol: frames[symbol].loc[index, "ret_6"] for symbol in symbols}
        if any(pd.isna(value) for value in values.values()):
            for symbol in symbols:
                frames[symbol].loc[index, "cross_section_rank_6"] = np.nan
            continue
        ordered = sorted(symbols, key=lambda symbol: (values[symbol], symbol))
        for symbol in symbols:
            frames[symbol].loc[index, "cross_section_rank_6"] = (
                ordered.index(symbol) / (len(symbols) - 1) * 2.0 - 1.0
            )

    combined = []
    for symbol in symbols:
        frame = frames[symbol].copy()
        frame["symbol"] = symbol
        frame["time_index"] = np.arange(n)
        for horizon in HORIZONS:
            frame[f"target_{horizon}"] = (
                frame.close.shift(-horizon) / frame.open.shift(-1) - 1.0
            )
        combined.append(frame)
    return pd.concat(combined, ignore_index=True), frames


def _bounds(n: int, horizon: int):
    usable_start = LOOKBACK
    usable = n - usable_start
    if usable < 180:
        raise ValueError("insufficient post-warmup stock bars for three-way ML split")
    train_cut = usable_start + int(usable * 0.60)
    validation_cut = usable_start + int(usable * 0.80)
    if train_cut + horizon >= validation_cut:
        raise ValueError("stock fold too short after target purge")
    return train_cut, validation_cut


def _split(rows: pd.DataFrame, *, n: int, horizon: int):
    target = f"target_{horizon}"
    clean = rows.dropna(subset=[*FEATURES, target]).copy()
    train_cut, validation_cut = _bounds(n, horizon)
    train = clean[clean.time_index < train_cut - horizon]
    validation = clean[
        (clean.time_index >= train_cut)
        & (clean.time_index < validation_cut - horizon)
    ]
    test = clean[clean.time_index >= validation_cut]
    if train.empty or validation.empty or test.empty:
        raise ValueError("stock purged chronological split is empty")
    return train, validation, test, train_cut, validation_cut


def _model(name: str):
    if name == "ridge_v1":
        return Pipeline([
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ])
    if name == "random_forest_v1":
        return RandomForestRegressor(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=10,
            max_features=0.7,
            n_jobs=-1,
            random_state=42,
        )
    if name == "extra_trees_v1":
        return ExtraTreesRegressor(
            n_estimators=300,
            max_depth=10,
            min_samples_leaf=10,
            max_features=0.8,
            n_jobs=-1,
            random_state=42,
        )
    if name == "hist_gradient_boosting_v1":
        return HistGradientBoostingRegressor(
            learning_rate=0.04,
            max_iter=220,
            max_leaf_nodes=15,
            min_samples_leaf=20,
            l2_regularization=1.0,
            random_state=42,
        )
    raise ValueError("unknown stock ML model")


def _simulate(
    fold: pd.DataFrame,
    predictions,
    *,
    horizon: int,
    threshold: float,
    cost_bps: float,
    frames: dict[str, pd.DataFrame],
) -> dict[str, object]:
    view = fold[["symbol", "time_index", f"target_{horizon}"]].copy()
    view["prediction"] = np.asarray(predictions, dtype=float)
    candidates: dict[int, list[tuple[str, float, float]]] = {}
    for row in view.itertuples(index=False):
        pred = float(row.prediction)
        if abs(pred) >= threshold:
            target = float(getattr(row, f"target_{horizon}"))
            candidates.setdefault(int(row.time_index), []).append(
                (row.symbol, pred, target)
            )

    first = int(view.time_index.min())
    last = int(view.time_index.max())
    cash = STARTING_CASH_USD
    positions: dict[str, dict[str, object]] = {}
    trades = []
    peak = STARTING_CASH_USD
    max_dd = 0.0

    for index in range(first, last + horizon + 1):
        for symbol in [
            symbol
            for symbol, position in positions.items()
            if int(position["exit_index"]) == index
        ]:
            position = positions.pop(symbol)
            gross = int(position["side"]) * float(position["target_return"])
            net = gross - cost_bps / 10_000.0
            pnl = STAKE_USD * net
            cash += STAKE_USD + pnl
            trades.append({**position, "pnl_usd": pnl, "net_return": net})

        ranked = sorted(
            candidates.get(index, ()),
            key=lambda item: (abs(item[1]), item[0]),
            reverse=True,
        )
        for symbol, pred, target in ranked:
            if symbol in positions:
                continue
            if len(positions) >= MAX_POSITIONS or cash < STAKE_USD:
                break
            positions[symbol] = {
                "symbol": symbol,
                "side": 1 if pred > 0 else -1,
                "signal_index": index,
                "exit_index": index + horizon,
                "prediction": pred,
                "target_return": target,
            }
            cash -= STAKE_USD

        marked = cash
        if index < len(next(iter(frames.values()))):
            for symbol, position in positions.items():
                entry = float(
                    frames[symbol].loc[int(position["signal_index"]) + 1, "open"]
                )
                current = float(frames[symbol].loc[index, "close"])
                gross_mark = int(position["side"]) * (current / entry - 1.0)
                marked += STAKE_USD * (
                    1.0 + gross_mark - cost_bps / 10_000.0
                )
        else:
            marked += STAKE_USD * len(positions)
        peak = max(peak, marked)
        max_dd = max(max_dd, peak - marked)

    if positions:
        raise ValueError("stock fixed-horizon simulation ended with open positions")
    return {
        "net_pnl_usd": cash - STARTING_CASH_USD,
        "trade_count": len(trades),
        "long_count": sum(int(x["side"]) == 1 for x in trades),
        "short_count": sum(int(x["side"]) == -1 for x in trades),
        "win_rate": (
            sum(float(x["pnl_usd"]) > 0 for x in trades) / len(trades)
            if trades else 0.0
        ),
        "expectancy_usd_per_trade": (
            sum(float(x["pnl_usd"]) for x in trades) / len(trades)
            if trades else 0.0
        ),
        "max_marked_drawdown_usd": max_dd,
        "estimated_total_round_trip_cost_usd":
            len(trades) * STAKE_USD * cost_bps / 10_000.0,
    }


def build_stock_ml_tournament(
    source_root: Path,
    *,
    as_of: datetime,
) -> dict[str, object]:
    checked = as_of.astimezone(timezone.utc)
    datasets, timeline, baseline = _load(source_root, as_of=checked)
    rows, frames = _build_rows(datasets, timeline)
    results = {}

    for horizon in HORIZONS:
        train, validation, test, train_cut, validation_cut = _split(
            rows,
            n=len(timeline),
            horizon=horizon,
        )
        target = f"target_{horizon}"
        model_results = {}
        for model_name in MODEL_NAMES:
            model = _model(model_name)
            model.fit(train[list(FEATURES)].to_numpy(), train[target].to_numpy())
            val_predictions = model.predict(validation[list(FEATURES)].to_numpy())
            threshold_reviews = {
                str(threshold): _simulate(
                    validation,
                    val_predictions,
                    horizon=horizon,
                    threshold=threshold,
                    cost_bps=COST_SCENARIOS[
                        "illustrative_base_equity_friction"
                    ],
                    frames=frames,
                )
                for threshold in THRESHOLDS
            }
            eligible = [
                (threshold, threshold_reviews[str(threshold)])
                for threshold in THRESHOLDS
                if int(threshold_reviews[str(threshold)]["trade_count"])
                >= MIN_VALIDATION_TRADES
            ]
            if eligible:
                threshold, val_result = max(
                    eligible,
                    key=lambda item: (
                        float(item[1]["net_pnl_usd"]),
                        float(item[1]["expectancy_usd_per_trade"]),
                        -item[0],
                    ),
                )
            else:
                threshold = THRESHOLDS[0]
                val_result = threshold_reviews[str(threshold)]

            combined = pd.concat([train, validation], ignore_index=True)
            final_model = _model(model_name)
            final_model.fit(
                combined[list(FEATURES)].to_numpy(),
                combined[target].to_numpy(),
            )
            test_predictions = final_model.predict(
                test[list(FEATURES)].to_numpy()
            )
            model_results[model_name] = {
                "selected_threshold_from_validation_only": threshold,
                "selected_validation_result": val_result,
                "descriptive_untouched_test_by_cost": {
                    scenario: _simulate(
                        test,
                        test_predictions,
                        horizon=horizon,
                        threshold=threshold,
                        cost_bps=cost,
                        frames=frames,
                    )
                    for scenario, cost in COST_SCENARIOS.items()
                },
                "automatic_paper_promotion": False,
            }

        results[str(horizon)] = {
            "train_rows": len(train),
            "validation_rows": len(validation),
            "descriptive_test_rows": len(test),
            "train_cut_core_bar_index": train_cut,
            "validation_cut_core_bar_index": validation_cut,
            "models": model_results,
        }

    return {
        "kind": "PHASE162_LONG_HORIZON_US_EQUITY_ML_TOURNAMENT",
        "symbols": list(SYMBOLS),
        "feed": "alpaca_equity_iex",
        "verified_core_bars_per_asset": len(timeline),
        "source_manifest_sha256": baseline["source_manifest_sha256"],
        "feature_names": list(FEATURES),
        "horizons_in_verified_core_bars": list(HORIZONS),
        "cost_scenarios_round_trip_bps": COST_SCENARIOS,
        "purged_chronological_boundaries": True,
        "validation_only_threshold_selection": True,
        "untouched_test_used_for_model_selection": False,
        "results": results,
        "short_results_are_research_only": True,
        "paper_activation_permitted": False,
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_stock_ml_tournament(
            args.source_root,
            as_of=datetime.now(timezone.utc),
        )
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("stock ML output must be create-only")
        raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps({
            "kind": result["kind"],
            "verified_core_bars_per_asset":
                result["verified_core_bars_per_asset"],
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "PHASE162_LONG_HORIZON_US_EQUITY_ML_TOURNAMENT",
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
