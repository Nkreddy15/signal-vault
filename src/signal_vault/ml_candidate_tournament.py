"""Phase 162 chronological ML candidate tournament for six-crypto history.

This is OFFLINE research only. It never imports broker/order modules, never
submits orders, and never promotes a model to PAPER/LIVE execution.

Design:
- exact 2160 aligned hourly bars for the existing six-crypto research universe
- causal features computed only from information available at each bar close
- next-hour direction is the target
- chronological train/validation/test split, no shuffling
- each model chooses only its confidence threshold on validation from a fixed
  predeclared set, then reports untouched test performance
- one-hour long/short research positions are closed each hour and pay an
  explicit estimated round-trip friction cost
- long/short results are research evidence only; venue/account shorting support
  must be verified separately before execution
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .offline_multimarket_pipeline import combine_historical_archives, read_historical_archive
from .relative_strength_tilt_research import SYMBOLS

HISTORICAL_HOURS = 2160
LOOKBACK = 168
TRAIN_FRAC = 0.60
VALIDATION_FRAC = 0.20

# Fixed before seeing model results. These are research sensitivity inputs,
# not claims about current provider fees/spreads.
ROUND_TRIP_COST_BPS = {
    "illustrative_low_friction": 44.0,   # 2*(15 fee + 1 half-spread + 6 slippage-ish)
    "illustrative_base_friction": 74.0,  # 2*(25 fee + 2 half-spread + 10 slippage)
    "illustrative_high_friction": 132.0, # 2*(40 fee + 6 half-spread + 20 slippage)
}
THRESHOLDS = (0.55, 0.60, 0.65, 0.70)
MIN_VALIDATION_TRADES = 20

FEATURE_NAMES = (
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


@dataclass(frozen=True)
class Observation:
    symbol: str
    time_index: int
    timestamp: str
    features: tuple[float, ...]
    next_return: float


def _dependencies():
    try:
        import numpy as np
        from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError(
            "ML research dependencies missing; install signal-vault[research]"
        ) from exc
    return np, HistGradientBoostingClassifier, RandomForestClassifier, LogisticRegression, Pipeline, StandardScaler


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
    lengths = {len(rows) for rows in datasets.values()}
    if lengths != {HISTORICAL_HOURS}:
        raise ValueError("exact aligned 90-day / 2160-hour history required")

    aligned = None
    for rows in datasets.values():
        stamps = tuple(row.start_utc for row in rows)
        if aligned is None:
            aligned = stamps
        elif stamps != aligned:
            raise ValueError("crypto histories must be exactly clock aligned")
    return datasets


def _ema(values, span: int):
    alpha = 2.0 / (span + 1.0)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1.0 - alpha) * out[-1])
    return out


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(max(0.0, var))


def _safe_return(now: float, before: float) -> float:
    if not math.isfinite(now) or not math.isfinite(before) or before <= 0:
        raise ValueError("invalid historical price")
    return now / before - 1.0


def build_observations(datasets: Mapping[str, Sequence[object]]) -> tuple[Observation, ...]:
    """Build causal per-asset rows using only bar t and earlier values."""
    symbols = tuple(sorted(datasets))
    closes = {s: [float(row.close) for row in datasets[s]] for s in symbols}
    highs = {s: [float(row.high) for row in datasets[s]] for s in symbols}
    lows = {s: [float(row.low) for row in datasets[s]] for s in symbols}
    volumes = {s: [float(row.volume) for row in datasets[s]] for s in symbols}
    ema12 = {s: _ema(closes[s], 12) for s in symbols}
    ema26 = {s: _ema(closes[s], 26) for s in symbols}
    ema24 = {s: _ema(closes[s], 24) for s in symbols}
    ema72 = {s: _ema(closes[s], 72) for s in symbols}

    rows: list[Observation] = []
    for i in range(LOOKBACK, HISTORICAL_HOURS - 1):
        ret24 = {
            s: _safe_return(closes[s][i], closes[s][i - 24])
            for s in symbols
        }
        ordered = sorted(symbols, key=lambda s: (ret24[s], s))
        rank = {
            symbol: (ordered.index(symbol) / max(1, len(symbols) - 1)) * 2.0 - 1.0
            for symbol in symbols
        }
        for symbol in symbols:
            c = closes[symbol]
            one_hour_returns = [
                _safe_return(c[j], c[j - 1])
                for j in range(i - 71, i + 1)
            ]
            vwin = volumes[symbol][i - 23 : i + 1]
            vmean = sum(vwin) / len(vwin)
            vstd = _std(vwin)
            vz = 0.0 if vstd == 0 else (volumes[symbol][i] - vmean) / vstd
            features = (
                _safe_return(c[i], c[i - 1]),
                _safe_return(c[i], c[i - 3]),
                _safe_return(c[i], c[i - 6]),
                _safe_return(c[i], c[i - 12]),
                ret24[symbol],
                _safe_return(c[i], c[i - 48]),
                _safe_return(c[i], c[i - 168]),
                ema12[symbol][i] / ema26[symbol][i] - 1.0,
                ema24[symbol][i] / ema72[symbol][i] - 1.0,
                _std(one_hour_returns[-24:]),
                _std(one_hour_returns),
                (highs[symbol][i] - lows[symbol][i]) / c[i],
                vz,
                rank[symbol],
            )
            if not all(math.isfinite(x) for x in features):
                raise ValueError("nonfinite causal feature")
            next_ret = _safe_return(c[i + 1], c[i])
            rows.append(
                Observation(
                    symbol=symbol,
                    time_index=i,
                    timestamp=datasets[symbol][i].closed_utc.isoformat(),
                    features=features,
                    next_return=next_ret,
                )
            )
    return tuple(rows)


def _split(rows: Sequence[Observation]):
    indices = sorted({row.time_index for row in rows})
    n = len(indices)
    train_cut = indices[int(n * TRAIN_FRAC)]
    val_cut = indices[int(n * (TRAIN_FRAC + VALIDATION_FRAC))]

    train = tuple(row for row in rows if row.time_index < train_cut)
    validation = tuple(row for row in rows if train_cut <= row.time_index < val_cut)
    test = tuple(row for row in rows if row.time_index >= val_cut)
    if not train or not validation or not test:
        raise ValueError("chronological split produced an empty fold")
    return train, validation, test, train_cut, val_cut


def _arrays(rows: Sequence[Observation]):
    np, *_ = _dependencies()
    X = np.asarray([row.features for row in rows], dtype=float)
    y = np.asarray([1 if row.next_return > 0 else 0 for row in rows], dtype=int)
    return X, y


def _models():
    np, HGB, RF, LR, Pipeline, StandardScaler = _dependencies()
    return {
        "logistic_l2_v1": Pipeline([
            ("scale", StandardScaler()),
            ("model", LR(
                C=1.0,
                penalty="l2",
                solver="lbfgs",
                max_iter=2000,
                random_state=42,
            )),
        ]),
        "random_forest_v1": RF(
            n_estimators=300,
            max_depth=7,
            min_samples_leaf=12,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
        ),
        "hist_gradient_boosting_v1": HGB(
            learning_rate=0.05,
            max_iter=250,
            max_leaf_nodes=15,
            min_samples_leaf=20,
            l2_regularization=1.0,
            random_state=42,
        ),
    }


def _evaluate(rows: Sequence[Observation], p_up, threshold: float, cost_bps: float):
    if len(rows) != len(p_up):
        raise ValueError("prediction/observation length mismatch")
    cost = cost_bps / 10_000.0
    trades = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    gross_sum = 0.0
    net_sum = 0.0
    winners = 0
    long_count = 0
    short_count = 0
    for row, prob in zip(rows, p_up):
        prob = float(prob)
        if prob >= threshold:
            side = 1.0
            long_count += 1
        elif prob <= 1.0 - threshold:
            side = -1.0
            short_count += 1
        else:
            continue
        gross = side * row.next_return
        net = gross - cost
        gross_sum += gross
        net_sum += net
        equity *= 1.0 + net
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
        if net > 0:
            winners += 1
        trades.append(net)

    trade_count = len(trades)
    avg = net_sum / trade_count if trade_count else 0.0
    if trade_count > 1:
        sd = _std(trades)
        per_trade_sharpe = 0.0 if sd == 0 else avg / sd * math.sqrt(trade_count)
    else:
        per_trade_sharpe = 0.0

    return {
        "trade_count": trade_count,
        "long_count": long_count,
        "short_count": short_count,
        "gross_return_sum": gross_sum,
        "estimated_round_trip_cost_bps": cost_bps,
        "estimated_cost_return_sum": cost * trade_count,
        "net_return_sum": net_sum,
        "compounded_net_return": equity - 1.0,
        "win_rate": winners / trade_count if trade_count else 0.0,
        "expectancy_per_trade": avg,
        "max_drawdown_fraction": max_dd,
        "per_trade_sharpe_like": per_trade_sharpe,
    }


def _pass(result: Mapping[str, object]) -> bool:
    return (
        int(result["trade_count"]) >= 20
        and float(result["net_return_sum"]) > 0.0
        and float(result["expectancy_per_trade"]) > 0.0
        and float(result["max_drawdown_fraction"]) <= 0.10
    )


def build_tournament(folder: Path) -> dict[str, object]:
    datasets = _load(folder)
    observations = build_observations(datasets)
    train, validation, test, train_cut, val_cut = _split(observations)
    X_train, y_train = _arrays(train)
    X_val, _ = _arrays(validation)
    X_test, _ = _arrays(test)

    results = {}
    for name, model in _models().items():
        model.fit(X_train, y_train)
        p_val = model.predict_proba(X_val)[:, 1]

        threshold_reviews = {}
        for threshold in THRESHOLDS:
            r = _evaluate(
                validation,
                p_val,
                threshold,
                ROUND_TRIP_COST_BPS["illustrative_base_friction"],
            )
            threshold_reviews[str(threshold)] = r

        eligible = [
            (threshold, threshold_reviews[str(threshold)])
            for threshold in THRESHOLDS
            if int(threshold_reviews[str(threshold)]["trade_count"]) >= MIN_VALIDATION_TRADES
        ]
        if eligible:
            chosen_threshold, chosen_validation = max(
                eligible,
                key=lambda item: (
                    float(item[1]["net_return_sum"]),
                    float(item[1]["expectancy_per_trade"]),
                    -item[0],
                ),
            )
        else:
            chosen_threshold = THRESHOLDS[0]
            chosen_validation = threshold_reviews[str(chosen_threshold)]

        # Retrain the SAME model family on chronological train+validation after
        # threshold selection. Untouched test remains unseen until evaluation.
        combined = train + validation
        X_combined, y_combined = _arrays(combined)
        model.fit(X_combined, y_combined)
        p_test = model.predict_proba(X_test)[:, 1]

        test_by_cost = {
            label: _evaluate(test, p_test, chosen_threshold, bps)
            for label, bps in ROUND_TRIP_COST_BPS.items()
        }
        results[name] = {
            "validation_threshold_reviews_base_friction": threshold_reviews,
            "selected_threshold_from_validation_only": chosen_threshold,
            "selected_validation_result": chosen_validation,
            "untouched_test_by_cost_scenario": test_by_cost,
            "passes_base_test_screen": _pass(
                test_by_cost["illustrative_base_friction"]
            ),
            "automatic_paper_promotion": False,
        }

    return {
        "kind": "PHASE162_SIX_CRYPTO_CHRONOLOGICAL_ML_CANDIDATE_TOURNAMENT",
        "historical_hours_per_asset": HISTORICAL_HOURS,
        "assets": sorted(datasets),
        "feature_names": list(FEATURE_NAMES),
        "feature_lookback_hours": LOOKBACK,
        "observation_count": len(observations),
        "chronological_split": {
            "train_rows": len(train),
            "validation_rows": len(validation),
            "untouched_test_rows": len(test),
            "train_end_time_index_exclusive": train_cut,
            "validation_end_time_index_exclusive": val_cut,
            "shuffled": False,
        },
        "predeclared_confidence_thresholds": list(THRESHOLDS),
        "estimated_round_trip_cost_bps": ROUND_TRIP_COST_BPS,
        "models": results,
        "research_position_semantics":
            "one-hour long-or-short directional research positions; shorting is NOT execution authorization",
        "model_selection_from_untouched_test": False,
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

        summary = {
            "kind": result["kind"],
            "historical_hours_per_asset": result["historical_hours_per_asset"],
            "assets": result["assets"],
            "chronological_split": result["chronological_split"],
            "model_summaries": {
                name: {
                    "selected_threshold_from_validation_only":
                        detail["selected_threshold_from_validation_only"],
                    "base_test":
                        detail["untouched_test_by_cost_scenario"][
                            "illustrative_base_friction"
                        ],
                    "passes_base_test_screen": detail["passes_base_test_screen"],
                }
                for name, detail in result["models"].items()
            },
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }
        print(json.dumps(summary, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "PHASE162_SIX_CRYPTO_CHRONOLOGICAL_ML_CANDIDATE_TOURNAMENT",
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "broker_order_submission": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
