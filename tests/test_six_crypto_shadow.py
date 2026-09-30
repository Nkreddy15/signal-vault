"""Source-verified 6*4*2 predeclared FLAT/HELD shadow: NO external orders."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from signal_vault.crypto_universe_forward import (
    CRYPTO_SIX,collect_six_crypto_once,universe_status,
)
from signal_vault.railway_universe_cron import universe_railway_once,KEY,SECRET,MOUNT
from signal_vault.six_crypto_shadow import (
    FOLDER,inspect_six_crypto_shadow,archive_six_crypto_shadow,
)
from test_crypto_universe_forward import FixtureSixCryptoProvider,FIRST,HOUR


class VerifiedSixSymbolShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"isolated-data-only"
        self.root.mkdir(mode=0o700)
        self.source=FixtureSixCryptoProvider()
        self.provider_calls=0

    def factory(self):
        self.provider_calls+=1
        return self.source

    def observe(self,stamp):
        return collect_six_crypto_once(
            root=self.root,now=stamp,provider_factory=self.factory)

    def test_historical_bootstrap_cannot_emit_retrospective_actions(self):
        self.assertEqual(inspect_six_crypto_shadow(root=self.root)["status"],
                         "NO_GENUINE_PROSPECTIVE_SIX_MARKET_HOUR_TO_EVALUATE")
        self.observe(FIRST)
        self.assertEqual(universe_status(root=self.root)[
            "current_segment_independent_prospective_hours"],0)
        no=archive_six_crypto_shadow(root=self.root)
        self.assertEqual(no["status"],
                         "NO_NEW_PROSPECTIVE_HOUR_NO_RETROSPECTIVE_SHADOW")
        self.assertEqual(no["network_requests"],"NONE")
        self.assertFalse((self.root/FOLDER).exists())
        self.assertEqual(self.provider_calls,1)

    def test_48_flat_and_held_predeclared_decisions_from_first_real_six_hour(self):
        self.observe(FIRST)
        self.observe(FIRST+HOUR)
        old_calls=self.provider_calls
        report=inspect_six_crypto_shadow(root=self.root)
        self.assertEqual(self.provider_calls,old_calls)
        self.assertEqual(report["kind"],"OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY")
        self.assertEqual(report["current_segment_distinct_prospective_UTC_hours"],1)
        self.assertEqual(report["current_segment_prospective_asset_bars"],6)
        self.assertEqual(report["segment_index"],1)
        self.assertEqual(len(report["asset_reviews"]),6)
        self.assertEqual(set(report["asset_reviews"]),set(CRYPTO_SIX))
        self.assertEqual(len(report["predeclared_flat_and_held_hypothetical_decisions"]),6)
        for sym in CRYPTO_SIX:
            review=report["asset_reviews"][sym]
            self.assertEqual(review["historical_warmup_bars"],72)
            self.assertEqual(review["genuinely_prospective_observed_bars"],1)
            versions=report["predeclared_flat_and_held_hypothetical_decisions"][sym]
            self.assertEqual(len(versions),4)
            self.assertEqual(
                versions["cash-v1-predeclared"]["flat"]["hypothetical_action"],"hold")
            self.assertEqual(
                versions["one-allocation-passive-v1-predeclared"][
                    "flat"]["hypothetical_action"],"buy")
            self.assertEqual(
                versions["one-allocation-passive-v1-predeclared"][
                    "already_held"]["hypothetical_action"],"hold")
            for state in versions.values():
                for key in ("flat","already_held"):
                    self.assertEqual(len(state[key]["evidence_sha256"]),64)
                    self.assertEqual(state[key]["broker_order_submission"],"DISABLED")
        self.assertFalse(report["strategy_promoted"])
        self.assertFalse(report["future_edge_established"])
        self.assertEqual(report["network_requests"],"NONE")
        self.assertEqual(report["credential_access"],"NONE")
        self.assertEqual(report["broker_order_submission"],"DISABLED")
        outcome=archive_six_crypto_shadow(root=self.root)
        self.assertEqual(outcome["status"],"NEW_IMMUTABLE_SIX_MARKET_SHADOW")
        file=next((self.root/FOLDER).glob("shadow-hour-*.json"))
        self.assertEqual(file.stat().st_mode&0o777,0o600)
        saved=json.loads(file.read_text())
        self.assertEqual(saved,report)
        self.assertEqual(saved["latest_universe_source_receipt_SHA256"],
                         universe_status(root=self.root)["last_receipt_sha256"])
        same=archive_six_crypto_shadow(root=self.root)
        self.assertEqual(same["status"],"ALREADY_ARCHIVED_IDENTICAL")
        self.assertEqual(self.provider_calls,old_calls)
        self.assertEqual(len(list((self.root/FOLDER).iterdir())),1)

    def test_two_subsequent_real_hours_preserve_old_immutable_shadow(self):
        self.observe(FIRST)
        self.observe(FIRST+HOUR)
        one=archive_six_crypto_shadow(root=self.root)
        f=next((self.root/FOLDER).glob("*.json"))
        before=f.read_bytes()
        self.observe(FIRST+2*HOUR)
        two=archive_six_crypto_shadow(root=self.root)
        self.assertNotEqual(one["shadow_payload_sha256"],
                            two["shadow_payload_sha256"])
        self.assertEqual(f.read_bytes(),before)
        self.assertEqual(len(list((self.root/FOLDER).glob("*.json"))),2)
        last=inspect_six_crypto_shadow(root=self.root)
        self.assertEqual(last["current_segment_distinct_prospective_UTC_hours"],2)
        self.assertEqual(last["current_segment_prospective_asset_bars"],12)
        self.assertTrue(all(
            q["genuinely_prospective_observed_bars"]==2
            for q in last["asset_reviews"].values()))

    def test_gap_new_baseline_has_no_shadow_and_preserves_prior_shadow_files(self):
        self.observe(FIRST)
        self.observe(FIRST+HOUR)
        archive_six_crypto_shadow(root=self.root)
        prior=next((self.root/FOLDER).iterdir()).read_bytes()
        self.observe(FIRST+4*HOUR)
        latest=inspect_six_crypto_shadow(root=self.root)
        self.assertEqual(latest["status"],
                         "NO_GENUINE_PROSPECTIVE_SIX_MARKET_HOUR_TO_EVALUATE")
        self.assertEqual(archive_six_crypto_shadow(root=self.root)["status"],
                         "NO_NEW_PROSPECTIVE_HOUR_NO_RETROSPECTIVE_SHADOW")
        self.assertEqual(next((self.root/FOLDER).iterdir()).read_bytes(),prior)
        self.observe(FIRST+5*HOUR)
        next_=archive_six_crypto_shadow(root=self.root)
        self.assertEqual(next_["current_segment_distinct_prospective_UTC_hours"],1)
        self.assertEqual(universe_status(root=self.root)["historical_bootstrap_count"],2)

    def test_tampered_source_or_existing_shadow_never_gets_overwritten(self):
        self.observe(FIRST)
        self.observe(FIRST+HOUR)
        first=archive_six_crypto_shadow(root=self.root)
        file=next((self.root/FOLDER).iterdir())
        prior=file.read_bytes()
        file.write_bytes(prior+b"tampered")
        with self.assertRaises(ValueError):
            archive_six_crypto_shadow(root=self.root)
        self.assertEqual(file.read_bytes(),prior+b"tampered")
        file.write_bytes(prior)
        source=sorted((self.root/"hourly-receipts").glob("*.json"))[-1]
        before=source.read_bytes()
        source.write_bytes(before+b"corrupted")
        with self.assertRaises(ValueError):
            inspect_six_crypto_shadow(root=self.root)
        self.assertEqual(self.provider_calls,2)

    def test_railway_adapter_archives_and_duplicate_recovers_without_new_GET(self):
        env={
            MOUNT:str(self.root),"RAILWAY_RUN_UID":"0",
            KEY:"FIXTURE_DATA_KEY_NOT_REAL",
            SECRET:"FIXTURE_DATA_SECRET_NOT_REAL",
        }
        def once(t):
            return universe_railway_once(
                environ=env,expected_root=self.root,now=t,
                provider_factory=self.factory)
        first=once(FIRST)
        self.assertEqual(first["status"],"HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertNotIn("shadow_receipt_status",first)
        second=once(FIRST+HOUR)
        self.assertEqual(second["status"],
                         "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR")
        self.assertEqual(second["shadow_receipt_status"],
                         "NEW_IMMUTABLE_SIX_MARKET_SHADOW")
        self.assertEqual(self.provider_calls,2)
        retry=once(FIRST+HOUR+timedelta(minutes=4))
        self.assertEqual(retry["status"],"SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET")
        self.assertEqual(retry["shadow_receipt_status"],"ALREADY_ARCHIVED_IDENTICAL")
        self.assertEqual(self.provider_calls,2)
        self.assertEqual(retry["broker_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()
