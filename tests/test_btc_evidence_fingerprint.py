"""Original BTC tree fingerprint is read-only and excludes only sidecar child."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from signal_vault.btc_evidence_fingerprint import (
    BtcEvidencePermissionError,fingerprint_btc_evidence_tree,
    restrict_btc_evidence_permissions,
)


class BtcEvidenceFingerprintTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.journal=self.root/"observations.sqlite3"
        self.journal.write_bytes(b"btc-journal-v1")
        self.journal.chmod(0o600)
        nested=self.root/"cloud-shadow-receipts"
        nested.mkdir(mode=0o700)
        self.shadow=nested/"shadow.json"
        self.shadow.write_bytes(b'{"safe":true}\n')
        self.shadow.chmod(0o600)
        self.side=self.root/"isolated-six-crypto-prospective"

    def test_stable_original_tree_same_digest_and_zero_writes(self):
        before={
            p.relative_to(self.root).as_posix():p.read_bytes()
            for p in self.root.rglob("*") if p.is_file()
        }
        one=fingerprint_btc_evidence_tree(
            self.root,excluded_sidecar_name=self.side.name)
        two=fingerprint_btc_evidence_tree(
            self.root,excluded_sidecar_name=self.side.name)
        self.assertEqual(one,two)
        self.assertEqual(len(one["tree_sha256"]),64)
        self.assertEqual(one["file_count"],2)
        self.assertGreater(one["total_file_bytes"],0)
        self.assertEqual(one["network_requests"],"NONE")
        self.assertEqual(one["credential_access"],"NONE")
        self.assertEqual(one["filesystem_mutation"],"NONE")
        after={
            p.relative_to(self.root).as_posix():p.read_bytes()
            for p in self.root.rglob("*") if p.is_file()
        }
        self.assertEqual(before,after)

    def test_sidecar_bytes_are_deliberately_excluded_but_BTC_byte_changes_are_detected(self):
        initial=fingerprint_btc_evidence_tree(
            self.root,excluded_sidecar_name=self.side.name)
        self.side.mkdir(mode=0o700)
        receipt=self.side/"new-sidecar-receipt.json"
        receipt.write_bytes(b"sidecar-only")
        receipt.chmod(0o600)
        after_sidecar=fingerprint_btc_evidence_tree(
            self.root,excluded_sidecar_name=self.side.name)
        self.assertEqual(initial["tree_sha256"],after_sidecar["tree_sha256"])
        self.journal.write_bytes(b"btc-journal-CHANGED")
        self.journal.chmod(0o600)
        changed=fingerprint_btc_evidence_tree(
            self.root,excluded_sidecar_name=self.side.name)
        self.assertNotEqual(initial["tree_sha256"],changed["tree_sha256"])

    def test_mode_only_repair_preserves_bytes_and_excludes_sidecar(self):
        nested=self.root/"cloud-shadow-receipts"
        self.journal.chmod(0o644)
        nested.chmod(0o755)
        self.side.mkdir(mode=0o755)
        side_file=self.side/"side.json"
        side_file.write_bytes(b"sidecar-preserve")
        side_file.chmod(0o644)
        before_journal=self.journal.read_bytes()
        before_shadow=self.shadow.read_bytes()
        repaired=restrict_btc_evidence_permissions(
            self.root,excluded_sidecar_name=self.side.name)
        self.assertEqual(self.journal.read_bytes(),before_journal)
        self.assertEqual(self.shadow.read_bytes(),before_shadow)
        self.assertEqual(self.journal.stat().st_mode&0o777,0o600)
        self.assertEqual(nested.stat().st_mode&0o777,0o700)
        self.assertEqual(self.side.stat().st_mode&0o777,0o755)
        self.assertEqual(side_file.stat().st_mode&0o777,0o644)
        self.assertEqual(side_file.read_bytes(),b"sidecar-preserve")
        self.assertTrue(any(x["path"]=="observations.sqlite3" for x in repaired))
        fingerprint_btc_evidence_tree(
            self.root,excluded_sidecar_name=self.side.name)

    def test_symlink_insecure_permissions_and_invalid_exclusion_fail_closed(self):
        bad=self.root/"bad-link"
        bad.symlink_to(self.journal)
        with self.assertRaises(ValueError):
            fingerprint_btc_evidence_tree(
                self.root,excluded_sidecar_name=self.side.name)
        bad.unlink()
        self.journal.chmod(0o644)
        with self.assertRaises(PermissionError):
            fingerprint_btc_evidence_tree(
                self.root,excluded_sidecar_name=self.side.name)
        self.journal.chmod(0o600)
        for invalid in ("","..","nested/child","nested\\child"):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                fingerprint_btc_evidence_tree(
                    self.root,excluded_sidecar_name=invalid)


if __name__=="__main__":
    unittest.main()
