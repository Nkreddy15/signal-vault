"""Point-in-time selection, label accounting and forecast leakage regressions."""
import io
import json
import tempfile
import unittest
import zipfile
import contextlib
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import audit_strategy_results as audit
import forecast_edge_lab as e
import multi_strategy_lab as m
import prepare_liquid_universe as u
from test_multi_strategy_lab import START, frame


def archive_csv(symbol, volume=100, future_volume=None):
    f = frame(800)
    f["volume"] = volume
    if future_volume is not None:
        f.loc[672:, "volume"] = future_volume
    f["ts"] //= 1000
    f["trades"] = 10
    return symbol+"USD_15.csv", f.to_csv(header=False, index=False)


class EdgeTests(unittest.TestCase):
    def test_universe_uses_formation_only_and_exact_usd_names(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"q1.zip"
            with zipfile.ZipFile(path, "w") as z:
                for symbol, volume, future in (("AAA",200,None), ("BBB",100,1_000_000), ("USDT",1_000_000,None)):
                    name, content = archive_csv(symbol, volume, future)
                    z.writestr(name, content)
                z.writestr("AAAUSDT_15.csv", "not a USD market")
                z.writestr("AAAEUR_15.csv", "not a USD market")
            with zipfile.ZipFile(path) as z:
                selected, _ = u.rank_formation(z, START, START+7*m.DAY, count=1, min_daily_usd=0)
            self.assertEqual(selected[0]["pair"], "AAA/USD")
            self.assertEqual(selected[0]["formation_bars"], 672)

    def test_later_missing_archive_does_not_remove_selected_asset(self):
        with tempfile.TemporaryDirectory() as d:
            first, second = Path(d)/"q1.zip", Path(d)/"q2.zip"
            with zipfile.ZipFile(first, "w") as z:
                name, content = archive_csv("AAA")
                z.writestr(name, content)
            with zipfile.ZipFile(second, "w"):
                pass
            saved = {}
            def save(f, path):
                saved[str(path)] = f.copy()
            with patch.object(pd.DataFrame, "to_feather", save):
                receipt = u.prepare([first, second], Path(d)/"prepared", 1, 0)
            self.assertEqual(receipt["selected"][0]["pair"], "AAA/USD")
            self.assertEqual(receipt["missing_later_members"][0]["pair"], "AAA/USD")
            self.assertEqual(len(saved), 1)

    def test_future_invalid_prices_do_not_change_formation_ranking(self):
        f = frame(800)
        f["ts"] //= 1000
        f["trades"] = 10
        f.loc[700:, "close"] = np.nan
        with io.BytesIO() as buffer:
            with zipfile.ZipFile(buffer, "w") as z:
                z.writestr("AAAUSD_15.csv", f.to_csv(header=False, index=False))
            buffer.seek(0)
            with zipfile.ZipFile(buffer) as z:
                selected, _ = u.rank_formation(z, START, START+7*m.DAY, count=1, min_daily_usd=0)
            self.assertEqual(selected[0]["pair"], "AAA/USD")

    def test_labels_match_fixed_barrier_engine_net_payoff(self):
        for profile in m.FEE_PROFILES:
            f = pd.DataFrame(dict(ts=START+np.arange(30)*m.BAR, open=100., high=100.1,
                low=99.9, close=100., atr=.001, stop=.02, target=.06))
            f.loc[4, "high"] = 110
            y, available = e.barrier_labels(f, m.FEE_PROFILES[profile][0][1], hold=8)
            sig = m.Signal("forecast_ridge", 1, 1, .02, .06, 8, START+3*m.BAR, 100, .001, False)
            market = [(int(r.ts), {"BTC/USD":((r.open, r.high, r.low, r.close, r.atr), [sig] if i == 4 else [])})
                for i, r in enumerate(f.itertuples()) if 4 <= i <= 12]
            result = m.simulate(market, m.Config(family="forecast_ridge", spread_bps=15,
                fee_profile=profile), allowed_families=e.ARRANGEMENTS)
            trade = result["trades"][0]
            self.assertAlmostEqual(y[3], trade["pnl"]/trade["stake"])
            self.assertEqual(available[3], START+12*m.BAR)
            self.assertFalse(trade["trailing"])

    def test_forward_label_cannot_cross_gap_or_entry_drift(self):
        f = pd.DataFrame(dict(ts=START+np.arange(30)*m.BAR, open=100., high=100.1,
            low=99.9, close=100., atr=.001, stop=.02, target=.06))
        y, _ = e.barrier_labels(f.drop(index=10).reset_index(drop=True), .008, hold=8)
        self.assertTrue(np.isnan(y[3]))
        f.loc[4, ["open", "high", "low", "close"]] = 120
        y, _ = e.barrier_labels(f, .008, hold=8)
        self.assertTrue(np.isnan(y[3]))

    def test_purge_uses_label_availability_not_just_feature_time(self):
        test_start = START+60*m.DAY
        val_start = test_start-14*m.DAY
        table = pd.DataFrame(dict(ts=[val_start-3*m.DAY, val_start-m.DAY, val_start, test_start-m.DAY],
            label_end_ms=[val_start-m.DAY, val_start+m.DAY, test_start-m.DAY, test_start+m.DAY], y=[1,2,3,4]))
        train, val, _ = e.purged_splits(table, test_start)
        self.assertEqual(train.y.tolist(), [1])
        self.assertEqual(val.y.tolist(), [3])

    def test_calibration_thins_overlapping_outcomes(self):
        validation = pd.DataFrame(dict(pair=["AAA/USD"]*100, ts=START+np.arange(100)*m.BAR,
            y=[.02]*100))
        result = e.calibration(validation, np.ones(100)*.03, hold=8, min_events=10)
        self.assertEqual(result["nonoverlapping_asset_events"], 12)
        self.assertIsNone(e.calibration(validation, np.ones(100)*.03, hold=192, min_events=10))

    def test_diagnostics_distinguish_prediction_and_sample_rejections(self):
        validation = pd.DataFrame(dict(pair=["AAA/USD"]*100, ts=START+np.arange(100)*m.BAR,
            y=[.02]*100))
        below = e.calibration_details(validation, np.full(100, -.01), hold=8, min_events=10)
        self.assertIsNone(below["selection"])
        self.assertTrue(all("NO_PREDICTIONS_ABOVE_THRESHOLD" in r["rejection_reasons"]
            for r in below["thresholds"]))
        sparse = e.calibration_details(validation, np.full(100, .03), hold=192, min_events=10)
        row = sparse["thresholds"][0]
        self.assertEqual(row["raw_events"], 100)
        self.assertEqual(row["nonoverlapping_asset_events"], 1)
        self.assertEqual(row["rejection_reasons"], ["TOO_FEW_NONOVERLAPPING_EVENTS"])
        good = e.calibration_details(validation, np.full(100, .03), hold=8, min_events=10)
        self.assertEqual(good["selection"]["threshold"], .003)
        self.assertEqual(good["selection"]["nonoverlapping_asset_events"], 12)
        self.assertAlmostEqual(good["selection"]["mean_net_return"], .02)
        self.assertIsNone(good["selection"]["profit_factor"])

    def test_diagnostics_identify_losing_selected_outcomes(self):
        validation = pd.DataFrame(dict(pair=["AAA/USD"]*10, ts=START+np.arange(10)*10*m.BAR,
            y=[.02, -.03]*5))
        details = e.calibration_details(validation, np.full(10, .03), hold=8, min_events=10)
        row = details["thresholds"][0]
        self.assertIsNone(details["selection"])
        self.assertEqual(row["rejection_reasons"],
            ["MEAN_NET_RETURN_BELOW_0.3_PERCENT", "PROFIT_FACTOR_BELOW_1.1"])
        self.assertAlmostEqual(row["profit_factor"], 2/3)
        with self.assertRaisesRegex(ValueError, "align"):
            e.calibration_details(validation, [.03])

    def test_predictive_skill_compares_against_past_mean(self):
        actual = np.array([-.02, .03])
        perfect = e.predictive_diagnostics(actual, actual, .005)
        self.assertEqual(perfect["mse_skill_vs_past_mean"], 1)
        constant = e.predictive_diagnostics(actual, np.full(2, .005), .005)
        self.assertEqual(constant["mse_skill_vs_past_mean"], 0)

    def test_monthly_fit_and_first_forecast_are_invariant_to_later_prices(self):
        frames = {"AAA/USD":frame(7000), "BBB/USD":frame(7000)}
        _, original, _ = e.monthly_predictions(frames, "kraken_spot", START+7*m.DAY,
            min_train=100, min_events=3, hold=8)
        altered = {p:f.copy() for p,f in frames.items()}
        future = int(pd.Timestamp("2026-03-10", tz="UTC").value//1_000_000)
        for f in altered.values():
            f.loc[f.ts >= future, ["open", "high", "low", "close"]] *= 10
        _, changed, _ = e.monthly_predictions(altered, "kraken_spot", START+7*m.DAY,
            min_train=100, min_events=3, hold=8)
        before = next(f for f in original if f["status"] == "PAST_ONLY_FIT")
        after = next(f for f in changed if f["status"] == "PAST_ONLY_FIT")
        self.assertEqual(before["month"], "2026-03")
        self.assertEqual(before["training_data_sha256"], after["training_data_sha256"])
        self.assertEqual(before["first_test_forecasts"], after["first_test_forecasts"])
        self.assertEqual(before["calibration_diagnostics"], after["calibration_diagnostics"])
        self.assertEqual(before["past_validation_predictive_diagnostics"], after["past_validation_predictive_diagnostics"])
        self.assertLess(before["train_max_label_end_ms"], before["validation_start_ms"])
        self.assertLess(before["calibration_max_label_end_ms"], before["test_start_ms"])

    def test_audit_reconciles_recorded_gross_fees_and_net(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            row = dict(name="fixture", trades=1, ending_equity=101.17, realized_pnl=1.17,
                fees=.82, short_carry=.01, pending_positions=0)
            (root/"multi-strategy-summary.json").write_text(json.dumps(dict(reports=[row])))
            trade = dict(gross_pnl=2, reason="TARGET", entry_ms=0, exit_ms=3600000)
            (root/"fixture.json").write_text(json.dumps(dict(trades=[trade])))
            result = audit.audit(root)["reports"][0]
            self.assertTrue(result["reconciliation_pass"])
            self.assertEqual(result["recorded_fill_gross_pnl"], 2)
            self.assertEqual(result["exit_reasons"], {"TARGET":1})

    def test_full_forecast_cli_writes_all_scenarios_and_no_profit_cap(self):
        raw = frame(7000)
        raw["ts"] += int(pd.Timestamp("2026-03-01", tz="UTC").value//1_000_000)-START
        prepared = {"AAA/USD":e.engineered(raw)}
        r = prepared["AAA/USD"].iloc[399]
        def forecasts(*args, **kwargs):
            candidates = {family:{(int(r.ts)+m.BAR, "AAA/USD"):
                m.Signal(family, 1, 1, .02, .06, e.HOLD, int(r.ts), float(r.close), float(r.atr), False)}
                for family in e.ARRANGEMENTS}
            return candidates, [dict(status="PAST_ONLY_FIT", month="2026-03",
                calibration_diagnostics={}, test_start_ms=int(raw.ts.iloc[0]))], prepared
        with tempfile.TemporaryDirectory() as d:
            root, out = Path(d)/"data", Path(d)/"out"
            root.mkdir()
            (root/"universe.json").write_text(json.dumps(dict(selected=[dict(pair="AAA/USD")], formation_end_ms=START)))
            (root/"AAA_USD-15m.feather").write_bytes(b'fixture')
            with patch.object(pd, "read_feather", return_value=raw), patch.object(e, "monthly_predictions", side_effect=forecasts),\
                    patch("sys.argv", ["lab", "--data-dir", str(root), "--output-dir", str(out)]),\
                    contextlib.redirect_stdout(io.StringIO()):
                e.main()
            result = json.loads((out/"forecast-summary.json").read_text())
            self.assertEqual(len(result["reports"]), 48)
            self.assertIsNone(result["profit_ceiling"])
            self.assertEqual(result["status"], "DEVELOPMENT_ONLY_NO_ACTIVATION")
            self.assertTrue(all(r["trades"] == 1 for r in result["reports"]))
            self.assertTrue((out/"forecast-results.md").is_file())
            self.assertEqual(result["milestones"][-1], 10000)

    def test_diagnostics_only_skips_replay_and_writes_uploadable_receipts(self):
        raw = frame(1000)
        fold = dict(status="INSUFFICIENT_PAST_DATA", month="2026-02")
        with tempfile.TemporaryDirectory() as d:
            root, out = Path(d)/"data", Path(d)/"out"
            root.mkdir()
            (root/"universe.json").write_text(json.dumps(dict(selected=[dict(pair="AAA/USD")], formation_end_ms=START)))
            (root/"AAA_USD-15m.feather").write_bytes(b'fixture')
            with patch.object(pd, "read_feather", return_value=raw),\
                    patch.object(e, "monthly_predictions", return_value=({}, [fold], {})),\
                    patch.object(m, "simulate", side_effect=AssertionError("Must not replay")),\
                    patch("sys.argv", ["lab", "--data-dir", str(root), "--output-dir", str(out), "--diagnostics-only"]),\
                    contextlib.redirect_stdout(io.StringIO()):
                e.main()
            result = json.loads((out/"forecast-diagnostics.json").read_text())
            self.assertFalse(result["policy_changed"])
            self.assertEqual(len(result["folds"]), 2)
            self.assertIn("INSUFFICIENT_PAST_DATA", (out/"forecast-diagnostics.md").read_text())
            self.assertFalse((out/"forecast-summary.json").exists())

    def test_engine_can_hold_and_earn_above_reporting_milestones(self):
        sig = m.Signal("forecast_ridge", 1, 1, .02, .06, 8, START-m.BAR, 100, .001, False)
        result = m.simulate([(START, {"AAA/USD":((100, 110, 100, 108, .001), [sig])})],
            m.Config(family="forecast_ridge", starting_balance=2000), allowed_families=e.ARRANGEMENTS)
        self.assertGreater(result["summary"]["ending_equity"], 2000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
