"""Free-plan one-volume dual cron: BTC first; six-sidecar optional, isolated."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from signal_vault.crypto_universe_forward import universe_status
from signal_vault.railway_btc_first_dual_cron import (
    ACTIVATION_FLAG,ACTIVATION_VALUE,BASENAME,
    _review_gate_next_action,combined_btc_first_once,combined_offline_status,
)
from test_crypto_universe_forward import FixtureSixCryptoProvider,FIRST,HOUR

ROOT=Path(__file__).resolve().parents[1]
BTC_SUCCESS="ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED"


class ReviewGateNextActionTests(unittest.TestCase):
    def test_waiting_complete_fail_and_complete_review_handoff_are_distinct(self):
        waiting={
            "evidence_window_complete_for_gate":False,
            "candidates_meeting_all_review_criteria":[],
        }
        self.assertEqual(
            _review_gate_next_action(waiting),
            "CONTINUE_UNATTENDED_FORWARD_COLLECTION")
        complete_none={
            "evidence_window_complete_for_gate":True,
            "candidates_meeting_all_review_criteria":[],
        }
        self.assertEqual(
            _review_gate_next_action(complete_none),
            "FORWARD_SAMPLE_COMPLETE_NO_CANDIDATE_MEETS_FROZEN_REVIEW_GATE")
        complete_review={
            "evidence_window_complete_for_gate":True,
            "candidates_meeting_all_review_criteria":[
                "generic-ema12x26-v1-predeclared"],
        }
        self.assertEqual(
            _review_gate_next_action(complete_review),
            "OWNER_PAPER_EXECUTION_DESIGN_REVIEW_REQUIRED_BEFORE_ANY_PAPER_ACTION")

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
        self.sentinel.chmod(0o600)

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
        self.assertEqual(baseline["sidecar_stage"],"COMPLETE")
        self.assertEqual(
            baseline["sidecar_scorecard_status"],
            "HISTORICAL_72H_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertEqual(baseline["sidecar_source_hours_remaining_to_168"],168)
        self.assertEqual(baseline["sidecar_scored_intervals_remaining_to_168"],168)
        self.assertFalse(baseline["sidecar_observation_complete"])
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
        self.assertEqual(captured["sidecar_shadow_archive_status"],"COMPLETE")
        self.assertEqual(captured["sidecar_current_segment_shadow_files_verified"],1)
        self.assertTrue(captured["sidecar_current_segment_shadow_archive_complete"])
        self.assertEqual(
            captured["sidecar_scorecard_status"],
            "ONE_PROSPECTIVE_HOUR_SHADOW_PRECOMMITTED_WAITING_FOR_OUTCOME")
        self.assertEqual(
            captured["sidecar_fully_observed_precommitted_decision_intervals"],0)
        self.assertEqual(captured["sidecar_source_hours_remaining_to_168"],167)
        self.assertEqual(captured["sidecar_scored_intervals_remaining_to_168"],168)
        self.assertFalse(captured["sidecar_source_168_hour_collection_ready"])
        self.assertFalse(captured["sidecar_full_168_precommitted_decision_outcomes_ready"])
        self.assertFalse(captured["sidecar_observation_complete"])
        self.assertFalse(captured["sidecar_review_gate_evidence_window_complete"])
        self.assertEqual(captured["sidecar_candidates_meeting_all_review_criteria"],[])
        self.assertEqual(captured["sidecar_automatic_candidate_selection"],"DISABLED")
        self.assertEqual(captured["sidecar_paper_order_submission"],"DISABLED")
        self.assertEqual(
            captured["sidecar_next_action"],
            "CONTINUE_UNATTENDED_FORWARD_COLLECTION")
        self.assertTrue(captured[
            "sidecar_separate_owner_authorization_still_required_for_any_PAPER_execution"])
        self.assertEqual(captured[
            "sidecar_review_gate_source_hours_remaining_to_169"],168)
        self.assertEqual(captured[
            "sidecar_review_gate_scored_outcomes_remaining_to_168"],168)
        self.assertEqual(captured["sidecar_readiness_audit_network_requests"],"NONE")
        self.assertEqual(captured["sidecar_readiness_audit_credentials_accessed"],"NONE")
        self.assertEqual(
            captured["sidecar_readiness_audit_broker_order_submission"],"DISABLED")
        self.assertEqual(
            captured["btc_evidence_before_sidecar_SHA256"],
            captured["btc_evidence_after_sidecar_SHA256"])
        self.assertFalse(captured["btc_evidence_changed_during_sidecar_stage"])
        self.assertEqual(len(captured["btc_evidence_before_sidecar_SHA256"]),64)
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

    def test_live_observation_complete_requires_source_and_scored_thresholds(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        self.tick(FIRST)
        with patch(
            "signal_vault.railway_btc_first_dual_cron.SOURCE_168_HOURS",2), patch(
            "signal_vault.railway_btc_first_dual_cron.FULLY_SCORED_DECISIONS",2), patch(
            "signal_vault.six_crypto_forward_scorecard.SOURCE_168_HOURS",2), patch(
            "signal_vault.six_crypto_forward_scorecard.FULLY_SCORED_DECISIONS",2):
            one=self.tick(FIRST+HOUR)
            self.assertFalse(one["sidecar_observation_complete"])
            two=self.tick(FIRST+2*HOUR)
            self.assertTrue(two["sidecar_source_168_hour_collection_ready"])
            self.assertFalse(two["sidecar_full_168_precommitted_decision_outcomes_ready"])
            self.assertFalse(two["sidecar_observation_complete"])
            three=self.tick(FIRST+3*HOUR)
            self.assertTrue(three["sidecar_source_168_hour_collection_ready"])
            self.assertTrue(three["sidecar_full_168_precommitted_decision_outcomes_ready"])
            self.assertEqual(three["sidecar_source_hours_remaining_to_168"],0)
            self.assertEqual(three["sidecar_scored_intervals_remaining_to_168"],0)
            self.assertTrue(three["sidecar_observation_complete"])
            self.assertEqual(three["broker_order_submission"],"DISABLED")

    def test_offline_status_reports_cumulative_independent_hours_without_provider_GET(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        self.tick(FIRST)
        self.tick(FIRST+HOUR)
        before=self.six_factory_calls
        with patch(
            "signal_vault.railway_btc_first_dual_cron.cloud_status",
            return_value={
                "status":"READ_ONLY_STATUS_AVAILABLE",
                "network_requests":"NONE",
                "broker_order_submission":"DISABLED",
            },
        ):
            with patch("signal_vault.railway_btc_first_dual_cron.CLOUD_ROOT",self.btc):
                out=combined_offline_status(
                    environ=self.env,btc_root=self.btc,sidecar_root=self.side)
        self.assertEqual(self.six_factory_calls,before)
        self.assertEqual(out["status"],"READ_ONLY_STATUS_AVAILABLE")
        self.assertEqual(out["network_requests"],"NONE")
        self.assertEqual(out["credential_access"],"NONE")
        self.assertEqual(out["sidecar_current_segment_index"],1)
        self.assertEqual(
            out["sidecar_current_segment_independent_prospective_hours"],1)
        self.assertEqual(out["sidecar_current_segment_prospective_asset_bar_count"],6)
        self.assertEqual(out["sidecar_latest_hour_utc"],
                         (FIRST+HOUR).replace(minute=0).isoformat())
        self.assertFalse(out["sidecar_ready_for_seven_day_audit"])
        self.assertFalse(out["sidecar_source_168_hour_collection_ready"])
        self.assertFalse(out["sidecar_full_168_precommitted_decision_outcomes_ready"])
        self.assertEqual(out["sidecar_source_hours_remaining_to_168"],167)
        self.assertEqual(out["sidecar_scored_intervals_remaining_to_168"],168)
        self.assertFalse(out["sidecar_observation_complete"])
        self.assertFalse(out["sidecar_review_gate_evidence_window_complete"])
        self.assertEqual(out["sidecar_candidates_meeting_all_review_criteria"],[])
        self.assertEqual(out["sidecar_automatic_candidate_selection"],"DISABLED")
        self.assertEqual(out["sidecar_paper_order_submission"],"DISABLED")
        self.assertEqual(
            out["sidecar_next_action"],
            "CONTINUE_UNATTENDED_FORWARD_COLLECTION")
        self.assertTrue(out[
            "sidecar_separate_owner_authorization_still_required_for_any_PAPER_execution"])
        self.assertEqual(out[
            "sidecar_review_gate_source_hours_remaining_to_169"],168)
        self.assertEqual(out[
            "sidecar_review_gate_scored_outcomes_remaining_to_168"],168)
        self.assertEqual(
            out["sidecar_fully_observed_precommitted_decision_intervals"],0)
        self.assertEqual(
            out["sidecar_scorecard_status"],
            "ONE_PROSPECTIVE_HOUR_SHADOW_PRECOMMITTED_WAITING_FOR_OUTCOME")
        self.assertEqual(
            out["sidecar_shadow_status"],
            "OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY")
        self.assertEqual(len(out["sidecar_latest_shadow_SHA256"]),64)
        self.assertEqual(out["broker_order_submission"],"DISABLED")

    def test_offline_status_does_not_create_sidecar_when_not_activated(self):
        self.assertFalse(self.side.exists())
        with patch(
            "signal_vault.railway_btc_first_dual_cron.cloud_status",
            return_value={"status":"READ_ONLY_STATUS_AVAILABLE"},
        ):
            with patch("signal_vault.railway_btc_first_dual_cron.CLOUD_ROOT",self.btc):
                out=combined_offline_status(
                    environ=self.env,btc_root=self.btc,sidecar_root=self.side)
        self.assertEqual(out["status"],"READ_ONLY_BTC_STATUS_AVAILABLE")
        self.assertEqual(out["sidecar_status"],"NOT_ACTIVATED_OR_UNRECOGNIZED")
        self.assertFalse(self.side.exists())
        self.assertEqual(self.six_factory_calls,0)

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

    def test_insecure_btc_mode_is_restricted_then_sidecar_proceeds_without_byte_change(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        original=self.sentinel.read_bytes()
        self.sentinel.chmod(0o644)
        result=self.tick(FIRST)
        self.assertEqual(result["btc_status"],BTC_SUCCESS)
        self.assertEqual(
            result["sidecar_status"],
            "HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertEqual(result["sidecar_stage"],"COMPLETE")
        self.assertEqual(self.sentinel.read_bytes(),original)
        self.assertEqual(self.sentinel.stat().st_mode&0o777,0o600)
        repaired=result["btc_evidence_permission_modes_restricted"]
        self.assertTrue(any(
            x["path"]=="observations-auto-original.sqlite3" and
            x["from_mode"]=="0644" and x["to_mode"]=="0600"
            for x in repaired))
        self.assertEqual(result["broker_order_submission"],"DISABLED")

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

    def test_unexpected_original_BTC_mutation_during_sidecar_is_detected_loudly(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        normal=FixtureSixCryptoProvider()
        sentinel=self.sentinel
        class MutatingProvider:
            def fetch(self,**kwargs):
                # Simulate a catastrophic sidecar bug or unexpected concurrent
                # writer. Production sidecar code has no path to this file.
                sentinel.write_bytes(b"UNEXPECTED BTC MUTATION")
                return normal.fetch(**kwargs)
        self.six_source=MutatingProvider()
        result=self.tick(FIRST)
        self.assertEqual(result["btc_status"],BTC_SUCCESS)
        self.assertEqual(
            result["sidecar_status"],"FAILED_BTC_EVIDENCE_MUTATION_GUARD")
        self.assertTrue(result["btc_evidence_changed_during_sidecar_stage"])
        self.assertNotEqual(
            result["btc_evidence_before_sidecar_SHA256"],
            result["btc_evidence_after_sidecar_SHA256"])
        self.assertEqual(
            result["sidecar_failure_class"],"BtcEvidenceFingerprintMismatch")
        self.assertFalse(result["original_BTC_status_preserved"])
        self.assertIsNone(result["existing_BTC_evidence_deleted_or_reset"])
        self.assertEqual(result["broker_order_submission"],"DISABLED")

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

    def test_known_sidecar_child_permission_drift_is_restricted_without_touching_BTC(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        before=self.sentinel.read_bytes()
        baseline=self.tick(FIRST)
        self.assertEqual(
            baseline["sidecar_status"],
            "HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        receipts=self.side/"hourly-receipts"
        receipts.chmod(0o755)
        with patch("signal_vault.railway_btc_first_dual_cron.os.geteuid",
                   return_value=0):
            next_hour=self.tick(FIRST+HOUR)
        self.assertEqual(next_hour["sidecar_stage"],"COMPLETE")
        self.assertEqual(
            next_hour["sidecar_status"],
            "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR")
        self.assertEqual(receipts.stat().st_mode&0o777,0o700)
        self.assertIn(
            "hourly-receipts",
            next_hour["sidecar_directory_permissions_restricted"])
        self.assertFalse(next_hour["btc_evidence_changed_during_sidecar_stage"])
        self.assertEqual(self.sentinel.read_bytes(),before)

    def test_permission_drift_failure_reports_precise_stage_and_never_uses_provider(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        self.tick(FIRST)
        receipts=self.side/"hourly-receipts"
        receipts.chmod(0o755)
        before_calls=self.six_factory_calls
        with patch("signal_vault.railway_btc_first_dual_cron.os.geteuid",
                   return_value=1001):
            out=self.tick(FIRST+HOUR)
        self.assertEqual(
            out["sidecar_status"],
            "FAILED_SAFE_OR_BLOCKED_NEW_SIDE_CAR_ONLY")
        self.assertEqual(out["sidecar_failure_class"],"PermissionError")
        self.assertEqual(
            out["sidecar_stage"],
            "SIDE_CAR_CHILD_PERMISSION_RESTRICTION")
        self.assertEqual(self.six_factory_calls,before_calls)
        self.assertEqual(receipts.stat().st_mode&0o777,0o755)
        self.assertTrue(out["original_BTC_status_preserved"])

    def test_permission_failure_includes_read_only_exact_sidecar_metadata(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        self.tick(FIRST)
        receipts=self.side/"hourly-receipts"
        receipts.chmod(0o755)
        before_calls=self.six_factory_calls
        with patch("signal_vault.railway_btc_first_dual_cron.os.geteuid",
                   return_value=1001):
            out=self.tick(FIRST+HOUR)
        self.assertEqual(out["sidecar_failure_class"],"PermissionError")
        snap=out["sidecar_permission_snapshot"]
        self.assertEqual(set(snap["entries"]),{
            ".", ".six-crypto-source.lock", "hourly-receipts",
            "immutable-six-crypto-shadows"})
        self.assertEqual(snap["entries"]["hourly-receipts"]["mode_octal"],"0755")
        self.assertEqual(snap["entries"]["."]["mode_octal"],"0700")
        self.assertIsInstance(
            snap["entries"]["hourly-receipts"]["uid_matches_process"],bool)
        self.assertEqual(self.six_factory_calls,before_calls)
        self.assertEqual(out["broker_order_submission"],"DISABLED")

    def test_low_free_disk_skips_six_source_without_harming_BTC(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        original=self.sentinel.read_bytes()
        # Simulate just 100 MiB free on the one existing persistent volume;
        # the sidecar requires an EXTRA 128 MiB BTC reserve + per-tick space.
        with patch("signal_vault.railway_btc_first_dual_cron.os.statvfs",
                   return_value=SimpleNamespace(
                       f_bavail=100,f_frsize=1024*1024)):
            result=self.tick(FIRST)
        self.assertEqual(result["btc_status"],BTC_SUCCESS)
        self.assertEqual(result["sidecar_status"],
                         "SIX_MARKET_SKIPPED_TO_PRESERVE_BTC_DISK_RESERVE")
        self.assertEqual(self.six_factory_calls,0)
        self.assertEqual(self.sentinel.read_bytes(),original)
        self.assertFalse((self.side/"hourly-receipts").exists())

    def test_large_sidecar_archive_cannot_exhaust_original_BTC_storage(self):
        self.env[ACTIVATION_FLAG]=ACTIVATION_VALUE
        self.side.mkdir(mode=0o700)
        existing=self.side/"previous-safe-archive.bin"
        with existing.open("wb") as file:
            file.truncate(32*1024*1024)  # allocation-independent st_size gate
        original=self.sentinel.read_bytes()
        result=self.tick(FIRST)
        self.assertEqual(result["btc_status"],BTC_SUCCESS)
        self.assertEqual(result["sidecar_status"],
                         "SIX_MARKET_SKIPPED_TO_PRESERVE_BTC_DISK_RESERVE")
        self.assertEqual(self.six_factory_calls,0)
        self.assertEqual(self.sentinel.read_bytes(),original)
        self.assertEqual(existing.stat().st_size,32*1024*1024)


    def test_no_operator_approval_means_old_production_start_command_unchanged(self):
        docker=(ROOT/"Dockerfile").read_text(encoding="utf-8")
        self.assertIn('"signal_vault.railway_forward_cron", "--once"',docker)
        self.assertNotIn("railway_btc_first_dual_cron",docker)
        self.assertFalse(self.env.get(ACTIVATION_FLAG))
        self.assertEqual(self.sentinel.read_bytes(),
                         b"ORIGINAL BTC SOURCE PRESERVE ME")


if __name__=="__main__":
    unittest.main()
