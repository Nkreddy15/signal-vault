"""Offline training for the immutable ML confirmation artifact.

scikit-learn is imported only here. Runtime inference in ml_confirmation.py has
no sklearn/joblib dependency and never executes serialized Python objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Sequence
import math

from .market_data import Bar, validate_bars
from .ml_confirmation import FEATURE_HISTORY, FEATURE_NAMES, MlArtifact, extract_features


@dataclass(frozen=True)
class MlTrainingConfig:
    horizon_hours: int = 12
    label_return_threshold: float = 0.0075
    decision_probability_threshold: float = 0.65
    model_version: str = "btc-logistic-confirm-v0.1"

    def __post_init__(self) -> None:
        if (not 1 <= self.horizon_hours <= 168 or not 0 <= self.label_return_threshold <= 0.5 or
                not 0.5 <= self.decision_probability_threshold <= 0.99 or not self.model_version.strip()):
            raise ValueError("invalid ML training config")


def build_supervised_samples(bars: Sequence[Bar], *, config: MlTrainingConfig | None = None):
    cfg = config or MlTrainingConfig()
    seq = validate_bars(bars, as_of=bars[-1].close_time if bars else None,
                        min_count=FEATURE_HISTORY + cfg.horizon_hours + 2)
    X=[]; y=[]; cutoffs=[]
    # Feature cutoff i is a fully closed candle. Hypothetical entry is next open;
    # target exit mark is horizon hours after that entry. No future value enters X.
    last_i = len(seq) - cfg.horizon_hours - 1
    for i in range(FEATURE_HISTORY - 1, last_i):
        features = extract_features(seq[:i + 1])
        entry = float(seq[i + 1].open)
        exit_close = float(seq[i + 1 + cfg.horizon_hours].close)
        future_return = exit_close / entry - 1.0
        X.append(features)
        y.append(1 if future_return > cfg.label_return_threshold else 0)
        cutoffs.append(seq[i].close_time)
    if len(set(y)) < 2:
        raise ValueError("training labels need both classes")
    return tuple(X), tuple(y), tuple(cutoffs)


def train_logistic_confirmation(bars: Sequence[Bar], *, dataset_sha256: str,
                                config: MlTrainingConfig | None = None) -> MlArtifact:
    cfg = config or MlTrainingConfig()
    if len(dataset_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in dataset_sha256.lower()):
        raise ValueError("valid training dataset SHA-256 required")
    X, y, cutoffs = build_supervised_samples(bars, config=cfg)
    # Lazy import keeps runtime small and prevents an ML package from becoming an
    # execution dependency.
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    import numpy as np

    matrix = np.asarray(X, dtype=float)
    scaler = StandardScaler().fit(matrix)
    scaled = scaler.transform(matrix)
    model = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs", random_state=0)
    model.fit(scaled, np.asarray(y, dtype=int))
    if model.coef_.shape != (1, len(FEATURE_NAMES)) or model.intercept_.shape != (1,):
        raise ValueError("unexpected logistic model shape")
    values = [*scaler.mean_, *scaler.scale_, *model.coef_[0], model.intercept_[0]]
    if any(not math.isfinite(float(x)) for x in values):
        raise ValueError("non-finite trained ML artifact")
    return MlArtifact(
        cfg.model_version, dataset_sha256.lower(), cutoffs[-1].astimezone(timezone.utc).isoformat(),
        cfg.horizon_hours, cfg.label_return_threshold, cfg.decision_probability_threshold,
        FEATURE_NAMES, tuple(map(float, scaler.mean_)), tuple(map(float, scaler.scale_)),
        tuple(map(float, model.coef_[0])), float(model.intercept_[0]),
    )
