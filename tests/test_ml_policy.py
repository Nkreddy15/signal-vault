import json
import tempfile
import unittest
from pathlib import Path

from signal_vault.ml_confirmation import FEATURE_NAMES, MlArtifact, save_artifact
from signal_vault.ml_policy import load_promoted_paper_artifact
from signal_vault.paper_worker import _ml_artifact_from_env


class MlPromotionPolicyTests(unittest.TestCase):
    def artifact(self):
        return MlArtifact(
            "test-v1", "a" * 64, "2026-09-28T00:00:00+00:00", 12, 0.0075, 0.65,
            FEATURE_NAMES, (0.0,) * len(FEATURE_NAMES), (1.0,) * len(FEATURE_NAMES),
            (0.0,) * len(FEATURE_NAMES), 1.0,
        )

    def write_pair(self, root: Path, *, artifact=None, artifact_hash=None, dataset=None):
        artifact = artifact or self.artifact()
        artifact_path = root / "model.json"
        save_artifact(artifact_path, artifact)
        receipt = {
            "schema_version": 1,
            "kind": "ML_PROVIDER_PAPER_SHADOW_PROMOTION_NOT_LIVE_AUTHORIZATION",
            "scope": "PROVIDER_PAPER_SHADOW_ONLY",
            "artifact_sha256": artifact_hash or artifact.fingerprint(),
            "dataset_sha256": dataset or artifact.dataset_sha256,
            "research_report_sha256": "b" * 64,
            "promoted_at_utc": "2026-09-28T20:00:00+00:00",
        }
        receipt_path = root / "promotion.json"
        receipt_path.write_text(json.dumps(receipt))
        return artifact_path, receipt_path

    def test_exact_artifact_and_dataset_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, r = self.write_pair(Path(tmp))
            artifact, receipt = load_promoted_paper_artifact(a, r)
            self.assertEqual(artifact.fingerprint(), receipt.artifact_sha256)

    def test_tampered_artifact_or_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, r = self.write_pair(Path(tmp), artifact_hash="c" * 64)
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                load_promoted_paper_artifact(a, r)
        with tempfile.TemporaryDirectory() as tmp:
            a, r = self.write_pair(Path(tmp), dataset="d" * 64)
            with self.assertRaisesRegex(ValueError, "dataset"):
                load_promoted_paper_artifact(a, r)

    def test_runtime_requires_artifact_and_receipt_together(self):
        self.assertIsNone(_ml_artifact_from_env({}))
        with self.assertRaisesRegex(ValueError, "together"):
            _ml_artifact_from_env({"SIGNAL_VAULT_ML_ARTIFACT": "/tmp/x"})
        with self.assertRaisesRegex(ValueError, "together"):
            _ml_artifact_from_env({"SIGNAL_VAULT_ML_PROMOTION_RECEIPT": "/tmp/y"})
