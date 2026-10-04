"""Prospective/shadow crypto ML signal generation for Phase 162.

This module joins the already-audited six-crypto forward source chain with the
SHA-bound frozen model bundle. It produces ModelSignal records for the common
ensemble/allocator, but it does NOT submit orders or mark candidates PAPER-ready.

A model prediction must clear its frozen validation-selected threshold and the
base friction estimate. Model "confidence" here is a structural ensemble weight,
NOT a calibrated probability of profit.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping

import numpy as np

from .crypto_ml_features import latest_crypto_feature_matrix
from .crypto_model_bundle import load_frozen_crypto_bundle
from .crypto_universe_forward import (
    CRYPTO_SIX,
    _audit_chain,
    _safe_root,
)
from .ensemble_signals import ModelSignal
from .opportunity_engine import Market
from .signal_adapters import directional_model_signal
from .six_crypto_forward_scorecard import _active_datasets

BASE_ROUND_TRIP_COST_RETURN = Decimal("0.0074")
STRUCTURAL_MODEL_WEIGHT = Decimal("0.60")


def _utc(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("source timestamp string required")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("source timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _evidence_id(
    *,
    model_name: str,
    model_sha: str,
    source_receipt_sha: str,
    symbol: str,
    prediction: float,
    feature_close: str,
) -> str:
    body = {
        "kind": "PHASE162_CRYPTO_FORWARD_ML_SIGNAL_EVIDENCE",
        "model_name": model_name,
        "model_sha256": model_sha,
        "source_receipt_sha256": source_receipt_sha,
        "symbol": symbol,
        "predicted_48h_signed_return": format(prediction, ".17g"),
        "feature_close_utc": feature_close,
        "estimated_round_trip_cost_return": str(BASE_ROUND_TRIP_COST_RETURN),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return "phase162-crypto-ml-sha256:" + digest


def build_crypto_forward_ml_signals(
    *,
    source_root: Path,
    bundle_directory: Path,
) -> dict[str, object]:
    """Verify source+models and emit only threshold-clearing shadow signals."""
    root = _safe_root(Path(source_root))
    chain = _audit_chain(root)
    if not chain:
        return {
            "kind": "PHASE162_CRYPTO_FORWARD_ML_SIGNALS_NO_ORDER",
            "status": "NO_VERIFIED_SIX_CRYPTO_SOURCE_CHAIN",
            "signals": (),
            "broker_order_submission": "DISABLED",
            "paper_activation_permitted": False,
            "live_trading": "UNAVAILABLE",
        }

    segment = chain[-1]["segment_index"]
    active = [row for row in chain if row["segment_index"] == segment]
    if (
        not active
        or active[0]["event"] != "HISTORICAL_72H_BOOTSTRAP"
        or len(active) < 2
    ):
        # 72 historical closes alone cannot form vol_72h; one fresh contiguous
        # close is needed to produce the 73rd close.
        return {
            "kind": "PHASE162_CRYPTO_FORWARD_ML_SIGNALS_NO_ORDER",
            "status": "WAITING_FOR_FIRST_PROSPECTIVE_HOUR_TO_COMPLETE_73_CLOSE_FEATURE_WARMUP",
            "signals": (),
            "current_segment_receipts": len(active),
            "broker_order_submission": "DISABLED",
            "paper_activation_permitted": False,
            "live_trading": "UNAVAILABLE",
        }
    if any(
        row["event"] != "ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR"
        for row in active[1:]
    ):
        raise ValueError("current source segment is not contiguous")

    datasets = _active_datasets(active)
    if tuple(sorted(datasets)) != tuple(sorted(CRYPTO_SIX)):
        raise ValueError("forward ML source universe changed")
    symbols, matrix, feature_open_timestamp = latest_crypto_feature_matrix(
        datasets
    )
    manifest, models = load_frozen_crypto_bundle(bundle_directory)

    # latest feature row timestamp is the bar OPEN. Source receipt's closed hour
    # is the bar close and is the decision timestamp boundary.
    latest_receipt = active[-1]
    source_close = _utc(latest_receipt["closed_hour_utc"])
    captured = _utc(latest_receipt["captured_utc"])
    if captured < source_close or captured >= source_close + timedelta(hours=1):
        raise ValueError("latest source capture is not inside its close hour")
    valid_until = source_close + timedelta(hours=1)

    emitted: list[ModelSignal] = []
    predictions: dict[str, dict[str, object]] = {}
    for model_name in sorted(models):
        loaded = models[model_name]
        values = np.asarray(loaded.model.predict(matrix), dtype=float)
        if values.shape != (len(symbols),) or not np.isfinite(values).all():
            raise ValueError("frozen crypto model returned invalid predictions")
        per_symbol = {}
        for symbol, predicted in zip(symbols, values):
            passed = abs(float(predicted)) >= loaded.threshold
            net_after_base = abs(float(predicted)) - float(
                BASE_ROUND_TRIP_COST_RETURN
            )
            per_symbol[symbol] = {
                "predicted_48h_signed_return": float(predicted),
                "frozen_absolute_threshold": loaded.threshold,
                "threshold_passed": passed,
                "estimated_net_directional_return_after_base_cost":
                    net_after_base,
            }
            if not passed or net_after_base <= 0:
                continue
            signal = directional_model_signal(
                market=Market.CRYPTO,
                instrument=symbol,
                source_model=model_name,
                strategy_family="phase162_frozen_48h_crypto_ml",
                predicted_signed_return=Decimal(
                    format(float(predicted), ".17g")
                ),
                estimated_round_trip_cost_return=
                    BASE_ROUND_TRIP_COST_RETURN,
                confidence=STRUCTURAL_MODEL_WEIGHT,
                max_loss_return=Decimal("0.05"),
                generated_utc=captured,
                valid_until_utc=valid_until,
                horizon_seconds=48 * 3600,
                evidence_id=_evidence_id(
                    model_name=model_name,
                    model_sha=loaded.model_sha256,
                    source_receipt_sha=latest_receipt["receipt_sha256"],
                    symbol=symbol,
                    prediction=float(predicted),
                    feature_close=source_close.isoformat(),
                ),
                correlation_group="crypto-beta",
                paper_long_supported=False,
                paper_short_supported=False,
            )
            if signal is not None:
                emitted.append(signal)
        predictions[model_name] = {
            "model_sha256": loaded.model_sha256,
            "threshold": loaded.threshold,
            "per_symbol": per_symbol,
        }

    return {
        "kind": "PHASE162_CRYPTO_FORWARD_ML_SIGNALS_NO_ORDER",
        "status": (
            "MODEL_SIGNALS_EMITTED_FOR_ENSEMBLE"
            if emitted else
            "NO_FROZEN_MODEL_SIGNAL_CLEARED_THRESHOLD_AND_COST"
        ),
        "segment_index": segment,
        "source_receipt_sha256": latest_receipt["receipt_sha256"],
        "source_feature_bar_open_utc": feature_open_timestamp,
        "source_feature_close_utc": source_close.isoformat(),
        "captured_utc": captured.isoformat(),
        "historical_model_source_set_sha256":
            manifest["historical_source_set_sha256"],
        "predictions": predictions,
        "signals": tuple(emitted),
        "signal_count": len(emitted),
        "confidence_semantics":
            "fixed structural ensemble weight; NOT calibrated probability of profit",
        "paper_activation_permitted": False,
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }
