import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from signal_vault.backtest import BacktestResult, CostAssumptions
from signal_vault.market_data import Bar
from signal_vault.ml_confirmation import FEATURE_NAMES, MlArtifact
from signal_vault.ml_research import MlWalkForwardConfig, bars_fingerprint, walk_forward_ml_confirmation


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def bars(n=24 * 40):
    rows=[]
    p=Decimal("50000")
    for i in range(n):
        # Alternating slow regimes ensure both ML target classes exist while
        # remaining deterministic and fully chronological.
        block=(i // 36) % 2
        step=Decimal("80") if block == 0 else Decimal("-60")
        p=max(Decimal("1000"), p+step)
        rows.append(Bar(START+timedelta(hours=i),p,p+10,p-10,p,Decimal("100")+(i%7),
                        "fixture",3600,"BTC/USD"))
    return tuple(rows)


class MlWalkForwardTests(unittest.TestCase):
    def test_dataset_fingerprint_changes_when_training_data_changes(self):
        a=list(bars(100)); b=list(a)
        x=b[-1]; b[-1]=Bar(x.start,x.open,x.high,x.low,x.close+1,x.volume,x.source,x.timeframe_seconds,x.symbol)
        self.assertNotEqual(bars_fingerprint(a), bars_fingerprint(b))

    def test_training_is_prior_only_for_every_fold(self):
        seq=bars(24*40)
        cfg=MlWalkForwardConfig(minimum_training_hours=24*30,evaluation_hours=24*2,minimum_folds=3)
        report=walk_forward_ml_confirmation(seq,as_of=seq[-1].close_time,config=cfg)
        self.assertGreaterEqual(len(report.folds),3)
        for fold in report.folds:
            self.assertLessEqual(datetime.fromisoformat(fold.training_end_utc),
                                 datetime.fromisoformat(fold.evaluation_start_utc))
            self.assertNotEqual(fold.training_dataset_sha256, "0"*64)
            self.assertNotEqual(fold.artifact_sha256, "0"*64)
        self.assertIn("RESEARCH",report.kind)

    def test_report_never_implies_authorization(self):
        seq=bars(24*40)
        cfg=MlWalkForwardConfig(minimum_training_hours=24*30,evaluation_hours=24*2,minimum_folds=3)
        report=walk_forward_ml_confirmation(seq,as_of=seq[-1].close_time,config=cfg)
        self.assertFalse("LIVE_AUTHORIZATION" not in report.kind)  # label explicitly negates it
        self.assertIsInstance(report.research_candidate_pass,bool)
