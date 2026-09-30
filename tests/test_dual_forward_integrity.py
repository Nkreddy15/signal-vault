"""Read-only combined BTC + six-market status classification tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.dual_forward_integrity import dual_forward_integrity_status
from signal_vault.railway_btc_first_dual_cron import BASENAME


def btc(*,count=7,start="2026-09-30T02:00:00+00:00",paused=False):
    return {
        "kind":"CLOUD_OFFLINE_GET_ONLY_STATUS",
        "status":"PAUSED" if paused else "READ_ONLY_STATUS_AVAILABLE",
        "durably_paused":paused,
        "verified_collector":{
            "state":"ARCHIVED_INTERNAL_EVIDENCE_VERIFIED",
            "prospective_observations_verified":count,
            "last_anchored_bar_started_utc":start,
            "last_journal_recorded_utc":"2026-09-30T03:08:00+00:00",
            "broker_order_submission":"DISABLED",
        },
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
    }


def side(*,hours=0,latest="2026-09-30T03:00:00+00:00",segment=1,bootstraps=1):
    return {
        "kind":"SIX_CRYPTO_OFFLINE_PROSPECTIVE_SOURCE_CHAIN_STATUS",
        "status":"VERIFIED",
        "symbols":["AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD"],
        "segment_index":segment,
        "latest_hour_utc":latest,
        "last_receipt_sha256":"a"*64,
        "all_segments_total_receipts":hours+bootstraps,
        "current_segment_independent_prospective_hours":hours,
        "current_segment_prospective_asset_bar_count":6*hours,
        "historical_bootstrap_count":bootstraps,
        "ready_for_seven_day_audit":hours>=168,
        "historical_baselines_count_as_prospective":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "broker_order_submission":"DISABLED",
    }


def shadow(*,hours=1):
    return {
        "kind":"OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY",
        "current_segment_distinct_prospective_UTC_hours":hours,
        "shadow_payload_sha256":"b"*64,
        "strategy_promoted":False,
        "future_edge_established":False,
        "broker_order_submission":"DISABLED",
    }


def shadow_archive(*,hours=0,complete=True):
    verified=hours if complete else max(0,hours-1)
    return {
        "kind":"OFFLINE_SIX_CRYPTO_ALL_SHADOWS_SOURCE_PARITY_AUDIT",
        "status":"COMPLETE" if complete else "INCOMPLETE_MISSING_DERIVED_SHADOWS",
        "current_segment_source_prospective_hours":hours,
        "current_segment_shadow_files_verified":verified,
        "current_segment_shadow_archive_complete":complete,
        "network_requests":"NONE",
        "broker_order_submission":"DISABLED",
    }


def score(*,hours=0):
    scorable=max(0,hours-1)
    return {
        "kind":"OFFLINE_SIX_CRYPTO_PROSPECTIVE_SHADOW_SCORECARD",
        "status":(
            "FULL_168_PRECOMMITTED_DECISION_OUTCOMES_AVAILABLE" if scorable>=168
            else "PROSPECTIVE_SHADOW_OUTCOMES_ACCUMULATING" if scorable
            else "ONE_PROSPECTIVE_HOUR_SHADOW_PRECOMMITTED_WAITING_FOR_OUTCOME"
                 if hours else "HISTORICAL_72H_BASELINE_ONLY_ZERO_PROSPECTIVE"
        ),
        "current_segment_prospective_source_hours":hours,
        "fully_observed_precommitted_decision_intervals":scorable,
        "source_168_consecutive_hour_collection_ready":hours>=168,
        "full_168_precommitted_decision_outcomes_ready":scorable>=168,
        "broker_order_submission":"DISABLED",
        "strategy_promoted":False,
    }


class DualForwardIntegrityStatusTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"forward"
        self.root.mkdir(mode=0o700)
        self.side=self.root/BASENAME

    def check(self,btc_status,source=None,shadow_status=None,
              shadow_archive_status=None,score_status=None):
        hours=(source or {}).get(
            "current_segment_independent_prospective_hours",0)
        archive_status=(shadow_archive_status if shadow_archive_status is not None
                        else shadow_archive(hours=hours))
        scoring=(score_status if score_status is not None else score(hours=hours))
        with patch("signal_vault.dual_forward_integrity.cloud_status",
                   return_value=btc_status),              patch("signal_vault.dual_forward_integrity.universe_status",
                   return_value=source) as us,              patch("signal_vault.dual_forward_integrity.inspect_six_crypto_shadow",
                   return_value=shadow_status) as ss,              patch("signal_vault.dual_forward_integrity.audit_six_crypto_shadow_archive",
                   return_value=archive_status),              patch("signal_vault.dual_forward_integrity.prospective_shadow_scorecard",
                   return_value=scoring):
            result=dual_forward_integrity_status(
                btc_root=self.root,sidecar_root=self.side)
        return result,us,ss

    def test_before_first_sidecar_tick_BTC_is_preserved_and_no_sidecar_reads_occur(self):
        result,us,ss=self.check(btc())
        self.assertEqual(result["status"],
                         "BTC_ONLY_HEALTHY_WAITING_FOR_FIRST_SIX_CRYPTO_TICK")
        self.assertEqual(result["btc_prospective_observations_verified"],7)
        self.assertEqual(result["sidecar"]["prospective_hours"],0)
        us.assert_not_called()
        ss.assert_not_called()
        self.assertFalse(self.side.exists())
        self.assertEqual(result["network_requests"],"NONE")
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_first_72h_sidecar_baseline_is_same_clock_but_zero_prospective(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=7,start="2026-09-30T02:00:00+00:00"),
            side(hours=0,latest="2026-09-30T03:00:00+00:00"),
            {"status":"NO_GENUINE_PROSPECTIVE_SIX_MARKET_HOUR_TO_EVALUATE"})
        self.assertEqual(result["status"],
                         "BTC_HEALTHY_SIX_CRYPTO_BASELINE_ONLY")
        self.assertEqual(result["six_crypto_lag_behind_BTC_hours"],0)
        self.assertEqual(result[
            "six_crypto_current_segment_independent_prospective_hours"],0)
        self.assertEqual(result[
            "six_crypto_current_segment_prospective_asset_bar_count"],0)
        self.assertFalse(result["six_crypto_ready_for_168_hour_audit"])

    def test_first_true_six_asset_hour_counts_one_clock_hour_and_shadow_must_match(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=8,start="2026-09-30T03:00:00+00:00"),
            side(hours=1,latest="2026-09-30T04:00:00+00:00"),
            shadow(hours=1))
        self.assertEqual(result["status"],"BTC_AND_SIX_CRYPTO_CURRENTLY_ALIGNED")
        self.assertEqual(result["six_crypto_lag_behind_BTC_hours"],0)
        self.assertEqual(result[
            "six_crypto_current_segment_independent_prospective_hours"],1)
        self.assertEqual(result[
            "six_crypto_current_segment_prospective_asset_bar_count"],6)
        self.assertEqual(result["six_crypto_shadow_payload_sha256"],"b"*64)
        self.assertFalse(result["six_crypto_strategy_promoted"])
        self.assertFalse(result["future_edge_established"])

    def test_168_source_hours_ready_but_one_more_hour_needed_for_168_scored_outcomes(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=175,start="2026-10-07T02:00:00+00:00"),
            side(hours=168,latest="2026-10-07T03:00:00+00:00"),
            shadow(hours=168))
        self.assertEqual(
            result["status"],
            "SIX_CRYPTO_168_SOURCE_HOURS_READY_WAITING_ONE_MORE_OUTCOME")
        self.assertTrue(result["six_crypto_ready_for_168_hour_audit"])
        self.assertTrue(result["six_crypto_source_168_hour_collection_ready"])
        self.assertFalse(
            result["six_crypto_fully_scored_168_decision_outcomes_ready"])
        self.assertEqual(
            result["six_crypto_fully_observed_precommitted_decision_intervals"],167)
        self.assertFalse(result["future_edge_established"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_169_source_hours_yields_168_scored_precommitted_outcomes_not_strategy_promotion(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=176,start="2026-10-07T03:00:00+00:00"),
            side(hours=169,latest="2026-10-07T04:00:00+00:00"),
            shadow(hours=169))
        self.assertEqual(
            result["status"],"SIX_CRYPTO_168_PRECOMMITTED_OUTCOMES_READY")
        self.assertTrue(result["six_crypto_source_168_hour_collection_ready"])
        self.assertTrue(
            result["six_crypto_fully_scored_168_decision_outcomes_ready"])
        self.assertEqual(
            result["six_crypto_fully_observed_precommitted_decision_intervals"],168)
        self.assertFalse(result["six_crypto_strategy_promoted"])
        self.assertFalse(result["future_edge_established"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_sidecar_one_hour_behind_is_warning_not_fabricated_alignment(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=9,start="2026-09-30T04:00:00+00:00"),
            side(hours=1,latest="2026-09-30T04:00:00+00:00"),
            shadow(hours=1))
        self.assertEqual(result["six_crypto_lag_behind_BTC_hours"],1)
        self.assertEqual(result["status"],"BTC_HEALTHY_SIX_CRYPTO_BEHIND")
        self.assertEqual(
            result["reason_code"],
            "SIX_CRYPTO_MISSED_OR_FAILED_LATEST_BTC_FIRST_TICK")

    def test_sidecar_ahead_of_BTC_first_stream_fails_closed(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=7,start="2026-09-30T02:00:00+00:00"),
            side(hours=1,latest="2026-09-30T04:00:00+00:00"),
            shadow(hours=1))
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(
            result["reason_code"],
            "SIX_CRYPTO_EVIDENCE_AHEAD_OF_BTC_FIRST_STREAM")

    def test_source_shadow_divergence_fails_closed(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=8,start="2026-09-30T03:00:00+00:00"),
            side(hours=2,latest="2026-09-30T04:00:00+00:00"),
            shadow(hours=1))
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(
            result["reason_code"],
            "SIX_CRYPTO_SOURCE_AND_SHADOW_COUNTS_DIVERGE")

    def test_missing_derived_shadow_archive_blocks_readiness_even_when_source_is_valid(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=8,start="2026-09-30T03:00:00+00:00"),
            side(hours=1,latest="2026-09-30T04:00:00+00:00"),
            shadow(hours=1),
            shadow_archive_status=shadow_archive(hours=1,complete=False))
        self.assertEqual(
            result["status"],"SIX_CRYPTO_SOURCE_VALID_SHADOW_ARCHIVE_INCOMPLETE")
        self.assertEqual(
            result["reason_code"],
            "MISSING_DERIVED_PREOUTCOME_SHADOWS_KEYLESS_REPAIR_AVAILABLE")
        self.assertFalse(result["six_crypto_source_168_hour_collection_ready"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_BTC_pause_preserves_side_evidence_without_claiming_health(self):
        self.side.mkdir(mode=0o700)
        result,_,_=self.check(
            btc(count=8,start="2026-09-30T03:00:00+00:00",paused=True),
            side(hours=1,latest="2026-09-30T04:00:00+00:00"),
            shadow(hours=1))
        self.assertEqual(result["status"],"BTC_PAUSED_SIDE_EVIDENCE_PRESERVED")
        self.assertEqual(result["reason_code"],"BTC_DURABLE_PAUSE_PRESENT")

    def test_wrong_sidecar_path_or_insecure_sidecar_refused_without_mutation(self):
        other=self.root/"not-approved-sidecar"
        before=set(self.root.iterdir())
        with self.assertRaises(ValueError):
            dual_forward_integrity_status(
                btc_root=self.root,sidecar_root=other)
        self.assertEqual(set(self.root.iterdir()),before)

        self.side.mkdir(mode=0o755)
        with patch("signal_vault.dual_forward_integrity.cloud_status",
                   return_value=btc()):
            result=dual_forward_integrity_status(
                btc_root=self.root,sidecar_root=self.side)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(
            result["reason_code"],
            "SIX_CRYPTO_SIDECAR_NOT_PRIVATE_DIRECTORY")
        self.assertEqual(self.side.stat().st_mode&0o777,0o755)


if __name__=="__main__":
    unittest.main()
