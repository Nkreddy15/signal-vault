"""Pure offline synthetic cost/gating and verified collector-summary tests.

No real transport, Keychain, broker, file journal mutation, machine scheduling,
actual strategy prediction, or trades are made by these tests.
"""
import contextlib
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from signal_vault.shadow_cost_gate import (
    ShadowCostPolicy, estimate_round_trip, inspect_offline_shadow_progress,
    main, review_shadow_signal,
)
from signal_vault.strategy import Action, StrategySignal


def fake_signal(action):
    return StrategySignal(
        action, "a" * 64, "2026-09-29T19:00:00+00:00",
        Decimal("65001"), Decimal("65000"),
        "synthetic signal ONLY", "btc-hourly-ema-cross-v0.1")


def fake_collector(count, *, decision="ONE_NEW_PROSPECTIVE_CANDLE_RECORDED"):
    return {
        "kind": "UNATTENDED_FORWARD_LOCAL_STATUS",
        "broker_order_submission": "DISABLED", "network_requests": "NONE",
        "state": "ARCHIVED_INTERNAL_EVIDENCE_VERIFIED",
        "prospective_observations_verified": count,
        "latest_tick": {"decision": decision, "failure_class": None},
    }


class ShadowCostMathTests(unittest.TestCase):
    def test_default_fee_spread_and_slippage_have_nontrivial_hurdle(self):
        v = estimate_round_trip(spread_bps=Decimal("3"))
        self.assertGreater(v.break_even_move_bps, Decimal("70"))
        self.assertLess(v.break_even_move_bps, Decimal("80"))
        self.assertGreater(v.target_move_bps, v.break_even_move_bps)
        self.assertGreater(v.target_move_bps, Decimal("90"))
        self.assertLess(v.target_move_bps, Decimal("100"))
        self.assertEqual(v.buy_fee_estimate_usd, Decimal("0.0375"))
        self.assertGreater(v.loss_on_flat_mid_usd, Decimal("0.10"))
        self.assertLess(v.loss_on_flat_mid_usd, Decimal("0.12"))
        serialized = v.to_dict()
        self.assertEqual(serialized["hypothetical_buy_notional_usd"], "15")
        self.assertEqual(serialized["buy_taker_fee_bps"], "25")
        self.assertIn("NOT a live quote", serialized["disclosure"])
        self.assertGreaterEqual(
            Decimal(serialized["target_gross_midprice_rise_bps_rounded_up"]),
            v.target_move_bps)
        self.assertGreaterEqual(
            Decimal(serialized["break_even_gross_midprice_rise_bps_rounded_up"]),
            v.break_even_move_bps)

    def test_zero_friction_break_even_is_exactly_zero_and_net_target_is_exact(self):
        p = ShadowCostPolicy(
            Decimal("0"), Decimal("0"), Decimal("0"),
            Decimal("0"), Decimal("20"), Decimal("15"))
        e = estimate_round_trip(spread_bps=Decimal("0"), policy=p)
        self.assertEqual(e.break_even_move_bps, Decimal("0"))
        self.assertEqual(e.target_move_bps, Decimal("20"))
        self.assertEqual(e.loss_on_flat_mid_usd, Decimal("0"))

    def test_increasing_spread_or_slippage_raises_required_return(self):
        base = estimate_round_trip(spread_bps=Decimal("0"))
        wide = estimate_round_trip(spread_bps=Decimal("40"))
        self.assertGreater(wide.break_even_move_bps, base.break_even_move_bps)
        self.assertGreater(wide.target_move_bps, base.target_move_bps)
        high_slip = ShadowCostPolicy(
            entry_slippage_allowance_bps=Decimal("30"),
            exit_slippage_allowance_bps=Decimal("30"))
        high = estimate_round_trip(spread_bps=Decimal("3"), policy=high_slip)
        self.assertGreater(high.target_move_bps,
                           estimate_round_trip(spread_bps=Decimal("3")).target_move_bps)

    def test_invalid_fee_spread_budget_and_nan_fail_closed(self):
        for v in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity"),
                  Decimal("1001"), "3", True):
            with self.subTest(value=v), self.assertRaises(ValueError):
                estimate_round_trip(spread_bps=v)
        with self.assertRaises(ValueError):
            ShadowCostPolicy(buy_taker_fee_bps=Decimal("-1"))
        with self.assertRaises(ValueError):
            ShadowCostPolicy(hypothetical_notional_usd=Decimal("100"))
        with self.assertRaises(ValueError):
            ShadowCostPolicy(buy_taker_fee_bps=25)


