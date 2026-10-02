"""Phase 162 deployable six-crypto ML screen aligned to the 72h forward bootstrap.

The earlier broader tournament included a 168h return feature. This companion
screen deliberately removes that feature so every signal input can be rebuilt
from the existing prospective six-crypto collector's 72-hour bootstrap plus
new contiguous observations.

OFFLINE historical research only. No provider access and no orders.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from .multi_horizon_ml_tournament import (
    COST_SCENARIOS,
    FEATURES,
    HISTORICAL_HOURS,
    MAX_POSITIONS,
    MIN_VALIDATION_TRADES,
    MODEL_NAMES,
    STAKE_USD,
    STARTING_CASH_USD,
    THRESHOLDS,
    TRAIN_CUT,
    VALIDATION_CUT,
    _build_rows,
    _load,
    _model,
    _passive,
    _shared_portfolio,
)

HORIZON = 48
MAX_FEATURE_LOOKBACK_HOURS = 72
DEPLOYABLE_FEATURES = tuple(
    feature for feature in FEATURES if feature != "ret_168h"
)


def _split(rows: pd.DataFrame):
    target = f"target_{HORIZON}h"
    clean = rows.dropna(subset=[*DEPLOYABLE_FEATURES, target]).copy()
    train = clean[clean.time_index < TRAIN_CUT - HORIZON]
    validation = clean[
        (clean.time_index >= TRAIN_CUT)
        & (clean.time_index < VALIDATION_CUT - HORIZON)
    ]
    holdout = clean[clean.time_index >= VALIDATION_CUT]
    if train.empty or validation.empty or holdout.empty:
        raise ValueError("deployable purged split is empty")
    return train, validation, holdout


def build_deployable_screen(folder: Path) -> dict[str, object]:
    datasets = _load(folder)
    rows, frames = _build_rows(datasets)
    train, validation, holdout = _split(rows)
    target = f"target_{HORIZON}h"
    models = {}

    for model_name in MODEL_NAMES:
        model = _model(model_name)
        model.fit(
            train[list(DEPLOYABLE_FEATURES)].to_numpy(),
            train[target].to_numpy(),
        )
        validation_predictions = model.predict(
            validation[list(DEPLOYABLE_FEATURES)].to_numpy()
        )
        threshold_reviews = {
            str(threshold): _shared_portfolio(
                validation,
                validation_predictions,
                horizon=HORIZON,
                threshold=threshold,
                cost_bps=COST_SCENARIOS["illustrative_base_friction"],
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
            threshold, validation_result = max(
                eligible,
                key=lambda item: (
                    float(item[1]["net_pnl_usd"]),
                    float(item[1]["expectancy_usd_per_trade"]),
                    -item[0],
                ),
            )
        else:
            threshold = THRESHOLDS[0]
            validation_result = threshold_reviews[str(threshold)]

        combined = pd.concat([train, validation], ignore_index=True)
        final_model = _model(model_name)
        final_model.fit(
            combined[list(DEPLOYABLE_FEATURES)].to_numpy(),
            combined[target].to_numpy(),
        )
        holdout_predictions = final_model.predict(
            holdout[list(DEPLOYABLE_FEATURES)].to_numpy()
        )
        holdout_by_cost = {
            label: _shared_portfolio(
                holdout,
                holdout_predictions,
                horizon=HORIZON,
                threshold=threshold,
                cost_bps=cost_bps,
                frames=frames,
            )
            for label, cost_bps in COST_SCENARIOS.items()
        }
        models[model_name] = {
            "selected_threshold_from_validation_only": threshold,
            "selected_validation_result": validation_result,
            "descriptive_holdout_by_cost": holdout_by_cost,
            "validation_supported": (
                int(validation_result["trade_count"]) >= MIN_VALIDATION_TRADES
                and float(validation_result["net_pnl_usd"]) > 0
                and float(validation_result["expectancy_usd_per_trade"]) > 0
            ),
            "automatic_paper_promotion": False,
        }

    passive = {
        label: _passive(
            holdout,
            horizon=HORIZON,
            cost_bps=cost_bps,
            frames=frames,
        )
        for label, cost_bps in COST_SCENARIOS.items()
    }

    supported = [
        name for name, result in models.items()
        if result["validation_supported"]
        and all(
            float(result["descriptive_holdout_by_cost"][scenario]["net_pnl_usd"]) > 0
            for scenario in COST_SCENARIOS
        )
    ]

    return {
        "kind": "PHASE162_DEPLOYABLE_72H_FEATURE_CRYPTO_ML_SCREEN",
        "assets": sorted(datasets),
        "historical_hours_per_asset": HISTORICAL_HOURS,
        "horizon_hours": HORIZON,
        "feature_names": list(DEPLOYABLE_FEATURES),
        "maximum_feature_lookback_hours": MAX_FEATURE_LOOKBACK_HOURS,
        "compatible_with_existing_72h_forward_bootstrap": True,
        "purged_chronological_boundaries": True,
        "validation_only_threshold_selection": True,
        "holdout_is_descriptive_not_model_selection": True,
        "portfolio": {
            "starting_cash_usd": STARTING_CASH_USD,
            "stake_usd": STAKE_USD,
            "max_positions": MAX_POSITIONS,
        },
        "cost_scenarios_round_trip_bps": COST_SCENARIOS,
        "models": models,
        "validation_supported_and_holdout_positive_all_costs": supported,
        "passive_holdout_by_cost": passive,
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
        result = build_deployable_screen(args.folder)
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("output must be create-only")
        raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps({
            "kind": result["kind"],
            "supported_candidates":
                result["validation_supported_and_holdout_positive_all_costs"],
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "PHASE162_DEPLOYABLE_72H_FEATURE_CRYPTO_ML_SCREEN",
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
