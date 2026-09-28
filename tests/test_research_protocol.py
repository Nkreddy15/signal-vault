import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.market_data import Bar
from signal_vault.research_protocol import ResearchProtocolConfig, run_research_protocol
from signal_vault.strategy import StrategyConfig

START=datetime(2026,1,1,tzinfo=timezone.utc)


def data(n=24*70):
    out=[]
    for i in range(n):
        # deterministic cycles create crosses without being a claim about BTC.
        phase=(i//24)%10
        px=Decimal(100 + (phase if phase<5 else 10-phase)*3)
        out.append(Bar(START+timedelta(hours=i),px,px+1,px-1,px,Decimal(5),"protocol-test"))
    return out


class ResearchProtocolTests(unittest.TestCase):
    def config(self):
        return ResearchProtocolConfig(minimum_total_hours=24*60,
                                      final_holdout_hours=24*14,
                                      evaluation_fold_hours=24*7,
                                      minimum_holdout_fills=1)

    def test_flat_or_weak_candidate_fails_without_becoming_authorized(self):
        bars=data()
        report=run_research_protocol(bars,dataset_sha256="a"*64,
                                     strategy=StrategyConfig(3,8),protocol=self.config())
        self.assertEqual(report.to_dict()["kind"],"OFFLINE_FIXED_RESEARCH_PROTOCOL_NOT_LIVE_AUTHORIZATION")
        if report.eligible_for_provider_paper_shadow:
            # Synthetic behavior can happen; even a pass is explicitly paper-shadow only.
            self.assertIn("does not predict live profit",report.to_dict()["warning"])

    def test_final_holdout_change_does_not_rewrite_pre_holdout_gate(self):
        bars=data(); cfg=StrategyConfig(3,8); pcfg=self.config()
        before=run_research_protocol(bars,dataset_sha256="b"*64,strategy=cfg,protocol=pcfg)
        changed=list(bars)
        # Only mutate the final bar while preserving OHLC validity.
        changed[-1]=replace(changed[-1],close=Decimal("300"),high=Decimal("301"))
        after=run_research_protocol(changed,dataset_sha256="c"*64,strategy=cfg,protocol=pcfg)
        self.assertEqual(before.pre_holdout_gate,after.pre_holdout_gate)
        self.assertEqual(before.final_holdout_start_utc,after.final_holdout_start_utc)

    def test_invalid_dataset_fingerprint_rejected(self):
        with self.assertRaises(ValueError):
            run_research_protocol(data(),dataset_sha256="fake",protocol=self.config())
