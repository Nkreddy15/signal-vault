"""Immutable logistic-regression confirmation layer for BTC BUY signals.

Research may train a model with scikit-learn, but the paper runtime loads only a
strict JSON coefficient artifact and performs inference with the standard
library. The model can VETO a BUY; it can never manufacture a BUY, override a
SELL, increase size, or bypass Guardian.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from statistics import fmean, pstdev
from typing import Sequence
import json
import math
import os
import tempfile

from .market_data import Bar
from .strategy import Action, StrategySignal

FEATURE_NAMES = (
    "return_1h", "return_3h", "return_6h", "return_12h", "return_24h",
    "ema_gap_12_26", "volatility_24h", "range_1h", "volume_ratio_24h",
)
FEATURE_HISTORY = 27


def _ema(values: Sequence[float], period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for current in values[1:]:
        value = alpha * current + (1.0 - alpha) * value
    return value


def extract_features(bars: Sequence[Bar]) -> tuple[float, ...]:
    """Features use only bars supplied through the latest fully closed bar."""
    if len(bars) < FEATURE_HISTORY:
        raise ValueError("insufficient feature history")
    view = bars[-FEATURE_HISTORY:]
    if any(view[i].start != view[i - 1].close_time for i in range(1, len(view))):
        raise ValueError("ML features require contiguous hourly bars")
    closes = [float(x.close) for x in view]
    volumes = [float(x.volume) for x in view]
    if any(not math.isfinite(x) or x <= 0 for x in closes) or any(not math.isfinite(x) or x < 0 for x in volumes):
        raise ValueError("invalid ML feature inputs")
    latest = closes[-1]

    def ret(hours: int) -> float:
        return latest / closes[-1 - hours] - 1.0

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 24, len(closes))]
    fast = _ema(closes, 12); slow = _ema(closes, 26)
    vol_mean = fmean(volumes[-24:])
    features = (
        ret(1), ret(3), ret(6), ret(12), ret(24),
        fast / slow - 1.0,
        pstdev(log_returns),
        float((view[-1].high - view[-1].low) / view[-1].close),
        (volumes[-1] / vol_mean) if vol_mean > 0 else 0.0,
    )
    if len(features) != len(FEATURE_NAMES) or any(not math.isfinite(x) for x in features):
        raise ValueError("non-finite ML feature")
    return features


@dataclass(frozen=True)
class MlArtifact:
    model_version: str
    dataset_sha256: str
    trained_until_utc: str
    horizon_hours: int
    label_return_threshold: float
    decision_probability_threshold: float
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float

    def __post_init__(self) -> None:
        n = len(FEATURE_NAMES)
        if (not self.model_version.strip() or len(self.dataset_sha256) != 64 or
                any(ch not in "0123456789abcdef" for ch in self.dataset_sha256.lower()) or
                self.feature_names != FEATURE_NAMES or
                any(len(x) != n for x in (self.means, self.scales, self.coefficients)) or
                not 1 <= self.horizon_hours <= 168 or
                not 0 <= self.label_return_threshold <= 0.5 or
                not 0.5 <= self.decision_probability_threshold <= 0.99):
            raise ValueError("invalid ML artifact metadata")
        numbers = (*self.means, *self.scales, *self.coefficients, self.intercept,
                   self.label_return_threshold, self.decision_probability_threshold)
        if any(not math.isfinite(x) for x in numbers) or any(x <= 0 for x in self.scales):
            raise ValueError("invalid ML artifact coefficients")
        try:
            stamp = datetime.fromisoformat(self.trained_until_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid ML training cutoff") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("ML training cutoff requires timezone")

    def fingerprint(self) -> str:
        return sha256(self.to_json_bytes()).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "model_version": self.model_version,
            "dataset_sha256": self.dataset_sha256.lower(),
            "trained_until_utc": self.trained_until_utc,
            "horizon_hours": self.horizon_hours,
            "label_return_threshold": self.label_return_threshold,
            "decision_probability_threshold": self.decision_probability_threshold,
            "feature_names": list(self.feature_names),
            "means": list(self.means), "scales": list(self.scales),
            "coefficients": list(self.coefficients), "intercept": self.intercept,
        }

    def to_json_bytes(self) -> bytes:
        return (json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")) + "\n").encode()

    def probability(self, features: Sequence[float]) -> float:
        if len(features) != len(FEATURE_NAMES):
            raise ValueError("ML feature width mismatch")
        standardized = []
        for x, mean, scale in zip(features, self.means, self.scales):
            if not math.isfinite(float(x)):
                raise ValueError("non-finite ML inference input")
            standardized.append((float(x) - mean) / scale)
        score = self.intercept + sum(c * x for c, x in zip(self.coefficients, standardized))
        if score >= 0:
            z = math.exp(-score); return 1.0 / (1.0 + z)
        z = math.exp(score); return z / (1.0 + z)


def save_artifact(path: str | Path, artifact: MlArtifact) -> str:
    target = Path(path).expanduser(); target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.is_symlink():
        raise ValueError("ML artifact path must not be a symlink")
    data = artifact.to_json_bytes()
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target); os.chmod(target, 0o600)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return sha256(data).hexdigest()


def load_artifact(path: str | Path) -> MlArtifact:
    target = Path(path).expanduser()
    if not target.is_file() or target.is_symlink() or target.stat().st_size > 128 * 1024:
        raise ValueError("invalid ML artifact file")
    raw = json.loads(target.read_text())
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("unsupported ML artifact schema")
    expected = {"schema_version", "model_version", "dataset_sha256", "trained_until_utc",
                "horizon_hours", "label_return_threshold", "decision_probability_threshold",
                "feature_names", "means", "scales", "coefficients", "intercept"}
    if set(raw) != expected:
        raise ValueError("unexpected ML artifact fields")
    return MlArtifact(
        str(raw["model_version"]), str(raw["dataset_sha256"]), str(raw["trained_until_utc"]),
        int(raw["horizon_hours"]), float(raw["label_return_threshold"]),
        float(raw["decision_probability_threshold"]), tuple(raw["feature_names"]),
        tuple(map(float, raw["means"])), tuple(map(float, raw["scales"])),
        tuple(map(float, raw["coefficients"])), float(raw["intercept"]),
    )


def apply_confirmation(signal: StrategySignal, bars: Sequence[Bar], artifact: MlArtifact) -> StrategySignal:
    """Model can only veto BUY; HOLD/SELL bypass model inference entirely.

    This asymmetry is deliberate: a broken or stale ML artifact must never block
    a risk-reducing SELL, and a HOLD signal does not need an ML opinion.
    """
    if signal.action is Action.SELL:
        return replace(signal, explanation=signal.explanation +
                       "; ML confirmation bypassed for risk-reducing SELL")
    if signal.action is Action.HOLD:
        return signal

    # BUY is the only action allowed to depend on ML inference. Any exception
    # here is handled fail-closed by the paper runtime before a draft exists.
    features = extract_features(bars)
    probability = artifact.probability(features)
    tag = (f"{signal.evidence_id}|ml={artifact.fingerprint()}|p={probability:.8f}|"
           f"threshold={artifact.decision_probability_threshold:.8f}|action={signal.action.value}")
    combined = sha256(tag.encode()).hexdigest()
    if probability < artifact.decision_probability_threshold:
        return replace(signal, action=Action.HOLD, evidence_id=combined,
                       explanation=(signal.explanation +
                                    f"; ML confirmation vetoed BUY (p={probability:.4f})"))
    return replace(signal, evidence_id=combined,
                   explanation=signal.explanation +
                   f"; ML confirmation passed BUY (p={probability:.4f})")

