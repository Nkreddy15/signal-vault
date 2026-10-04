"""Frozen Phase 162 crypto model bundle trainer/loader.

The research tournament has already frozen two forward-shadow candidates:
- random_forest_v1, 48h, threshold 0.015
- extra_trees_v1, 48h, threshold 0.0125

This module retrains those SAME fixed model families on all eligible historical
rows after the candidate definitions are frozen, then writes a private
SHA-bound local bundle for prospective/shadow inference.

The bundle is not committed to Git and does not authorize PAPER/LIVE orders.
joblib/pickle is loaded only after the local manifest and model SHA are checked.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor

from .crypto_ml_features import (
    DEPLOYABLE_CRYPTO_FEATURES,
    build_crypto_feature_frames,
)
from .deployable_crypto_ml_tournament import HORIZON, _load


BUNDLE_VERSION = "phase162-crypto-48h-forward-shadow-v1"
FROZEN_CANDIDATES: Mapping[str, Mapping[str, object]] = {
    "random_forest_v1": {
        "threshold": 0.015,
        "model_class": "RandomForestRegressor",
        "params": {
            "n_estimators": 300,
            "max_depth": 8,
            "min_samples_leaf": 10,
            "max_features": 0.7,
            "n_jobs": -1,
            "random_state": 42,
        },
    },
    "extra_trees_v1": {
        "threshold": 0.0125,
        "model_class": "ExtraTreesRegressor",
        "params": {
            "n_estimators": 300,
            "max_depth": 10,
            "min_samples_leaf": 10,
            "max_features": 0.8,
            "n_jobs": -1,
            "random_state": 42,
        },
    },
}


def _private_folder(path: Path, *, create: bool = False) -> Path:
    if create:
        if path.exists() or path.is_symlink():
            raise ValueError("model bundle output directory must be a new path")
        path.mkdir(parents=True, mode=0o700)
        os.chmod(path, 0o700)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError("model bundle directory must be private 0700")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_archives(folder: Path) -> list[dict[str, str]]:
    files = sorted(folder.glob("historical-crypto-*.json"))
    if not files:
        raise ValueError("historical source archives missing")
    return [{"filename": p.name, "sha256": _sha(p)} for p in files]


def _training_table(datasets):
    frames = build_crypto_feature_frames(datasets)
    combined = []
    for symbol in sorted(frames):
        frame = frames[symbol].copy()
        frame["symbol"] = symbol
        source = datasets[symbol]
        frame["target_48h"] = (
            frame.close.shift(-HORIZON) / frame.open.shift(-1) - 1.0
        )
        # Evidence close is the completed feature bar close.
        frame["feature_close_utc"] = [
            row.closed_utc.isoformat() for row in source
        ]
        combined.append(frame)
    rows = pd.concat(combined, ignore_index=True)
    rows = rows.dropna(
        subset=[*DEPLOYABLE_CRYPTO_FEATURES, "target_48h"]
    ).copy()
    if rows.empty:
        raise ValueError("no eligible rows for frozen model training")
    return rows


def _new_model(name: str):
    spec = FROZEN_CANDIDATES[name]
    params = dict(spec["params"])
    if name == "random_forest_v1":
        return RandomForestRegressor(**params)
    if name == "extra_trees_v1":
        return ExtraTreesRegressor(**params)
    raise ValueError("unknown frozen crypto model")


def train_frozen_crypto_bundle(
    historical_folder: Path,
    *,
    output_directory: Path,
) -> dict[str, object]:
    """Train both frozen shadow candidates and create a SHA-bound manifest."""
    source = Path(historical_folder)
    if source.is_symlink() or not source.is_dir():
        raise ValueError("historical source folder required")
    datasets = _load(source)
    rows = _training_table(datasets)
    output = _private_folder(Path(output_directory), create=True)

    X = rows[list(DEPLOYABLE_CRYPTO_FEATURES)].to_numpy(dtype=float)
    y = rows["target_48h"].to_numpy(dtype=float)
    source_archives = _source_archives(source)
    source_digest = hashlib.sha256(
        json.dumps(
            source_archives,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    model_receipts = {}
    for name in sorted(FROZEN_CANDIDATES):
        model = _new_model(name)
        model.fit(X, y)
        target = output / f"{name}.joblib"
        joblib.dump(
            {
                "bundle_version": BUNDLE_VERSION,
                "name": name,
                "features": tuple(DEPLOYABLE_CRYPTO_FEATURES),
                "horizon_hours": HORIZON,
                "threshold": FROZEN_CANDIDATES[name]["threshold"],
                "historical_source_set_sha256": source_digest,
                "sklearn_version": sklearn.__version__,
                "model": model,
            },
            target,
            compress=3,
        )
        os.chmod(target, 0o600)
        model_receipts[name] = {
            "filename": target.name,
            "sha256": _sha(target),
            "threshold": FROZEN_CANDIDATES[name]["threshold"],
            "model_class": FROZEN_CANDIDATES[name]["model_class"],
            "params": FROZEN_CANDIDATES[name]["params"],
        }

    manifest = {
        "kind": "PHASE162_FROZEN_CRYPTO_FORWARD_MODEL_BUNDLE",
        "bundle_version": BUNDLE_VERSION,
        "model_selection_performed_during_bundle_training": False,
        "frozen_candidate_names": sorted(FROZEN_CANDIDATES),
        "horizon_hours": HORIZON,
        "feature_names": list(DEPLOYABLE_CRYPTO_FEATURES),
        "minimum_completed_hourly_closes_for_inference": 73,
        "training_row_count": len(rows),
        "training_feature_close_first_utc": rows["feature_close_utc"].min(),
        "training_feature_close_last_utc": rows["feature_close_utc"].max(),
        "historical_source_archives": source_archives,
        "historical_source_set_sha256": source_digest,
        "sklearn_version": sklearn.__version__,
        "models": model_receipts,
        "prospective_shadow_only": True,
        "paper_activation_permitted": False,
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }
    manifest_path = output / "manifest.json"
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(manifest_path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        **manifest,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
    }


@dataclass(frozen=True)
class LoadedFrozenCryptoModel:
    name: str
    threshold: float
    horizon_hours: int
    features: tuple[str, ...]
    model_sha256: str
    source_set_sha256: str
    model: object


def load_frozen_crypto_bundle(
    bundle_directory: Path,
) -> tuple[dict[str, object], dict[str, LoadedFrozenCryptoModel]]:
    """Verify manifest/model hashes before deserializing locally created models."""
    root = _private_folder(Path(bundle_directory))
    manifest_path = root / "manifest.json"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.stat().st_mode & 0o077
        or manifest_path.stat().st_size > 200_000
    ):
        raise ValueError("invalid private model manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("kind") != "PHASE162_FROZEN_CRYPTO_FORWARD_MODEL_BUNDLE"
        or manifest.get("bundle_version") != BUNDLE_VERSION
        or manifest.get("paper_activation_permitted") is not False
        or manifest.get("broker_order_submission") != "DISABLED"
        or manifest.get("live_trading") != "UNAVAILABLE"
        or manifest.get("feature_names") != list(DEPLOYABLE_CRYPTO_FEATURES)
        or manifest.get("horizon_hours") != HORIZON
        or manifest.get("minimum_completed_hourly_closes_for_inference") != 73
    ):
        raise ValueError("model manifest contract mismatch")
    model_specs = manifest.get("models")
    if not isinstance(model_specs, dict) or set(model_specs) != set(FROZEN_CANDIDATES):
        raise ValueError("model manifest candidate set changed")

    loaded = {}
    for name in sorted(FROZEN_CANDIDATES):
        spec = model_specs[name]
        if not isinstance(spec, dict):
            raise ValueError("invalid model manifest record")
        model_path = root / str(spec.get("filename", ""))
        if (
            model_path.parent.resolve() != root.resolve()
            or model_path.is_symlink()
            or not model_path.is_file()
            or model_path.stat().st_mode & 0o077
            or model_path.stat().st_size > 100_000_000
        ):
            raise ValueError("invalid private model file")
        actual_sha = _sha(model_path)
        if actual_sha != spec.get("sha256"):
            raise ValueError("model file SHA differs from manifest")
        # Deserialization occurs only after path, permissions and SHA checks.
        payload = joblib.load(model_path)
        if (
            not isinstance(payload, dict)
            or payload.get("bundle_version") != BUNDLE_VERSION
            or payload.get("name") != name
            or tuple(payload.get("features", ())) != DEPLOYABLE_CRYPTO_FEATURES
            or payload.get("horizon_hours") != HORIZON
            or payload.get("threshold") != FROZEN_CANDIDATES[name]["threshold"]
            or payload.get("historical_source_set_sha256")
            != manifest.get("historical_source_set_sha256")
            or payload.get("sklearn_version") != manifest.get("sklearn_version")
            or "model" not in payload
        ):
            raise ValueError("deserialized frozen model metadata mismatch")
        loaded[name] = LoadedFrozenCryptoModel(
            name=name,
            threshold=float(payload["threshold"]),
            horizon_hours=HORIZON,
            features=DEPLOYABLE_CRYPTO_FEATURES,
            model_sha256=actual_sha,
            source_set_sha256=str(payload["historical_source_set_sha256"]),
            model=payload["model"],
        )
    return manifest, loaded
