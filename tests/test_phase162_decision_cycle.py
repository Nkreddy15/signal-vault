from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.decision_cycle import run_decision_cycle
from signal_vault.multimarket_cycle import PaperRoute
from signal_vault.opportunity_engine import (
    AllocationPortfolioState,
    Direction,
    Market,
)
from signal_vault.signal_adapters import (
    directional_model_signal,
    event_probability_model_signal,
)


NOW = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)


def directional(
    market,
    instrument,
    model,
    evidence,
    prediction,
    cost,
    confidence,
    max_loss,
    group,
    *,
    long=True,
    short=False,
):
    return directional_model_signal(
        market=market,
        instrument=instrument,
        source_model=model,
        strategy_family="ml_return",
        predicted_signed_return=Decimal(prediction),
        estimated_round_trip_cost_return=Decimal(cost),
        confidence=Decimal(confidence),
        max_loss_return=Decimal(max_loss),
        generated_utc=NOW - timedelta(minutes=1),
        valid_until_utc=NOW + timedelta(hours=2),
        horizon_seconds=48 * 3600,
        evidence_id=evidence,
        correlation_group=group,
        paper_long_supported=long,
        paper_short_supported=short,
    )


def event(model, evidence, probability):
    return event_probability_model_signal(
        ticker="KXTEST",
        source_model=model,
        strategy_family="event_probability",
        estimated_yes_probability=Decimal(probability),
        probability_confidence=Decimal("0.72"),
        yes_ask_probability=Decimal("0.55"),
        no_ask_probability=Decimal("0.47"),
        estimated_round_trip_fee_return=Decimal("0.01"),
        generated_utc=NOW - timedelta(minutes=1),
        valid_until_utc=NOW + timedelta(minutes=10),
        horizon_seconds=86400,
        evidence_id=evidence,
        correlation_group="event:macro",
        paper_demo_supported=True,
    )


class Phase162DecisionCycleTests(unittest.TestCase):
    def setUp(self):
        self.routes = (
            PaperRoute(Market.CRYPTO, "crypto-paper-long-v1", True),
            PaperRoute(Market.US_EQUITY, "equity-paper-long-v1", True),
            PaperRoute(Market.EVENT_CONTRACT, "kalshi-demo-v1", True),
        )
        self.signals = tuple(
            item for item in (
                directional(
                    Market.CRYPTO, "BTC/USD", "crypto_rf48", "c1",
                    "0.030", "0.0074", "0.76", "0.05", "crypto-beta",
                ),
                directional(
                    Market.CRYPTO, "BTC/USD", "crypto_hgb48", "c2",
                    "0.027", "0.0074", "0.70", "0.05", "crypto-beta",
                ),
                directional(
                    Market.US_EQUITY, "NVDA", "stock_rf24", "s1",
                    "0.022", "0.0013", "0.75", "0.04", "growth-equity",
                ),
                directional(
                    Market.US_EQUITY, "NVDA", "stock_extra24", "s2",
                    "0.019", "0.0013", "0.71", "0.04", "growth-equity",
                ),
                event("event_calibration_a", "e1", "0.74"),
                event("event_calibration_b", "e2", "0.71"),
            )
            if item is not None
        )

    def test_one_brain_can_select_crypto_stock_and_event_together(self):
        result = run_decision_cycle(
            self.signals,
            as_of=NOW,
            routes=self.routes,
            mode="paper",
        )
        self.assertEqual(len(result.ensemble.opportunities), 3)
        self.assertEqual(len(result.plan.execution_intents), 3)
        self.assertEqual(
            {item.market for item in result.plan.execution_intents},
            {Market.CRYPTO, Market.US_EQUITY, Market.EVENT_CONTRACT},
        )
        # Binary event premium has 100% max-loss semantics, so shared risk
        # dynamically sizes that leg to $10 while normal $15 stakes remain.
        event_selected = next(
            item for item in result.plan.allocation.selected
            if item.opportunity.market is Market.EVENT_CONTRACT
        )
        self.assertEqual(
            event_selected.allocated_notional_usd,
            Decimal("10"),
        )
        self.assertEqual(
            result.plan.allocation.total_exposure_usd,
            Decimal("40"),
        )
        summary = result.summary()
        self.assertEqual(summary["planned_execution_intent_count"], 3)
        self.assertEqual(summary["order_submission"], "DISABLED")
        self.assertEqual(summary["live_trading"], "UNAVAILABLE")

    def test_one_narrow_signal_cannot_control_portfolio(self):
        lone = directional(
            Market.CRYPTO, "ETH/USD", "ema_only", "one",
            "0.04", "0.0074", "0.80", "0.05", "crypto-beta",
        )
        result = run_decision_cycle(
            (lone,),
            as_of=NOW,
            routes=self.routes,
            mode="paper",
        )
        self.assertEqual(result.ensemble.opportunities, ())
        self.assertEqual(result.plan.execution_intents, ())

    def test_shared_drawdown_halt_stops_all_markets(self):
        portfolio = AllocationPortfolioState(
            notional_exposure_usd={},
            risk_exposure_usd={},
            open_positions=0,
            open_instruments=frozenset(),
            marked_equity_usd=Decimal("89"),
            daily_anchor_equity_usd=Decimal("100"),
            peak_equity_usd=Decimal("100"),
        )
        result = run_decision_cycle(
            self.signals,
            as_of=NOW,
            routes=self.routes,
            portfolio=portfolio,
            mode="paper",
        )
        self.assertEqual(result.plan.execution_intents, ())
        self.assertTrue(result.plan.allocation.rejected)
        self.assertTrue(
            all(
                item.reason == "SHARED_RISK_GOVERNOR_REJECTED"
                for item in result.plan.allocation.rejected
            )
        )

    def test_live_mode_does_not_exist(self):
        with self.assertRaises(ValueError):
            run_decision_cycle(
                self.signals,
                as_of=NOW,
                routes=self.routes,
                mode="live",
            )


if __name__ == "__main__":
    unittest.main()
