"""Phase 162 multi-horizon ML tournament for six-crypto history.

OFFLINE research only. The tournament uses causal features, purged chronological
train/validation boundaries, validation-only threshold selection, one shared
logical $100 portfolio, and a descriptive holdout. It never imports order
submission code and never promotes a model automatically.
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

from .offline_multimarket_pipeline import combine_historical_archives, read_historical_archive
from .relative_strength_tilt_research import SYMBOLS

HISTORICAL_HOURS = 2160
LOOKBACK = 168
TRAIN_CUT = 1362
VALIDATION_CUT = 1760
HORIZONS = (6, 12, 24, 48)
THRESHOLDS = (0.006, 0.008, 0.010, 0.0125, 0.015, 0.020, 0.025, 0.030)
MIN_VALIDATION_TRADES = 10
STARTING_CASH_USD = 100.0
STAKE_USD = 15.0
MAX_POSITIONS = 4
COST_SCENARIOS = {
    "illustrative_low_friction": 42.0,
    "illustrative_base_friction": 74.0,
    "illustrative_high_friction": 132.0,
}
FEATURES = (
    "ret_1h",
    "ret_3h",
    "ret_6h",
    "ret_12h",
    "ret_24h",
    "ret_48h",
    "ret_168h",
    "ema12_over_ema26_minus1",
    "ema24_over_ema72_minus1",
    "vol_24h",
    "vol_72h",
    "range_1h",
    "volume_z_24h",
    "cross_section_rank_24h",
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
        raise ValueError("exact 2160 aligned hourly bars required")
    reference = None
    for rows in datasets.values():
        stamps = tuple(row.start_utc for row in rows)
        if reference is None:
            reference = stamps
        elif stamps != reference:
            raise ValueError("crypto histories must be exactly time aligned")
    return datasets


def _build_rows(datasets) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    frames: dict[str, pd.DataFrame] = {}
    symbols = tuple(sorted(datasets))
    for symbol, rows in datasets.items():
        frame = pd.DataFrame({
            "ts": pd.to_datetime([row.start_utc for row in rows], utc=True),
            "open": [float(row.open) for row in rows],
            "high": [float(row.high) for row in rows],
            "low": [float(row.low) for row in rows],
            "close": [float(row.close) for row in rows],
            "volume": [float(row.volume) for row in rows],
        })
        for horizon in (1, 3, 6, 12, 24, 48, 168):
            frame[f"ret_{horizon}h"] = frame.close.pct_change(horizon)
        frame["ema12"] = frame.close.ewm(span=12, adjust=False).mean()
        frame["ema26"] = frame.close.ewm(span=26, adjust=False).mean()
        frame["ema24"] = frame.close.ewm(span=24, adjust=False).mean()
        frame["ema72"] = frame.close.ewm(span=72, adjust=False).mean()
        frame["ema12_over_ema26_minus1"] = frame.ema12 / frame.ema26 - 1.0
        frame["ema24_over_ema72_minus1"] = frame.ema24 / frame.ema72 - 1.0
        one_hour = frame.close.pct_change()
        frame["vol_24h"] = one_hour.rolling(24).std()
        frame["vol_72h"] = one_hour.rolling(72).std()
        frame["range_1h"] = (frame.high - frame.low) / frame.close
        frame["volume_z_24h"] = (
            (frame.volume - frame.volume.rolling(24).mean())
            / frame.volume.rolling(24).std()
        )
        frames[symbol] = frame

    for index in range(HISTORICAL_HOURS):
        values = {symbol: frames[symbol].loc[index, "ret_24h"] for symbol in symbols}
        if any(pd.isna(value) for value in values.values()):
            for symbol in symbols:
                frames[symbol].loc[index, "cross_section_rank_24h"] = np.nan
            continue
        ordered = sorted(symbols, key=lambda symbol: (values[symbol], symbol))
        for symbol in symbols:
            frames[symbol].loc[index, "cross_section_rank_24h"] = (
                ordered.index(symbol) / (len(symbols) - 1) * 2.0 - 1.0
            )

    combined = []
    for symbol in symbols:
        frame = frames[symbol].copy()
        frame["symbol"] = symbol
        frame["time_index"] = np.arange(len(frame))
        for horizon in HORIZONS:
            # Signal after close[t], execute at open[t+1], exit at close[t+horizon].
            frame[f"target_{horizon}h"] = (
                frame.close.shift(-horizon) / frame.open.shift(-1) - 1.0
            )
        combined.append(frame)
    return pd.concat(combined, ignore_index=True), frames


def _split(rows: pd.DataFrame, horizon: int):
    target = f"target_{horizon}h"
    clean = rows.dropna(subset=[*FEATURES, target]).copy()
    # Purge horizon-length boundary labels so training never consumes validation
    # prices and validation never consumes descriptive-holdout prices.
    train = clean[clean.time_index < TRAIN_CUT - horizon]
    validation = clean[
        (clean.time_index >= TRAIN_CUT)
        & (clean.time_index < VALIDATION_CUT - horizon)
    ]
    holdout = clean[clean.time_index >= VALIDATION_CUT]
    if train.empty or validation.empty or holdout.empty:
        raise ValueError("purged chronological split is empty")
    return train, validation, holdout


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
    raise ValueError("unknown ML model")


MODEL_NAMES = (
    "ridge_v1",
    "random_forest_v1",
    "extra_trees_v1",
    "hist_gradient_boosting_v1",
)


def _shared_portfolio(
    fold: pd.DataFrame,
    predictions,
    *,
    horizon: int,
    threshold: float,
    cost_bps: float,
    frames: dict[str, pd.DataFrame],
) -> dict[str, object]:
    view = fold[["symbol", "time_index", f"target_{horizon}h"]].copy()
    view["prediction"] = np.asarray(predictions, dtype=float)
    candidates: dict[int, list[tuple[str, float, float]]] = {}
    for row in view.itertuples(index=False):
        prediction = float(row.prediction)
        if abs(prediction) >= threshold:
            target = float(getattr(row, f"target_{horizon}h"))
            candidates.setdefault(int(row.time_index), []).append(
                (row.symbol, prediction, target)
            )

    first = int(view.time_index.min())
    last = int(view.time_index.max())
    cash = STARTING_CASH_USD
    positions: dict[str, dict[str, object]] = {}
    trades: list[dict[str, object]] = []
    peak = STARTING_CASH_USD
    max_drawdown = 0.0

    for index in range(first, last + horizon + 1):
        exits = [
            symbol
            for symbol, position in positions.items()
            if int(position["exit_index"]) == index
        ]
        for symbol in exits:
            position = positions.pop(symbol)
            gross = int(position["side"]) * float(position["target_return"])
            net = gross - cost_bps / 10_000.0
            pnl = STAKE_USD * net
            cash += STAKE_USD + pnl
            trades.append({**position, "net_return": net, "pnl_usd": pnl})

        ranked = sorted(
            candidates.get(index, ()),
            key=lambda item: (abs(item[1]), item[0]),
            reverse=True,
        )
        for symbol, prediction, target in ranked:
            if symbol in positions:
                continue
            if len(positions) >= MAX_POSITIONS or cash < STAKE_USD:
                break
            side = 1 if prediction > 0 else -1
            positions[symbol] = {
                "symbol": symbol,
                "side": side,
                "signal_index": index,
                "exit_index": index + horizon,
                "prediction": prediction,
                "target_return": target,
            }
            cash -= STAKE_USD

        marked = cash
        if index < HISTORICAL_HOURS:
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
        max_drawdown = max(max_drawdown, peak - marked)

    if positions:
        raise ValueError("fixed-horizon simulator ended with open positions")
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
            len(trades) * STAKE_USD * cost_bps / 10_000.0
        ),
    }


def _passive(
    fold: pd.DataFrame,
    *,
    horizon: int,
    cost_bps: float,
    frames: dict[str, pd.DataFrame],
) -> dict[str, object]:
    first = int(fold.time_index.min())
    last = int(fold.time_index.max()) + horizon
    cash = STARTING_CASH_USD - STAKE_USD * len(frames)
    entries = {
        symbol: float(frames[symbol].loc[first + 1, "open"])
        for symbol in frames
    }
    peak = STARTING_CASH_USD
    max_drawdown = 0.0
    final = STARTING_CASH_USD
    for index in range(first + 1, last + 1):
        marked = cash
        for symbol in frames:
            net_mark = (
                float(frames[symbol].loc[index, "close"]) / entries[symbol]
                - 1.0
                - cost_bps / 10_000.0
            )
            marked += STAKE_USD * (1.0 + net_mark)
        peak = max(peak, marked)
        max_drawdown = max(max_drawdown, peak - marked)
        final = marked
    return {
        "net_pnl_usd": final - STARTING_CASH_USD,
        "final_equity_usd": final,
        "max_marked_drawdown_usd": max_drawdown,
        "exposure_usd": STAKE_USD * len(frames),
    }


def build_tournament(folder: Path) -> dict[str, object]:
    datasets = _load(folder)
    rows, frames = _build_rows(datasets)
    results: dict[str, object] = {}

    for horizon in HORIZONS:
        train, validation, holdout = _split(rows, horizon)
        target = f"target_{horizon}h"
        horizon_results: dict[str, object] = {}
        for model_name in MODEL_NAMES:
            model = _model(model_name)
            model.fit(train[list(FEATURES)].to_numpy(), train[target].to_numpy())
            validation_predictions = model.predict(
                validation[list(FEATURES)].to_numpy()
            )
            threshold_results = {}
            for threshold in THRESHOLDS:
                threshold_results[str(threshold)] = _shared_portfolio(
                    validation,
                    validation_predictions,
                    horizon=horizon,
                    threshold=threshold,
                    cost_bps=COST_SCENARIOS["illustrative_base_friction"],
                    frames=frames,
                )
            eligible = [
                (threshold, threshold_results[str(threshold)])
                for threshold in THRESHOLDS
                if int(threshold_results[str(threshold)]["trade_count"])
                >= MIN_VALIDATION_TRADES
            ]
            if eligible:
                selected_threshold, selected_validation = max(
                    eligible,
                    key=lambda item: (
                        float(item[1]["net_pnl_usd"]),
                        float(item[1]["expectancy_usd_per_trade"]),
                        -item[0],
                    ),
                )
            else:
                selected_threshold = THRESHOLDS[0]
                selected_validation = threshold_results[str(selected_threshold)]

            # Threshold is frozen before the descriptive holdout is evaluated.
            combined = pd.concat([train, validation], ignore_index=True)
            final_model = _model(model_name)
            final_model.fit(
                combined[list(FEATURES)].to_numpy(), combined[target].to_numpy()
            )
            holdout_predictions = final_model.predict(
                holdout[list(FEATURES)].to_numpy()
            )
            holdout_by_cost = {
                label: _shared_portfolio(
                    holdout,
                    holdout_predictions,
                    horizon=horizon,
                    threshold=selected_threshold,
                    cost_bps=cost_bps,
                    frames=frames,
                )
                for label, cost_bps in COST_SCENARIOS.items()
            }
            horizon_results[model_name] = {
                "validation_threshold_reviews_base_friction": threshold_results,
                "selected_threshold_from_validation_only": selected_threshold,
                "selected_validation_result": selected_validation,
                "descriptive_holdout_by_cost": holdout_by_cost,
                "automatic_paper_promotion": False,
            }

        results[str(horizon)] = {
            "train_rows": len(train),
            "validation_rows": len(validation),
            "descriptive_holdout_rows": len(holdout),
            "models": horizon_results,
            "passive_holdout_by_cost": {
                label: _passive(
                    holdout,
                    horizon=horizon,
                    cost_bps=cost_bps,
                    frames=frames,
                )
                for label, cost_bps in COST_SCENARIOS.items()
            },
        }

    return {
        "kind": "PHASE162_MULTI_HORIZON_CRYPTO_ML_TOURNAMENT",
        "assets": sorted(datasets),
        "historical_hours_per_asset": HISTORICAL_HOURS,
        "feature_names": list(FEATURES),
        "horizons_hours": list(HORIZONS),
        "confidence_return_thresholds": list(THRESHOLDS),
        "purged_chronological_boundaries": True,
        "validation_only_threshold_selection": True,
        "holdout_is_descriptive_not_model_selection": True,
        "cost_scenarios_round_trip_bps": COST_SCENARIOS,
        "portfolio": {
            "starting_cash_usd": STARTING_CASH_USD,
            "stake_usd": STAKE_USD,
            "max_positions": MAX_POSITIONS,
        },
        "results": results,
        "short_results_are_research_only": True,
        "automatic_strategy_ranking": "DISABLED",
        "paper_activation_permitted": False,
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
        print(json.dumps({
            "kind": result["kind"],
            "status": "COMPLETE_OFFLINE_RESEARCH_ONLY",
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "PHASE162_MULTI_HORIZON_CRYPTO_ML_TOURNAMENT",
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
