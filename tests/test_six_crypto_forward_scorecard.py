"""Prospective scorecard uses only source-time archived shadows, never hindsight."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from signal_vault.crypto_universe_forward import (
    CRYPTO_SIX, collect_six_crypto_once,
)
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.research_universe import ResearchBar
from signal_vault.six_crypto_forward_scorecard import prospective_shadow_scorecard
from signal_vault.six_crypto_shadow import archive_six_crypto_shadow

UTC=timezone.utc
HOUR=timedelta(hours=1)
FIRST=datetime(2026,9,29,12,7,tzinfo=UTC)


class DeterministicSixSource:
    def __init__(self):
        self.calls=[]

    def fetch(self,*,specs,start,end,as_of,**kwargs):
        self.calls.append((start,end,as_of,tuple(s.symbol for s in specs)))
        count=int((end-start)/HOUR)
        bars={}
        for symbol_index,spec in enumerate(specs):
            rows=[]
            for i in range(count):
                t=start+i*HOUR
                # Same source hour always gets same deterministic price,
                # independent of which bounded request fetched it.
                phase=Decimal(int(t.timestamp()//3600)%37)
                p=Decimal(100+symbol_index*20)+phase/Decimal("10")
                rows.append(ResearchBar(
                    spec.symbol,t,p,p+Decimal("1"),p-Decimal("1"),p,
                    Decimal("12"),"alpaca_crypto_us",as_of,False))
            bars[spec.symbol]=tuple(rows)
        return HistoricalDataBatch(
            "crypto",tuple(s.symbol for s in specs),"alpaca_crypto_us",
            "not_applicable",start.isoformat(),end.isoformat(),
            as_of.isoformat(),1,bars)


class ProspectiveSixCryptoShadowScorecardTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"sidecar"
        self.root.mkdir(mode=0o700)
        self.provider=DeterministicSixSource()

    def factory(self):
        return self.provider

    def source_tick(self,stamp,archive=True):
        result=collect_six_crypto_once(
            root=self.root,now=stamp,provider_factory=self.factory)
        if (archive and result["status"]==
                "SIX_NEW_PROSPECTIVE_ASSET_BARS_ONE_CLOCK_HOUR"):
            archive_six_crypto_shadow(root=self.root)
        return result

    def test_bootstrap_is_zero_forward_and_has_no_score_or_shadow(self):
        first=self.source_tick(FIRST)
        self.assertEqual(first["status"],
                         "HISTORICAL_BASELINE_ONLY_ZERO_PROSPECTIVE")
        report=prospective_shadow_scorecard(root=self.root)
        self.assertEqual(report["status"],
                         "HISTORICAL_72H_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertEqual(report["current_segment_prospective_source_hours"],0)
        self.assertEqual(report["current_segment_prospective_asset_bars"],0)
        self.assertEqual(report["fully_observed_precommitted_decision_intervals"],0)
        self.assertEqual(report["scenarios"],{})
        self.assertFalse(report["historical_72h_warmup_counted_as_prospective"])
        self.assertEqual(report["network_requests"],"NONE")
        self.assertEqual(report["broker_order_submission"],"DISABLED")
        self.assertFalse((self.root/"immutable-six-crypto-shadows").exists())

    def test_first_forward_hour_precommits_shadow_but_cannot_score_own_outcome(self):
        self.source_tick(FIRST)
        self.source_tick(FIRST+HOUR)
        report=prospective_shadow_scorecard(root=self.root)
        self.assertEqual(
            report["status"],
            "ONE_PROSPECTIVE_HOUR_SHADOW_PRECOMMITTED_WAITING_FOR_OUTCOME")
        self.assertEqual(report["current_segment_prospective_source_hours"],1)
        self.assertEqual(report["current_segment_prospective_asset_bars"],6)
        self.assertEqual(report["fully_observed_precommitted_decision_intervals"],0)
        self.assertEqual(report["verified_preoutcome_shadow_count"],1)
        self.assertEqual(report["scenarios"],{})
        self.assertTrue(
            report["latest_shadow_is_not_scored_until_next_hour_arrives"])

    def test_two_forward_hours_score_exactly_one_precommitted_interval_all_fixed_cases(self):
        self.source_tick(FIRST)
        self.source_tick(FIRST+HOUR)
        self.source_tick(FIRST+2*HOUR)
        report=prospective_shadow_scorecard(root=self.root)
        self.assertEqual(report["status"],
                         "PROSPECTIVE_SHADOW_OUTCOMES_ACCUMULATING")
        self.assertEqual(report["current_segment_prospective_source_hours"],2)
        self.assertEqual(report["current_segment_prospective_asset_bars"],12)
        self.assertEqual(report["fully_observed_precommitted_decision_intervals"],1)
        self.assertEqual(report["verified_preoutcome_shadow_count"],2)
        self.assertEqual(len(report["scenarios"]),3)
        self.assertFalse(report["strategy_promoted"])
        self.assertFalse(report["future_edge_established"])
        for scenario in report["scenarios"].values():
            self.assertTrue(
                scenario["illustrative_cost_assumptions_not_observed_execution"])
            self.assertEqual(len(scenario["fixed_predeclared_hypotheses"]),4)
            for result in scenario["fixed_predeclared_hypotheses"].values():
                self.assertEqual(result["initial_ONE_shared_bankroll_usd"],"100")
                self.assertEqual(result["max_total_long_exposure_usd"],"30")
                self.assertEqual(result[
                    "evaluated_precommitted_outcome_intervals"],1)
                self.assertEqual(
                    result["synthetic_fill_count"],
                    result["synthetic_fills_with_preoutcome_shadow_SHA_verified"])
                self.assertEqual(result["broker_order_submission"],"DISABLED")

    def test_source_collection_threshold_and_fully_scored_threshold_are_distinct(self):
        self.source_tick(FIRST)
        self.source_tick(FIRST+HOUR)
        self.source_tick(FIRST+2*HOUR)
        with patch(
            "signal_vault.six_crypto_forward_scorecard.SOURCE_168_HOURS",2),              patch(
            "signal_vault.six_crypto_forward_scorecard.FULLY_SCORED_DECISIONS",2):
            at_two=prospective_shadow_scorecard(root=self.root)
            self.assertTrue(at_two["source_168_consecutive_hour_collection_ready"])
            self.assertFalse(at_two["full_168_precommitted_decision_outcomes_ready"])
            self.assertEqual(
                at_two["fully_observed_precommitted_decision_intervals"],1)
            self.source_tick(FIRST+3*HOUR)
            at_three=prospective_shadow_scorecard(root=self.root)
            self.assertTrue(at_three["source_168_consecutive_hour_collection_ready"])
            self.assertTrue(at_three["full_168_precommitted_decision_outcomes_ready"])
            self.assertEqual(
                at_three["status"],
                "FULL_168_PRECOMMITTED_DECISION_OUTCOMES_AVAILABLE")
            self.assertEqual(
                at_three["fully_observed_precommitted_decision_intervals"],2)

    def test_missing_or_tampered_preoutcome_shadow_fails_before_pnl(self):
        self.source_tick(FIRST)
        self.source_tick(FIRST+HOUR)
        self.source_tick(FIRST+2*HOUR)
        folder=self.root/"immutable-six-crypto-shadows"
        first=sorted(folder.glob("*.json"))[0]
        original=first.read_bytes()
        first.unlink()
        with self.assertRaises(ValueError):
            prospective_shadow_scorecard(root=self.root)
        first.write_bytes(original)
        first.chmod(0o600)
        body=json.loads(first.read_bytes())
        body["strategy_promoted"]=True
        first.write_text(json.dumps(body),encoding="utf-8")
        first.chmod(0o600)
        with self.assertRaises(ValueError):
            prospective_shadow_scorecard(root=self.root)

    def test_gap_starts_new_zero_forward_segment_but_preserves_and_audits_old_shadow(self):
        self.source_tick(FIRST)
        self.source_tick(FIRST+HOUR)
        old_shadow=next((self.root/"immutable-six-crypto-shadows").glob("*.json"))
        old_hash=old_shadow.read_bytes()
        gap=self.source_tick(FIRST+4*HOUR)
        self.assertEqual(gap["event"],"HISTORICAL_72H_BOOTSTRAP")
        self.assertEqual(gap["segment_index"],2)
        report=prospective_shadow_scorecard(root=self.root)
        self.assertEqual(report["segment_index"],2)
        self.assertEqual(report["status"],
                         "HISTORICAL_72H_BASELINE_ONLY_ZERO_PROSPECTIVE")
        self.assertEqual(report["current_segment_prospective_source_hours"],0)
        self.assertEqual(old_shadow.read_bytes(),old_hash)

    def test_unexpected_shadow_file_is_not_ignored(self):
        self.source_tick(FIRST)
        self.source_tick(FIRST+HOUR)
        folder=self.root/"immutable-six-crypto-shadows"
        extra=folder/"shadow-hour-20260101T0000Z.json"
        extra.write_text("{}")
        extra.chmod(0o600)
        with self.assertRaises(ValueError):
            prospective_shadow_scorecard(root=self.root)


if __name__=="__main__":
    unittest.main()
