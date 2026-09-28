"""Fail-closed provenance gate for optional ML paper-shadow artifacts.

A trained model is not automatically deployable. The runtime accepts an ML
artifact only when a separate, strict JSON receipt identifies the exact artifact
fingerprint and training dataset. A receipt is evidence of an offline research
promotion decision, not evidence of profitability and never live authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json

from .ml_confirmation import MlArtifact, load_artifact


def _sha256(value: str, label: str) -> str:
    lowered = value.lower()
    if len(lowered) != 64 or any(ch not in "0123456789abcdef" for ch in lowered):
        raise ValueError(f"invalid {label} SHA-256")
    return lowered


@dataclass(frozen=True)
class MlPaperPromotionReceipt:
    artifact_sha256: str
    dataset_sha256: str
    research_report_sha256: str
    promoted_at_utc: str
    scope: str = "PROVIDER_PAPER_SHADOW_ONLY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_sha256", _sha256(self.artifact_sha256, "artifact"))
        object.__setattr__(self, "dataset_sha256", _sha256(self.dataset_sha256, "dataset"))
        object.__setattr__(self, "research_report_sha256", _sha256(
            self.research_report_sha256, "research report"))
        if self.scope != "PROVIDER_PAPER_SHADOW_ONLY":
            raise ValueError("ML promotion receipt has invalid scope")
        try:
            stamp = datetime.fromisoformat(self.promoted_at_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid ML promotion timestamp") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("ML promotion timestamp requires timezone")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "ML_PROVIDER_PAPER_SHADOW_PROMOTION_NOT_LIVE_AUTHORIZATION",
            "scope": self.scope,
            "artifact_sha256": self.artifact_sha256,
            "dataset_sha256": self.dataset_sha256,
            "research_report_sha256": self.research_report_sha256,
            "promoted_at_utc": self.promoted_at_utc,
        }

    def fingerprint(self) -> str:
        data = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        return sha256(data).hexdigest()


def load_promotion_receipt(path: str | Path) -> MlPaperPromotionReceipt:
    target = Path(path).expanduser()
    if not target.is_file() or target.is_symlink() or target.stat().st_size > 64 * 1024:
        raise ValueError("invalid ML promotion receipt file")
    raw = json.loads(target.read_text())
    expected = {"schema_version", "kind", "scope", "artifact_sha256", "dataset_sha256",
                "research_report_sha256", "promoted_at_utc"}
    if not isinstance(raw, dict) or set(raw) != expected or raw.get("schema_version") != 1:
        raise ValueError("unsupported ML promotion receipt schema")
    if raw.get("kind") != "ML_PROVIDER_PAPER_SHADOW_PROMOTION_NOT_LIVE_AUTHORIZATION":
        raise ValueError("invalid ML promotion receipt kind")
    return MlPaperPromotionReceipt(
        artifact_sha256=str(raw["artifact_sha256"]),
        dataset_sha256=str(raw["dataset_sha256"]),
        research_report_sha256=str(raw["research_report_sha256"]),
        promoted_at_utc=str(raw["promoted_at_utc"]),
        scope=str(raw["scope"]),
    )


def load_promoted_paper_artifact(artifact_path: str | Path,
                                 receipt_path: str | Path) -> tuple[MlArtifact, MlPaperPromotionReceipt]:
    artifact = load_artifact(artifact_path)
    receipt = load_promotion_receipt(receipt_path)
    if artifact.fingerprint() != receipt.artifact_sha256:
        raise ValueError("ML artifact fingerprint does not match promotion receipt")
    if artifact.dataset_sha256.lower() != receipt.dataset_sha256:
        raise ValueError("ML artifact dataset does not match promotion receipt")
    return artifact, receipt