class ShadowSignalGateTests(unittest.TestCase):
    def setUp(self):
        self.cost = estimate_round_trip(spread_bps=Decimal("3"))

    def test_plain_ema_buy_is_vetoed_without_independent_forecast(self):
        result = review_shadow_signal(signal=fake_signal(Action.BUY), costs=self.cost)
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["reason_code"],
                         "BUY_VETO_NO_INDEPENDENT_PROSPECTIVE_EDGE_EVIDENCE")
        self.assertFalse(result["strategy_promoted"])
        self.assertEqual(result["broker_order_submission"], "DISABLED")

    def test_made_up_move_without_prospective_validation_is_not_accepted(self):
        result = review_shadow_signal(
            signal=fake_signal(Action.BUY), costs=self.cost,
            forecast_midprice_rise_bps=Decimal("1000"),
            independent_prospective_validation=False)
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["reason_code"],
                         "BUY_VETO_NO_INDEPENDENT_PROSPECTIVE_EDGE_EVIDENCE")

    def test_validated_research_estimate_below_hurdle_holds(self):
        result = review_shadow_signal(
            signal=fake_signal(Action.BUY), costs=self.cost,
            forecast_midprice_rise_bps=self.cost.target_move_bps - Decimal("0.001"),
            independent_prospective_validation=True)
        self.assertEqual(result["reason_code"],
                         "BUY_VETO_ESTIMATED_MOVE_BELOW_AFTER_COST_TARGET")
        self.assertEqual(result["decision"], "HOLD")

    def test_even_above_hurdle_never_promotes_or_authorizes_order(self):
        result = review_shadow_signal(
            signal=fake_signal(Action.BUY), costs=self.cost,
            forecast_midprice_rise_bps=Decimal("200"),
            independent_prospective_validation=True)
        self.assertEqual(result["decision"],
                         "RESEARCH_ONLY_BUY_CANDIDATE_PASSES_COST_ASSUMPTIONS")
        self.assertFalse(result["strategy_promoted"])
        self.assertEqual(result["automatic_trading"], "DISABLED")
        self.assertEqual(result["broker_order_submission"], "DISABLED")

    def test_risk_reducing_sell_is_not_profit_hurdle_vetoed(self):
        result = review_shadow_signal(signal=fake_signal(Action.SELL), costs=self.cost)
        self.assertEqual(result["decision"],
                         "SELL_CANDIDATE_REQUIRES_SEPARATE_POSITION_RISK_REVIEW")
        self.assertFalse(result["strategy_promoted"])
        self.assertEqual(result["broker_order_submission"], "DISABLED")

    def test_hold_is_never_transformed_into_buy(self):
        result = review_shadow_signal(
            signal=fake_signal(Action.HOLD), costs=self.cost,
            forecast_midprice_rise_bps=Decimal("1000"),
            independent_prospective_validation=True)
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["reason_code"], "NO_SIGNAL")

    def test_bad_forecasts_do_not_pass(self):
        for value in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity"),
                      Decimal("100001"), "1000"):
            with self.subTest(value=value):
                r = review_shadow_signal(
                    signal=fake_signal(Action.BUY), costs=self.cost,
                    forecast_midprice_rise_bps=value,
                    independent_prospective_validation=True)
                self.assertEqual(r["decision"], "HOLD")
                self.assertEqual(r["reason_code"], "BUY_VETO_INVALID_EXPECTED_MOVE")


class OfflineResearchStatusTests(unittest.TestCase):
    def test_owner_one_genuine_prospective_bar_is_counted_not_profit_claim(self):
        report = inspect_offline_shadow_progress(
            collector_reader=lambda **_: fake_collector(1))
        self.assertEqual(report["prospective_observations_verified"], 1)
        self.assertEqual(report["research_status"],
                         "ACCUMULATING_PROSPECTIVE_OBSERVATIONS")
        self.assertEqual(report["minimum_prospective_bars_for_INITIAL_sample_review"], 168)
        self.assertFalse(report["strategy_promoted"])
        self.assertEqual(report["broker_order_submission"], "DISABLED")
        self.assertEqual(report["market_data_request"], "NONE")
        self.assertEqual(report["journal_modifications"], "NONE")
        self.assertIn("NOT evidence of a profitable strategy", report["warning"])

    def test_bootstrap_zero_and_threshold_do_not_claim_strategy_edge(self):
        zero = inspect_offline_shadow_progress(
            collector_reader=lambda **_: fake_collector(
                0, decision="FIRST_AUTO_SEGMENT_BOOTSTRAPPED"))
        self.assertEqual(zero["research_status"],
                         "AUTOMATIC_BOOTSTRAP_ONLY_NO_FORWARD_OBSERVATIONS")
        many = inspect_offline_shadow_progress(
            collector_reader=lambda **_: fake_collector(168))
        self.assertEqual(many["research_status"],
                         "MINIMUM_SAMPLE_COUNT_REACHED_NOT_EDGE_VALIDATION")
        self.assertFalse(many["strategy_promoted"])

    def test_halt_and_malformed_audit_do_not_count_old_observations(self):
        halted = inspect_offline_shadow_progress(
            collector_reader=lambda **_: fake_collector(
                50, decision="HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE"))
        self.assertEqual(halted["research_status"],
                         "COLLECTOR_HALTED_PRESERVE_ORIGINAL_EVIDENCE")
        self.assertEqual(halted["prospective_observations_verified"], 0)
        invalid = inspect_offline_shadow_progress(
            collector_reader=lambda **_: fake_collector(True))
        self.assertEqual(invalid["research_status"], "INVALID_COLLECTOR_AUDIT_RESULT")
        self.assertEqual(invalid["prospective_observations_verified"], 0)

    def test_missing_root_remains_missing_and_never_creates_forward_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "nonexistent-forward-root"
            r = inspect_offline_shadow_progress(forward_root=root)
            self.assertEqual(r["research_status"],
                             "NO_VERIFIED_AUTOMATIC_FORWARD_SEGMENT")
            self.assertFalse(root.exists())

    def test_reader_exception_does_not_leak_private_detail(self):
        def fail(**_):
            raise RuntimeError("SENTINEL_NOT_FOR_JSON")
        result = inspect_offline_shadow_progress(collector_reader=fail)
        self.assertEqual(result["research_status"], "COLLECTOR_AUDIT_UNAVAILABLE")
        self.assertEqual(result["failure_class"], "RuntimeError")
        self.assertNotIn("SENTINEL_NOT_FOR_JSON", json.dumps(result))

    def test_cli_does_not_start_broker_collector_or_other_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "forward-uninitialized"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["--forward-root", str(root), "--assumed-spread-bps", "2.86"])
            self.assertEqual(result, 2)  # missing collector evidence
            data = json.loads(output.getvalue())
            self.assertEqual(data["market_data_request"], "NONE")
            self.assertEqual(data["broker_order_submission"], "DISABLED")
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
