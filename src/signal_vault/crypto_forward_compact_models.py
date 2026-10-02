"""Dependency-light Phase 162 crypto forward model runtime.

This is the deployable inference path for the compact 48h model ensemble.  It
uses only the Python standard library plus existing Signal Vault data contracts:
no pandas, numpy, scikit-learn, broker SDK, credentials, or order code.

The three frozen models were selected using validation only and then refit on
train+validation. Their coefficients are mirrored from:
research/models/phase162_compact_linear_48h_crypto.json

They remain prospective/shadow signals until a separate PAPER readiness decision
explicitly enables an execution adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import stdev
from typing import Mapping, Sequence

from .ensemble_signals import ModelSignal, build_ensemble_opportunities
from .opportunity_engine import Market
from .research_universe import ResearchBar
from .signal_adapters import directional_model_signal


FEATURE_NAMES = (
    "ret_1h",
    "ret_3h",
    "ret_6h",
    "ret_12h",
    "ret_24h",
    "ret_48h",
    "ema12_over_ema26_minus1",
    "ema24_over_ema72_minus1",
    "vol_24h",
    "vol_72h",
    "range_1h",
    "volume_z_24h",
    "cross_section_rank_24h",
)
MINIMUM_COMPLETED_BARS = 73
HORIZON_HOURS = 48
BASE_ROUND_TRIP_COST_RETURN = Decimal("0.0074")
STRUCTURAL_MODEL_WEIGHT = Decimal("0.60")
MODEL_RECEIPT_PATH = "research/models/phase162_compact_linear_48h_crypto.json"


@dataclass(frozen=True)
class FrozenLinearModel:
    name: str
    model_class: str
    threshold_abs_return: float
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    coef: tuple[float, ...]
    intercept: float

    def __post_init__(self) -> None:
        width = len(FEATURE_NAMES)
        if (
            len(self.scaler_mean) != width
            or len(self.scaler_scale) != width
            or len(self.coef) != width
        ):
            raise ValueError("frozen model width differs from feature contract")
        if any(
            not math.isfinite(value)
            for value in (
                *self.scaler_mean,
                *self.scaler_scale,
                *self.coef,
                self.intercept,
                self.threshold_abs_return,
            )
        ):
            raise ValueError("frozen model contains nonfinite values")
        if any(value <= 0 for value in self.scaler_scale):
            raise ValueError("frozen scaler requires positive scales")
        if self.threshold_abs_return <= 0:
            raise ValueError("frozen model threshold must be positive")

    def predict(self, feature_vector: Sequence[float]) -> float:
        if len(feature_vector) != len(FEATURE_NAMES):
            raise ValueError("feature vector width mismatch")
        standardized = []
        for value, mean, scale in zip(
            feature_vector,
            self.scaler_mean,
            self.scaler_scale,
        ):
            if not math.isfinite(float(value)):
                raise ValueError("nonfinite forward feature")
            standardized.append((float(value) - mean) / scale)
        return self.intercept + sum(
            weight * value
            for weight, value in zip(self.coef, standardized)
        )


_SHARED_MEAN = (
    0.0002280440089774328,
    0.0007237368340187627,
    0.0014573131883197409,
    0.0026569793310895094,
    0.004776574847928,
    0.008176735231101783,
    0.0011760494024810584,
    0.0034271305247620554,
    0.004572022730390085,
    0.004779400487519352,
    0.007247668407372191,
    0.010749712457039127,
    1.7852832556786437e-17,
)
_SHARED_SCALE = (
    0.005130341579222432,
    0.008843587370695372,
    0.012334443726546572,
    0.017502727280315385,
    0.025500788364869603,
    0.035541898064234446,
    0.005692364980700099,
    0.011236021150277917,
    0.002061823048882925,
    0.0017803689865944123,
    0.005440356896454378,
    0.99988650661853,
    0.6831300510639733,
)

FROZEN_MODELS = (
    FrozenLinearModel(
        name="huber",
        model_class="HuberRegressor",
        threshold_abs_return=0.008,
        scaler_mean=_SHARED_MEAN,
        scaler_scale=_SHARED_SCALE,
        coef=(
            -0.0006726692841247068,
            -0.0012586489354465215,
            -0.000591056020927473,
            0.0030074175205416108,
            0.0010753949466198393,
            0.0021241338029340507,
            -0.006431333207420783,
            0.0002672274582417607,
            0.006926089310050293,
            -0.005634330454794857,
            0.0011582703615279728,
            -0.00028174764346304895,
            0.00015607942616374453,
        ),
        intercept=0.005108288709738346,
    ),
    FrozenLinearModel(
        name="ridge50",
        model_class="Ridge",
        threshold_abs_return=0.015,
        scaler_mean=_SHARED_MEAN,
        scaler_scale=_SHARED_SCALE,
        coef=(
            -0.0003903603932635611,
            -0.000738191251068086,
            0.00016946209935446278,
            0.004125475545432756,
            0.0006288828010921525,
            -0.0004560065819075715,
            -0.005037105612486892,
            0.005324786364541735,
            0.010876704992778922,
            -0.011252721738470488,
            0.0006900096651193439,
            -0.0003358882089539227,
            -0.0021655001532223015,
        ),
        intercept=0.010583542254280475,
    ),
    FrozenLinearModel(
        name="elasticnet_a0001_l25",
        model_class="ElasticNet",
        threshold_abs_return=0.0125,
        scaler_mean=_SHARED_MEAN,
        scaler_scale=_SHARED_SCALE,
        coef=(
            -0.0,
            -0.0,
            0.0,
            0.0016833506952857538,
            -0.00039377558110157345,
            0.0,
            -0.0,
            0.001936765469019001,
            0.009664430829845385,
            -0.00940083835716796,
            0.0003138909509166652,
            -0.0,
            -0.0018721938548037186,
        ),
        intercept=0.010583542254280475,
    ),
)


def _ret(values: Sequence[float], hours: int) -> float:
    if len(values) <= hours or values[-1 - hours] <= 0:
        raise ValueError("insufficient/invalid return history")
    return values[-1] / values[-1 - hours] - 1.0


def _ema_last(values: Sequence[float], span: int) -> float:
    if not values:
        raise ValueError("EMA requires values")
    alpha = 2.0 / (span + 1.0)
    result = float(values[0])
    for raw in values[1:]:
        result = alpha * float(raw) + (1.0 - alpha) * result
    return result


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        raise ValueError("sample standard deviation requires two values")
    result = float(stdev(values))
    if not math.isfinite(result):
        raise ValueError("nonfinite rolling standard deviation")
    return result


def latest_feature_vectors(
    datasets: Mapping[str, Sequence[ResearchBar]],
) -> tuple[dict[str, tuple[float, ...]], datetime]:
    """Calculate the exact latest compact-model features from completed bars."""
    if not isinstance(datasets, Mapping) or len(datasets) < 2:
        raise ValueError("multiple crypto datasets required")
    symbols = tuple(sorted(datasets))
    reference_starts = None
    feature_parts: dict[str, dict[str, float]] = {}
    close_times = set()

    for symbol in symbols:
        rows = tuple(datasets[symbol])
        if len(rows) < MINIMUM_COMPLETED_BARS:
            raise ValueError("73 completed hourly bars required")
        if any(not isinstance(row, ResearchBar) or row.symbol != symbol for row in rows):
            raise ValueError("mixed/malformed crypto feature history")
        starts = tuple(row.start_utc for row in rows)
        if reference_starts is None:
            reference_starts = starts
        elif starts != reference_starts:
            raise ValueError("crypto feature histories must share one clock")

        closes = [float(row.close) for row in rows]
        highs = [float(row.high) for row in rows]
        lows = [float(row.low) for row in rows]
        volumes = [float(row.volume) for row in rows]
        if any(
            not math.isfinite(value) or value <= 0
            for value in (*closes, *highs, *lows)
        ):
            raise ValueError("invalid crypto OHLC values")
        if any(not math.isfinite(value) or value < 0 for value in volumes):
            raise ValueError("invalid crypto volumes")

        returns_72 = [
            closes[index] / closes[index - 1] - 1.0
            for index in range(len(closes) - 71, len(closes))
        ]
        returns_24 = returns_72[-24:]
        volume_window = volumes[-24:]
        volume_std = _sample_std(volume_window)
        volume_mean = sum(volume_window) / len(volume_window)
        volume_z = (
            0.0
            if volume_std == 0.0
            else (volumes[-1] - volume_mean) / volume_std
        )
        ema12 = _ema_last(closes, 12)
        ema26 = _ema_last(closes, 26)
        ema24 = _ema_last(closes, 24)
        ema72 = _ema_last(closes, 72)
        feature_parts[symbol] = {
            "ret_1h": _ret(closes, 1),
            "ret_3h": _ret(closes, 3),
            "ret_6h": _ret(closes, 6),
            "ret_12h": _ret(closes, 12),
            "ret_24h": _ret(closes, 24),
            "ret_48h": _ret(closes, 48),
            "ema12_over_ema26_minus1": ema12 / ema26 - 1.0,
            "ema24_over_ema72_minus1": ema24 / ema72 - 1.0,
            "vol_24h": _sample_std(returns_24),
            "vol_72h": _sample_std(returns_72),
            "range_1h": (highs[-1] - lows[-1]) / closes[-1],
            "volume_z_24h": volume_z,
        }
        close_times.add(rows[-1].closed_utc.astimezone(timezone.utc))

    if len(close_times) != 1:
        raise ValueError("latest crypto completed bars are not aligned")

    ordered = sorted(
        symbols,
        key=lambda symbol: (
            feature_parts[symbol]["ret_24h"],
            symbol,
        ),
    )
    denominator = max(1, len(symbols) - 1)
    for symbol in symbols:
        feature_parts[symbol]["cross_section_rank_24h"] = (
            ordered.index(symbol) / denominator * 2.0 - 1.0
        )

    vectors = {
        symbol: tuple(
            float(feature_parts[symbol][name])
            for name in FEATURE_NAMES
        )
        for symbol in symbols
    }
    if any(
        not all(math.isfinite(value) for value in vector)
        for vector in vectors.values()
    ):
        raise ValueError("nonfinite compact crypto feature vector")
    return vectors, next(iter(close_times))


def _evidence_id(
    *,
    model: FrozenLinearModel,
    symbol: str,
    predicted_return: float,
    source_receipt_sha256: str,
    feature_close_utc: datetime,
) -> str:
    body = {
        "kind": "PHASE162_COMPACT_CRYPTO_MODEL_SIGNAL_EVIDENCE",
        "model": model.name,
        "model_class": model.model_class,
        "model_receipt_path": MODEL_RECEIPT_PATH,
        "symbol": symbol,
        "predicted_48h_signed_return": format(predicted_return, ".17g"),
        "threshold_abs_return": format(model.threshold_abs_return, ".17g"),
        "source_receipt_sha256": source_receipt_sha256,
        "feature_close_utc": feature_close_utc.isoformat(),
        "estimated_round_trip_cost_return": str(
            BASE_ROUND_TRIP_COST_RETURN
        ),
    }
    return "phase162-compact-crypto-sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_compact_crypto_model_signals(
    datasets: Mapping[str, Sequence[ResearchBar]],
    *,
    source_receipt_sha256: str,
    captured_utc: datetime,
    valid_until_utc: datetime | None = None,
) -> tuple[ModelSignal, ...]:
    """Emit threshold+cost-clearing model opinions for the common ensemble."""
    if (
        not isinstance(source_receipt_sha256, str)
        or len(source_receipt_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in source_receipt_sha256)
    ):
        raise ValueError("canonical source receipt SHA256 required")
    if captured_utc.tzinfo is None or captured_utc.utcoffset() is None:
        raise ValueError("timezone-aware capture time required")
    captured = captured_utc.astimezone(timezone.utc)
    vectors, feature_close = latest_feature_vectors(datasets)
    expiry = (
        valid_until_utc.astimezone(timezone.utc)
        if valid_until_utc is not None
        else feature_close + timedelta(hours=1)
    )
    if expiry <= captured:
        raise ValueError("model signal expiry must follow capture")

    signals = []
    for model in FROZEN_MODELS:
        for symbol, vector in vectors.items():
            predicted = model.predict(vector)
            if abs(predicted) < model.threshold_abs_return:
                continue
            estimated_net = (
                abs(Decimal(format(predicted, ".17g")))
                - BASE_ROUND_TRIP_COST_RETURN
            )
            if estimated_net <= 0:
                continue
            signal = directional_model_signal(
                market=Market.CRYPTO,
                instrument=symbol,
                source_model=model.name,
                strategy_family="phase162_compact_linear_48h_crypto",
                predicted_signed_return=Decimal(
                    format(predicted, ".17g")
                ),
                estimated_round_trip_cost_return=
                    BASE_ROUND_TRIP_COST_RETURN,
                confidence=STRUCTURAL_MODEL_WEIGHT,
                max_loss_return=Decimal("0.05"),
                generated_utc=captured,
                valid_until_utc=expiry,
                horizon_seconds=HORIZON_HOURS * 3600,
                evidence_id=_evidence_id(
                    model=model,
                    symbol=symbol,
                    predicted_return=predicted,
                    source_receipt_sha256=source_receipt_sha256,
                    feature_close_utc=feature_close,
                ),
                correlation_group="crypto-beta",
                paper_long_supported=False,
                paper_short_supported=False,
            )
            if signal is not None:
                signals.append(signal)
    return tuple(signals)


def compact_crypto_ensemble_snapshot(
    datasets: Mapping[str, Sequence[ResearchBar]],
    *,
    source_receipt_sha256: str,
    captured_utc: datetime,
) -> dict[str, object]:
    """Return one no-order multi-model consensus snapshot."""
    signals = build_compact_crypto_model_signals(
        datasets,
        source_receipt_sha256=source_receipt_sha256,
        captured_utc=captured_utc,
    )
    ensemble = build_ensemble_opportunities(
        signals,
        as_of=captured_utc,
        min_independent_models=2,
        min_consensus=Decimal("0.60"),
        min_expected_net_return=Decimal("0.001"),
    )
    return {
        "kind": "PHASE162_COMPACT_CRYPTO_ENSEMBLE_SNAPSHOT_NO_ORDER",
        "model_signal_count": len(signals),
        "model_names": [model.name for model in FROZEN_MODELS],
        "opportunity_count": len(ensemble.opportunities),
        "opportunities": [
            {
                "instrument": item.instrument,
                "direction": item.direction.value,
                "component_models": list(item.component_models),
                "ensemble_consensus": str(item.ensemble_consensus),
                "expected_net_return": str(item.expected_net_return),
                "confidence": str(item.confidence),
                "paper_executable": item.paper_executable,
            }
            for item in ensemble.opportunities
        ],
        "rejected_groups": list(ensemble.rejected_groups),
        "model_receipt_path": MODEL_RECEIPT_PATH,
        "broker_order_submission": "DISABLED",
        "paper_activation_permitted": False,
        "live_trading": "UNAVAILABLE",
    }
