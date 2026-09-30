"""Free-plan one-volume dual cron: BTC first; six-sidecar optional, isolated."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from signal_vault.crypto_universe_forward import universe_status
from signal_vault.railway_btc_first_dual_cron import (
    ACTIVATION_FLAG,ACTIVATION_VALUE,BASENAME,
    combined_btc_first_once,
)
from test_crypto_universe_forward import FixtureSixCryptoProvider,FIRST,HOUR

ROOT=Path(__file__).resolve().parents[1]
BTC_SUCCESS="ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED"


class ExistingBtcFirstNoExtraRailwayVolumeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.btc=Path(temp.name)/"original-attached-btc-volume"
        self.btc.mkdir(mode=0o700)
        self.side=self.btc/BASENAME
        self.env={
            "RAILWAY_VOLUME_MOUNT_PATH":str(self.btc),
            "RAILWAY_RUN_UID":"0",
            "SIGNAL_VAULT_FORWARD_DATA_KEY_ID":"OLD_BTC_DATA_TEST_VALUE_NOT_REAL",
            "SIGNAL_VAULT_FORWARD_DATA_SECRET":"OLD_BTC_DATA_TEST_SECRET_NOT_REAL",
        }
        self.calls=[]
        self.six_source=FixtureSixCryptoProvider()
        self.six_factory_calls=0
        self.sentinel=self.btc/"observations-auto-original.sqlite3"
        self.sentinel.write_bytes(b"ORIGINAL BTC SOURCE PRESERVE ME")

    def fake_btc(self,*,now,environ,expected_root):
        self.calls.append((now,expected_root))
        return {
            "status":BTC_SUCCESS,
            "prospective_observations_verified":3,
            "collector_decision":"ONE_NEW_PROSPECTIVE_CANDLE_RECORDED",
            "broker_order_submission":"DISABLED",
        }

    def six_factory(self):
        self.six_factory_calls+=1
        return self.six_source

    def tick(self,stamp,btc_runner=None,side_clock=None):
        with patch("signal_vault.railway_btc_first_dual_cron.CLOUD_ROOT",self.btc):
            return combined_btc_first_once(
                now=stamp,environ=self.env,btc_root=self.btc,
                sidecar_root=self.side,
                btc_runner=btc_runner or self.fake_btc,
                sidecar_provider_factory=self.six_factory,
                sidecar_clock=(lambda: side_clock or stamp))

    def test_merge_without_one_time_opt_in_never_creates_sidecar_or_touches_BTC(self):
        before=self.sentinel.read_bytes()
        result=self.tick(FIRST)
        self.assertEqual(result["btc_status"],BTC_SUCCESS)
        self.assertEqual(result["btc_prospective_observations_verified"],3)
        self.assertEqual(result["sidecar_status"],"NOT_ACTIVATED")
        self.assertFalse(self.side.exists())
        self.assertEqual(self.six_factory_calls,0)
        self.assertEqual(self.sentinel.read_bytes(),before)
        self.assertFalse(result["new_Railway_volume_created"])
        self.assertFalse(result["new_Railway_service_created"])
        self.assertFalse(result["new_credential_values_required"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_opt_in_one_existing_volume_separate_namespace_true_six_hour_plus_shadow(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        before=self.sentinel.read_bytes()
        baseline=self.tick(FIRST)
        self.assertEqual(baseline["btc_status"],BTC_SUCCESS)
        self.assertEqual(baseline["sidecar_status"],
                         "HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertEqual(baseline["sidecar_recorded_prospective_asset_bars"],0)
        self.assertTrue(self.side.is_dir())
        self.assertEqual(self.side.stat().st_mode&0o777,0o700)
        self.assertEqual(universe_status(root=self.side)[
            "current_segment_independent_prospective_hours"],0)
        captured=self.tick(FIRST+HOUR)
        self.assertEqual(captured["btc_status"],BTC_SUCCESS)
        self.assertEqual(captured["sidecar_status"],
                         "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR")
        self.assertEqual(captured["sidecar_recorded_prospective_asset_bars"],6)
        self.assertEqual(captured["sidecar_recorded_distinct_prospective_UTC_hours"],1)
        self.assertEqual(captured["sidecar_shadow_status"],
                         "NEW_IMMUTABLE_SIX_MARKET_SHADOW")
        self.assertEqual(len(list(self.side.glob("*.sqlite3"))),0)
        self.assertEqual(self.sentinel.read_bytes(),before)
        self.assertEqual(self.six_factory_calls,2)
        self.assertEqual(len(self.calls),2)
        repeat=self.tick(FIRST+HOUR+timedelta(minutes=3))
        self.assertEqual(repeat["sidecar_status"],
                         "SAFE_DUPLICATE_OR_CLOCK_ROLLBACK_NO_GET")
        self.assertEqual(repeat["sidecar_shadow_status"],
                         "ALREADY_ARCHIVED_IDENTICAL")
        self.assertEqual(self.six_factory_calls,2)
        self.assertEqual(self.sentinel.read_bytes(),before)

    def test_bad_optin_and_failed_BTC_never_touch_six_data(self):
        self.env[ACTIVATION_FLAG]="ENABLE_TRADES_OR_UNKNOWN"
        wrong=self.tick(FIRST)
        self.assertEqual(wrong["btc_status"],BTC_SUCCESS)
        self.assertEqual(wrong["sidecar_status"],
                         "BLOCKED_UNRECOGNIZED_SIX_MARKET_OPT_IN")
        self.assertFalse(self.side.exists())
        self.assertEqual(self.six_factory_calls,0)
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        def failed_BTC(**kwargs):
            self.calls.append((kwargs["now"],kwargs["expected_root"]))
            return {"status":"PAUSED_OPERATOR_REVIEW_REQUIRED"}
        bad=self.tick(FIRST+HOUR,btc_runner=failed_BTC)
        self.assertEqual(bad["btc_status"],"PAUSED_OPERATOR_REVIEW_REQUIRED")
        self.assertEqual(bad["sidecar_status"],
                         "SKIPPED_BECAUSE_ORIGINAL_BTC_IS_NOT_HEALTHY")
        self.assertFalse(self.side.exists())
        self.assertEqual(self.six_factory_calls,0)

    def test_bad_sidecar_six_provider_does_not_roll_back_or_mask_healthy_BTC(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        self.six_source=FixtureSixCryptoProvider(missing="ETH/USD")
        before=self.sentinel.read_bytes()
        out=self.tick(FIRST)
        self.assertEqual(out["btc_status"],BTC_SUCCESS)
        self.assertEqual(out["btc_prospective_observations_verified"],3)
        self.assertEqual(out["sidecar_status"],
                         "FAILED_SAFE_OR_BLOCKED_NEW_SIDE_CAR_ONLY")
        self.assertTrue(out["original_BTC_status_preserved"])
        self.assertEqual(self.sentinel.read_bytes(),before)
        self.assertEqual(self.six_factory_calls,1)
        self.assertFalse((self.side/"hourly-receipts").exists())

    def test_symlinked_or_insecure_existing_sidecar_is_never_repaired_by_BTC_worker(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        before=self.sentinel.read_bytes()
        outside=Path(self.btc.parent)/"outside-volume"
        outside.mkdir()
        self.side.symlink_to(outside,target_is_directory=True)
        x=self.tick(FIRST)
        self.assertEqual(x["btc_status"],BTC_SUCCESS)
        self.assertEqual(x["sidecar_status"],
                         "FAILED_SAFE_OR_BLOCKED_NEW_SIDE_CAR_ONLY")
        self.assertEqual(self.six_factory_calls,0)
        self.assertFalse(list(outside.iterdir()))
        self.assertEqual(self.sentinel.read_bytes(),before)
        self.side.unlink()
        self.side.mkdir(mode=0o755)
        x=self.tick(FIRST+HOUR)
        self.assertEqual(x["btc_status"],BTC_SUCCESS)
        self.assertEqual(x["sidecar_status"],
                         "FAILED_SAFE_OR_BLOCKED_NEW_SIDE_CAR_ONLY")
        self.assertEqual(self.side.stat().st_mode&0o777,0o755)
        self.assertEqual(self.six_factory_calls,0)

    def test_no_operator_approval_means_old_production_start_command_unchanged(self):
        docker=(ROOT/"Dockerfile").read_text(encoding="utf-8")
        self.assertIn('"signal_vault.railway_forward_cron", "--once"',docker)
        self.assertNotIn("railway_btc_first_dual_cron",docker)
        self.assertFalse(self.env.get(ACTIVATION_FLAG))
        self.assertEqual(self.sentinel.read_bytes(),
                         b"ORIGINAL BTC SOURCE PRESERVE ME")


if __name__=="__main__":
    unittest.main()
