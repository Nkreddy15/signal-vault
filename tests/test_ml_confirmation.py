import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.market_data import Bar
from signal_vault.ml_confirmation import (FEATURE_NAMES,MlArtifact,apply_confirmation,
                                           extract_features,load_artifact,save_artifact)
from signal_vault.ml_training import MlTrainingConfig,build_supervised_samples,train_logistic_confirmation
from signal_vault.strategy import Action,StrategyConfig,generate_signal

START=datetime(2026,1,1,tzinfo=timezone.utc)


def bars(n=300):
    out=[]
    for i in range(n):
        # multi-scale deterministic synthetic movement; research fixture only.
        px=Decimal(str(100 + 10*((i//12)%2) + (i%7)*0.3))
        out.append(Bar(START+timedelta(hours=i),px,px+1,px-1,px,Decimal(10+(i%5)),"ml-test"))
    return out


def artifact(coef=0.0,intercept=0.0,threshold=.65):
    n=len(FEATURE_NAMES)
    return MlArtifact("test-ml","a"*64,"2026-01-01T00:00:00+00:00",12,.0075,threshold,
                      FEATURE_NAMES,(0.0,)*n,(1.0,)*n,(coef,)*n,intercept)


class MlConfirmationTests(unittest.TestCase):
    def test_features_do_not_use_future_bars(self):
        data=bars(80); cutoff=50
        before=extract_features(data[:cutoff])
        changed=list(data); changed[-1]=replace(changed[-1],close=Decimal("999"),high=Decimal("1000"))
        self.assertEqual(before,extract_features(changed[:cutoff]))

    def test_model_only_vetoes_buy_and_never_creates_buy(self):
        data=bars(100); cfg=StrategyConfig(3,5)
        # Manufacture signal objects from real deterministic function then replace action.
        base=generate_signal(data[:60],cfg)
        buy=replace(base,action=Action.BUY)
        veto=apply_confirmation(buy,data[:60],artifact(intercept=-20))
        self.assertEqual(veto.action,Action.HOLD)
        sell=replace(base,action=Action.SELL)
        self.assertEqual(apply_confirmation(sell,data[:60],artifact(intercept=-20)).action,Action.SELL)
        hold=replace(base,action=Action.HOLD)
        self.assertNotEqual(apply_confirmation(hold,data[:60],artifact(intercept=20)).action,Action.BUY)

    def test_json_artifact_roundtrip_no_pickle(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"model.json"; original=artifact(coef=.2,intercept=.1)
            digest=save_artifact(path,original)
            loaded=load_artifact(path)
            self.assertEqual(loaded,original)
            self.assertEqual(loaded.fingerprint(),digest)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_training_samples_and_model_are_chronological(self):
        data=bars(400); cfg=MlTrainingConfig(horizon_hours=6,label_return_threshold=.001)
        X,y,cutoffs=build_supervised_samples(data,config=cfg)
        self.assertGreater(len(X),100); self.assertEqual(set(y),{0,1})
        self.assertTrue(all(a<b for a,b in zip(cutoffs,cutoffs[1:])))
        model=train_logistic_confirmation(data,dataset_sha256="b"*64,config=cfg)
        p=model.probability(extract_features(data))
        self.assertGreaterEqual(p,0); self.assertLessEqual(p,1)
        self.assertLessEqual(datetime.fromisoformat(model.trained_until_utc),data[-cfg.horizon_hours-2].close_time)


class MlSellBypassRegressionTests(unittest.TestCase):
    def test_sell_and_hold_do_not_touch_broken_model(self):
        from signal_vault.strategy import StrategySignal
        class ExplodingArtifact:
            def probability(self, *_): raise AssertionError("SELL/HOLD must not infer")
            def fingerprint(self): raise AssertionError("SELL/HOLD must not fingerprint")
        base = StrategySignal(Action.SELL, "e" * 64, "2026-09-28T00:00:00+00:00",
                              Decimal("1"), Decimal("1"), "sell", "v")
        out = apply_confirmation(base, (), ExplodingArtifact())
        self.assertIs(out.action, Action.SELL)
        self.assertEqual(out.evidence_id, base.evidence_id)
        hold = StrategySignal(Action.HOLD, "h" * 64, "2026-09-28T00:00:00+00:00",
                              Decimal("1"), Decimal("1"), "hold", "v")
        self.assertEqual(apply_confirmation(hold, (), ExplodingArtifact()), hold)
