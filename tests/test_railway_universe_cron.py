"""Separate/unactivated six-crypto Railway adapter: strict own mount and DATA vars."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

from signal_vault.railway_universe_cron import (
    KEY, SECRET, MOUNT, mounted_universe_volume,
    universe_railway_preflight, universe_railway_once,
)
from signal_vault.crypto_universe_forward import universe_status
from test_crypto_universe_forward import FixtureSixCryptoProvider,FIRST

HOUR=timedelta(hours=1)


class DedicatedUniverseRailwayAdapterTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)/"new-separate-prospective-universe"
        self.root.mkdir(mode=0o700)
        self.env={
            MOUNT:str(self.root),
            "RAILWAY_RUN_UID":"0",
            KEY:"FIXTURE_DATA_KEY_NEVER_REAL",
            SECRET:"FIXTURE_DATA_SECRET_NEVER_REAL",
        }
        self.provider=FixtureSixCryptoProvider()
        self.factory_count=0

    def factory(self):
        self.factory_count+=1
        return self.provider

    def once(self,now,**kwargs):
        return universe_railway_once(
            environ=self.env,now=now,expected_root=self.root,
            provider_factory=self.factory,**kwargs)

    def test_new_six_crypto_worker_bootstrap_then_true_six_independent_assets(self):
        pre=universe_railway_preflight(
            environ=self.env,expected_root=self.root)
        self.assertEqual(pre["status"],"SEPARATE_SIX_CRYPTO_SOURCE_READY")
        self.assertEqual(pre["network_requests"],"NONE")
        self.assertEqual(self.factory_count,0)
        self.assertNotIn("FIXTURE_DATA",json.dumps(pre))
        self.assertFalse(pre["service_created_by_this_code"])
        first=self.once(FIRST)
        self.assertEqual(first["status"],"HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertFalse(first["old_BTC_collector_modified"])
        self.assertEqual(first["recorded_prospective_asset_bars"],0)
        second=self.once(FIRST+HOUR)
        self.assertEqual(second["status"],
                         "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR")
        self.assertEqual(self.factory_count,2)
        state=universe_status(root=self.root)
        self.assertEqual(state["current_segment_independent_prospective_hours"],1)
        self.assertEqual(state["current_segment_prospective_asset_bar_count"],6)
        self.assertEqual(second["broker_order_submission"],"DISABLED")
        self.assertNotIn("FIXTURE_DATA",json.dumps(second))

    def test_wrong_volume_old_BTC_secrets_generic_credentials_and_uid_all_block(self):
        for changes in (
            {MOUNT:"/var/lib/signal-vault/forward"},
            {MOUNT:"/var/lib/signal-vault/forward-universe"},
            {"RAILWAY_RUN_UID":"1001"},
            {"SIGNAL_VAULT_FORWARD_DATA_KEY_ID":"SHOULD_NOT_USE_OLD_BTC_VAR"},
            {"ALPACA_PAPER_KEY_ID":"DO_NOT_ENABLE_BROKER"},
            {"SIGNAL_VAULT_ENABLE_PAPER_ORDERS":"1"},
            {SECRET:""},
        ):
            with self.subTest(changes=changes):
                env={**self.env,**changes}
                out=universe_railway_once(
                    environ=env,now=FIRST,expected_root=self.root,
                    provider_factory=self.factory)
                self.assertEqual(out["status"],
                                 "BLOCKED_NO_NEW_PROSPECTIVE_EVIDENCE")
                self.assertEqual(out["broker_order_submission"],"DISABLED")
                self.assertEqual(self.factory_count,0)
                self.assertFalse((self.root/"hourly-receipts").exists())
                pre=universe_railway_preflight(
                    environ=env,expected_root=self.root)
                self.assertEqual(pre["status"],"BLOCKED")
                self.assertEqual(pre["network_requests"],"NONE")

    def test_unsafe_volume_and_stale_run_do_not_acquire_provider_credentials(self):
        self.root.chmod(0o755)
        with patch("signal_vault.railway_universe_cron.os.geteuid",return_value=1001):
            result=self.once(FIRST)
        self.assertEqual(result["status"],"BLOCKED_NO_NEW_PROSPECTIVE_EVIDENCE")
        self.assertEqual(self.factory_count,0)
        self.root.chmod(0o700)
        result=self.once(FIRST+timedelta(minutes=20))
        self.assertEqual(result["status"],"SAFE_SKIP_OUTSIDE_FRESH_CLOSED_HOUR_WINDOW")
        self.assertEqual(self.factory_count,0)
        self.assertEqual(universe_status(root=self.root)["all_segments_total_receipts"],0)


    def test_only_real_owner_may_restrict_new_exact_mount_root(self):
        self.root.chmod(0o755)
        with patch("signal_vault.railway_universe_cron.os.geteuid",return_value=0):
            out=self.once(FIRST)
        self.assertEqual(out["status"],"HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertEqual(self.root.stat().st_mode&0o777,0o700)
        self.assertEqual(out["recorded_prospective_asset_bars"],0)
        self.assertFalse(out["old_BTC_collector_modified"])
        self.assertEqual(self.factory_count,1)


if __name__=="__main__":
    unittest.main()
