"""Storage audit explains capacity without deleting or rewriting evidence."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from signal_vault.crypto_universe_forward import collect_six_crypto_once
from signal_vault.railway_btc_first_dual_cron import (
    BASENAME,BTC_MINIMUM_FREE_RESERVE_BYTES,
    MAX_NEW_SIDECAR_TICK_BUDGET_BYTES,SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES,
)
from signal_vault.six_crypto_shadow import archive_six_crypto_shadow
from signal_vault.six_crypto_storage_audit import sidecar_storage_audit
from test_six_crypto_forward_scorecard import DeterministicSixSource,FIRST,HOUR


def digest_tree(root:Path):
    return {
        str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }


class SidecarStorageAuditTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.btc=Path(tmp.name)/"forward"
        self.btc.mkdir(mode=0o700)
        self.side=self.btc/BASENAME
        self.provider=DeterministicSixSource()

    def factory(self):
        return self.provider

    def tick(self,stamp,shadow=True):
        result=collect_six_crypto_once(
            root=self.side,now=stamp,provider_factory=self.factory)
        if (shadow and result["status"]==
                "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR"):
            archive_six_crypto_shadow(root=self.side)
        return result

    def test_missing_sidecar_reports_zero_bytes_without_creating_it(self):
        result=sidecar_storage_audit(
            btc_root=self.btc,sidecar_root=self.side)
        self.assertEqual(result["status"],"SIDECAR_NOT_YET_CREATED")
        self.assertEqual(result["sidecar_bytes"],0)
        self.assertFalse(self.side.exists())
        self.assertEqual(result["automatic_pruning"],"DISABLED")
        self.assertEqual(result["evidence_deletion"],"DISABLED")
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_baseline_only_has_no_fake_tick_size_projection_and_no_mutation(self):
        self.side.mkdir(mode=0o700)
        self.tick(FIRST)
        before=digest_tree(self.side)
        result=sidecar_storage_audit(
            btc_root=self.btc,sidecar_root=self.side)
        after=digest_tree(self.side)
        self.assertEqual(before,after)
        self.assertEqual(result["current_segment_prospective_source_hours"],0)
        self.assertEqual(result[
            "projection_status"],
            "WAIT_FOR_FIRST_PROSPECTIVE_RECEIPT_PLUS_SHADOW_PAIR")
        self.assertEqual(result["observed_prospective_receipt_shadow_pair_count"],0)
        self.assertTrue(result["hard_runtime_guard_allows_one_more_tick"])
        self.assertEqual(result["source_168_hours_remaining"],168)
        self.assertEqual(
            result["source_169_hours_remaining_for_168_scored_outcomes"],169)

    def test_actual_receipt_plus_shadow_size_drives_conservative_projection(self):
        self.side.mkdir(mode=0o700)
        self.tick(FIRST)
        self.tick(FIRST+HOUR)
        before=digest_tree(self.side)
        with patch(
            "signal_vault.six_crypto_storage_audit.SOURCE_MILESTONE",2),              patch(
            "signal_vault.six_crypto_storage_audit.SCORED_OUTCOME_SOURCE_HOURS",3):
            result=sidecar_storage_audit(
                btc_root=self.btc,sidecar_root=self.side)
        self.assertEqual(digest_tree(self.side),before)
        self.assertEqual(result["current_segment_prospective_source_hours"],1)
        self.assertEqual(result["observed_prospective_receipt_shadow_pair_count"],1)
        self.assertGreater(result["observed_tick_pair_bytes_max"],0)
        self.assertEqual(result["source_168_hours_remaining"],1)
        self.assertEqual(
            result["source_169_hours_remaining_for_168_scored_outcomes"],2)
        self.assertEqual(
            result["projected_sidecar_bytes_at_169_source_hours_using_largest_observed_tick"],
            result["sidecar_bytes"]+2*result["observed_tick_pair_bytes_max"])
        self.assertTrue(result["projection_is_not_a_guarantee"])
        self.assertEqual(result["automatic_pruning"],"DISABLED")
        self.assertEqual(
            result["original_BTC_files_may_be_deleted_for_sidecar"],"NEVER")

    def test_low_filesystem_space_matches_runtime_BTC_reserve_fail_closed(self):
        self.side.mkdir(mode=0o700)
        self.tick(FIRST)
        low=BTC_MINIMUM_FREE_RESERVE_BYTES+MAX_NEW_SIDECAR_TICK_BUDGET_BYTES-1
        with patch(
            "signal_vault.six_crypto_storage_audit.os.statvfs",
            return_value=SimpleNamespace(f_bavail=low,f_frsize=1)):
            result=sidecar_storage_audit(
                btc_root=self.btc,sidecar_root=self.side)
        self.assertFalse(result["hard_runtime_guard_allows_one_more_tick"])
        self.assertEqual(
            result["status"],"HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK")
        self.assertEqual(result["evidence_deletion"],"DISABLED")

    def test_near_sidecar_cap_warns_without_pruning_existing_bytes(self):
        self.side.mkdir(mode=0o700)
        self.tick(FIRST)
        padding=self.side/"preserved-sidecar-padding.bin"
        existing=sum(p.stat().st_size for p in self.side.rglob("*") if p.is_file())
        target=SIX_MARKET_TOTAL_EVIDENCE_CAP_BYTES-(
            MAX_NEW_SIDECAR_TICK_BUDGET_BYTES//2)
        with padding.open("wb") as stream:
            stream.truncate(target-existing)
        padding.chmod(0o600)
        before=padding.stat().st_size
        result=sidecar_storage_audit(
            btc_root=self.btc,sidecar_root=self.side)
        self.assertFalse(result["hard_runtime_guard_allows_one_more_tick"])
        self.assertEqual(result["status"],
                         "HARD_GUARD_WOULD_SKIP_NEXT_SIDECAR_TICK")
        self.assertEqual(padding.stat().st_size,before)
        self.assertTrue(padding.exists())

    def test_insecure_file_and_wrong_child_path_block_without_repair(self):
        self.side.mkdir(mode=0o700)
        self.tick(FIRST)
        receipt=next((self.side/"hourly-receipts").glob("*.json"))
        receipt.chmod(0o644)
        with self.assertRaises(PermissionError):
            sidecar_storage_audit(
                btc_root=self.btc,sidecar_root=self.side)
        self.assertEqual(receipt.stat().st_mode&0o777,0o644)
        with self.assertRaises(ValueError):
            sidecar_storage_audit(
                btc_root=self.btc,
                sidecar_root=self.btc/"some-other-child")


if __name__=="__main__":
    unittest.main()
