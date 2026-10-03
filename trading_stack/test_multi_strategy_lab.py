"""Research mechanics, not claims about market profitability."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import multi_strategy_lab as m

START = int(pd.Timestamp("2026-01-01", tz="UTC").value//1_000_000)


def frame(count=600):
    i = np.arange(count)
    close = 100*np.exp(i*.0004+.005*np.sin(i/7))
    return pd.DataFrame(dict(ts=START+i*m.BAR, open=close*.999, high=close*1.002,
        low=close*.997, close=close, volume=100+70*(i%13 == 0)))


def signal(family="breakout", side=1, stop=.02, target=.06):
    return m.Signal(family, side, 3, stop, target, 96, START-m.BAR)


class Mechanics(unittest.TestCase):
    def test_datetime_units_and_real_duplicates(self):
        f = frame()
        for unit in ("s", "ms", "us", "ns"):
            dated = f.drop(columns="ts").copy()
            dated["date"] = pd.to_datetime(f.ts, unit="ms", utc=True).astype(f"datetime64[{unit}, UTC]")
            pd.testing.assert_frame_equal(m.normalized(dated), f)
        with self.assertRaises(ValueError):
            m.normalized(pd.concat([f, f.iloc[:1]]))

    def test_prefix_indicators_and_signals_do_not_see_future(self):
        f = frame()
        prefix = m.features(f.iloc[:400])
        full = m.features(f)
        pd.testing.assert_frame_equal(prefix, full.iloc[:400])
        expected = m.signals(prefix)
        actual = {ts:s for ts,s in m.signals(full).items() if ts < START+400*m.BAR}
        self.assertEqual(actual, expected)
        future = f.copy()
        future.loc[400:, ["open", "high", "low", "close"]] *= 10
        self.assertEqual(expected, {ts:s for ts,s in m.signals(m.features(future)).items()
            if ts < START+400*m.BAR})

    def test_gap_restarts_warmup_and_does_not_backfill(self):
        out = m.features(frame().drop(index=300))
        self.assertEqual(int(out.age.iloc[300]), 1)
        self.assertEqual(len(out), 599)
        self.assertFalse(any(START+301*m.BAR <= t < START+556*m.BAR for t in m.signals(out)))

    def test_stop_first_trigger_extrema_and_gap_fills_both_sides(self):
        p = dict(side=1, stop_price=95, target_price=110)
        cfg = m.Config(spread_bps=0, slippage=0)
        self.assertEqual(m.bar_exit(p, (100, 120, 80, 100, .01), cfg), (95, "STOP", True))
        self.assertEqual(m.bar_exit(p, (90, 100, 85, 98, .01), cfg)[0], 90)
        self.assertEqual(m.bar_exit(p, (100, 120, 80, 100, .01),
            m.Config(spread_bps=0, slippage=0, execution="extrema"))[0], 80)
        p = dict(side=-1, stop_price=105, target_price=90)
        self.assertEqual(m.bar_exit(p, (100, 120, 80, 100, .01), cfg), (105, "STOP", True))
        self.assertEqual(m.bar_exit(p, (115, 120, 100, 110, .01), cfg)[0], 115)

    def test_next_bar_entries_and_exact_long_short_accounting(self):
        for side, terminal in ((1, 110), (-1, 90)):
            cfg = m.Config(mode="synthetic_long_short")
            market = [(START, {"BTC/USD":((100, 100, 100, 100, .001), [signal(side=side, stop=.1, target=.2)])}),
                (START+m.BAR, {"BTC/USD":((terminal, terminal, terminal, terminal, .001), [])})]
            result = m.simulate(market, cfg)
            self.assertEqual(len(result["trades"]), 1)
            t = result["trades"][0]
            self.assertEqual(t["entry_ms"], t["signal_ms"]+m.BAR)
            expected_entry = m.entry_price(100, side, cfg)
            expected_exit = m.exit_price(terminal, side, cfg)
            expected_gross = t["stake"]*(expected_exit/expected_entry-1)*side
            self.assertAlmostEqual(t["gross_pnl"], expected_gross)
            self.assertAlmostEqual(t["exit_fee"], t["stake"]*expected_exit/expected_entry*.008)
            self.assertAlmostEqual(t["pnl"], expected_gross-t["entry_fee"]-t["exit_fee"]-t["carry"])
            self.assertAlmostEqual(result["summary"]["ending_equity"], 100+t["pnl"])
        with self.assertRaisesRegex(ValueError, "previous closed"):
            m.simulate([(START, {"BTC/USD":((100, 100, 100, 100, .001),
                [m.Signal("breakout", 1, 3, .02, .06, 96, START)])})], m.Config())

    def test_shared_cash_conflicts_and_capacity_scaling(self):
        rows = {p:((100, 100, 100, 100, .001), [signal()]) for p in m.PAIRS}
        result = m.simulate([(START, rows)], m.Config(family="breakout", risk="aggressive"))
        self.assertEqual(result["summary"]["max_concurrent"], 2)
        self.assertLessEqual(result["summary"]["max_reserved_notional"], 80)
        self.assertAlmostEqual(result["summary"]["ending_equity"], 100+sum(t["pnl"] for t in result["trades"]))
        larger = m.simulate([(START, rows)], m.Config(family="breakout", risk="aggressive", starting_balance=300))
        self.assertEqual(larger["summary"]["max_concurrent"], 6)
        self.assertLessEqual(larger["summary"]["max_reserved_notional"], 240)
        conflicting = {"BTC/USD":((100, 100, 100, 100, .001), [signal(), signal("range_reversal", -1)])}
        result = m.simulate([(START, conflicting)], m.Config(mode="synthetic_long_short"))
        self.assertEqual(result["summary"]["trades"], 0)
        self.assertEqual(result["summary"]["diagnostics"]["conflicting_sides"], 1)

    def test_fee_tiers_use_only_past_rolling_volume(self):
        fees = m.Fees()
        self.assertEqual(fees.rate(START), .008)
        fees.record(START, 2500)
        self.assertEqual(fees.rate(START+1), .006)
        self.assertEqual(fees.rate(START+30*m.DAY), .008)

    def test_gap_can_overshoot_drawdown_trigger(self):
        rows = {p:((100, 100, 100, 100, .001), [signal(stop=.01, target=.2)]) for p in ("BTC/USD", "ETH/USD")}
        fall = {p:((40, 40, 40, 40, .001), []) for p in rows}
        result = m.simulate([(START, rows), (START+m.BAR, fall)], m.Config(family="breakout"))
        self.assertTrue(result["summary"]["halted"])
        self.assertGreater(result["summary"]["max_drawdown_pct"], 25)

    def test_missing_end_mark_remains_pending(self):
        market = [(START, {"BTC/USD":((100, 100, 100, 100, .001), [signal()])}),
            (START+m.BAR, {"ETH/USD":((100, 100, 100, 100, .001), [])})]
        result = m.simulate(market, m.Config())
        self.assertEqual(result["summary"]["pending_positions"], 1)
        self.assertEqual(result["summary"]["trades"], 0)

    def test_month_schedule_does_not_open_before_selected_month(self):
        result = m.simulate([(START, {"BTC/USD":((100, 100, 100, 100, .001), [signal()])})],
            m.Config(), family_schedule={"2026-01":None, "2026-02":"breakout"})
        self.assertEqual(result["summary"]["trades"], 0)

    def test_selector_uses_previous_month_and_keeps_cash_after_losses(self):
        windows = [(name, 0, 1, False) for name in ("2026-01", "2026-02", "2026-03")]
        months = {"breakout":[dict(return_pct=r, pending_positions=0) for r in (5, -2, 900)],
            "pullback":[dict(return_pct=r, pending_positions=0) for r in (1, -1, 1000)]}
        self.assertEqual(m.prior_month_schedule(windows, months),
            {"2026-01":None, "2026-02":"breakout", "2026-03":None})

    def test_past_signal_compilation_and_trailing_apply_next_bar(self):
        f = frame(600)
        compiled = m.compile_market({"BTC/USD":f})
        candidates = [(now, s) for now, rows in compiled for _, sigs in rows.values() for s in sigs]
        self.assertTrue(candidates)
        self.assertTrue(all(now == s.signal_ms+m.BAR for now, s in candidates))
        # This bar's high sets a tighter stop for the following bar only.
        market = [(START, {"BTC/USD":((100, 104, 98.5, 103, .001), [signal(stop=.02, target=.2)])}),
            (START+m.BAR, {"BTC/USD":((103, 103, 103, 103, .001), [])})]
        result = m.simulate(market, m.Config(spread_bps=0, slippage=0))
        self.assertEqual(result["trades"][0]["exit_ms"], START+2*m.BAR-1)
        self.assertEqual(result["trades"][0]["reason"], "WINDOW_END")

    def test_operating_costs_charge_elapsed_time_including_feed_gaps(self):
        market = [(START, {"BTC/USD":((100, 100, 100, 100, .001), [])}),
            (START+3*m.BAR, {"BTC/USD":((100, 100, 100, 100, .001), [])})]
        result = m.simulate(market, m.Config(daily_operating_cost_usd=96))
        self.assertEqual(result["summary"]["operating_cost_usd"], 4)
        self.assertEqual(result["summary"]["ending_equity"], 96)

    def test_entry_drift_and_actual_range_target_room_are_checked(self):
        sig = m.Signal("breakout", 1, 3, .02, .06, 96, START-m.BAR, 100, .001)
        result = m.simulate([(START, {"BTC/USD":((105, 105, 105, 105, .001), [sig])})], m.Config())
        self.assertEqual(result["summary"]["trades"], 0)
        self.assertEqual(result["summary"]["diagnostics"]["opening_price_drift"], 1)
        sig = m.Signal("range_reversal", 1, 3, .02, .03, 96, START-m.BAR, 100, .001)
        result = m.simulate([(START, {"BTC/USD":((101, 101, 101, 101, .001), [sig])})], m.Config())
        self.assertEqual(result["summary"]["trades"], 0)
        self.assertEqual(result["summary"]["diagnostics"]["target_below_cost_buffer"], 1)

    def test_cli_writes_serializable_reports_without_touching_forward_state(self):
        frames = {p:frame(400) for p in m.PAIRS}
        with tempfile.TemporaryDirectory() as d:
            args = ["lab", "--data-dir", "fixture", "--output-dir", d, "--families", "blend",
                "--risks", "balanced", "--modes", "long_only", "--spreads", "5", "--executions", "trigger"]
            with patch.object(m, "load_frames", return_value=(frames, [{"kind":"TEST_FIXTURE"}])), patch("sys.argv", args):
                m.main()
            import json
            report = json.loads((Path(d)/"multi-strategy-summary.json").read_text())
            self.assertEqual(report["status"], "DEVELOPMENT_ONLY_NO_ACTIVATION")
            self.assertEqual(len(report["reports"]), 1)
            self.assertTrue((Path(d)/"multi-strategy-results.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
