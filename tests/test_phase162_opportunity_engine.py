from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.opportunity_engine import (
    AllocatorLimits,
    Direction,
    Market,
    Opportunity,
    allocate_opportunities,
)


NOW = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)


def _opportunity(
    candidate_id: str,
    *,
    market: Market,
    instrument: str,
    direction: Direction,
    gross: str,
    cost: str = "0.002",
    confidence: str = "0.70",
    max_loss: str = "0.05",
    group: str = "default",
    paper: bool = True,
):
    return Opportunity(
        market=market,
        instrument=instrument,
        candidate_id=candidate_id,
        strategy_family="phase162-test-family",
        direction=direction,
        generated_utc=NOW - timedelta(minutes=1),
        valid_until_utc=NOW + timedelta(hours=1),
        horizon_seconds=3600,
        expected_gross_return=Decimal(gross),
        estimated_round_trip_cost_return=Decimal(cost),
        confidence=Decimal(confidence),
        max_loss_return=Decimal(max_loss),
        evidence_id=f"evidence:{candidate_id}",
        correlation_group=group,
        paper_executable=paper,
    )


class Phase162OpportunityEngineTests(unittest.TestCase):
    def test_cross_market_candidates_compete_in_one_ranker(self):
        opportunities = (
            _opportunity(
                "crypto-btc",
                market=Market.CRYPTO,
                instrument="BTC/USD",
                direction=Direction.LONG,
                gross="0.020",
                group="crypto-beta",
            ),
            _opportunity(
                "stock-nvda",
                market=Market.US_EQUITY,
                instrument="NVDA",
                direction=Direction.LONG,
                gross="0.018",
                confidence="0.80",
                max_loss="0.03",
                group="growth-equity",
            ),
            _opportunity(
                "event-fed",
                market=Market.EVENT_CONTRACT,
                instrument="KALSHI:TEST",
                direction=Direction.YES,
                gross="0.030",
                confidence="0.60",
                max_loss="0.10",
                group="macro-event",
            ),
        )
        decision = allocate_opportunities(opportunities, as_of=NOW, mode="paper")
        self.assertEqual(len(decision.selected), 3)
        self.assertEqual(decision.total_exposure_usd, Decimal("45"))
        self.assertEqual(
            {item.opportunity.market for item in decision.selected},
            {Market.CRYPTO, Market.US_EQUITY, Market.EVENT_CONTRACT},
        )

    def test_after_cost_edge_is_required(self):
        weak = _opportunity(
            "weak",
            market=Market.CRYPTO,
            instrument="ETH/USD",
            direction=Direction.LONG,
            gross="0.005",
            cost="0.002",
        )
        decision = allocate_opportunities((weak,), as_of=NOW)
        self.assertEqual(len(decision.selected), 0)
        self.assertEqual(
            decision.rejected[0].reason,
            "INSUFFICIENT_AFTER_COST_EDGE",
        )

    def test_paper_mode_rejects_unverified_adapter(self):
        candidate = _opportunity(
            "not-paper-ready",
            market=Market.EVENT_CONTRACT,
            instrument="KALSHI:TEST",
            direction=Direction.NO,
            gross="0.025",
            paper=False,
        )
        research = allocate_opportunities((candidate,), as_of=NOW, mode="research")
        paper = allocate_opportunities((candidate,), as_of=NOW, mode="paper")
        self.assertEqual(len(research.selected), 1)
        self.assertEqual(len(paper.selected), 0)
        self.assertEqual(
            paper.rejected[0].reason,
            "PAPER_ADAPTER_NOT_VERIFIED",
        )

    def test_correlation_cap_prevents_four_equivalent_crypto_bets(self):
        items = tuple(
            _opportunity(
                f"crypto-{i}",
                market=Market.CRYPTO,
                instrument=f"COIN{i}/USD",
                direction=Direction.LONG,
                gross=str(Decimal("0.03") - Decimal(i) / Decimal("1000")),
                group="crypto-beta",
            )
            for i in range(4)
        )
        decision = allocate_opportunities(items, as_of=NOW)
        self.assertEqual(len(decision.selected), 2)
        self.assertEqual(
            sum(x.reason == "CORRELATION_GROUP_CAP" for x in decision.rejected),
            2,
        )

    def test_market_and_total_caps_are_deterministic(self):
        limits = AllocatorLimits(
            logical_capital_usd=Decimal("100"),
            max_total_exposure_usd=Decimal("45"),
            position_notional_usd=Decimal("15"),
            max_positions=4,
            max_positions_per_correlation_group=4,
            max_market_exposure_usd=(
                (Market.CRYPTO, Decimal("30")),
                (Market.US_EQUITY, Decimal("45")),
                (Market.EVENT_CONTRACT, Decimal("30")),
            ),
        )
        items = (
            _opportunity(
                "btc", market=Market.CRYPTO, instrument="BTC/USD",
                direction=Direction.LONG, gross="0.04", group="c1"
            ),
            _opportunity(
                "eth", market=Market.CRYPTO, instrument="ETH/USD",
                direction=Direction.LONG, gross="0.035", group="c2"
            ),
            _opportunity(
                "sol", market=Market.CRYPTO, instrument="SOL/USD",
                direction=Direction.LONG, gross="0.030", group="c3"
            ),
            _opportunity(
                "spy", market=Market.US_EQUITY, instrument="SPY",
                direction=Direction.LONG, gross="0.025", group="s1"
            ),
        )
        decision = allocate_opportunities(items, as_of=NOW, limits=limits)
        self.assertEqual(decision.total_exposure_usd, Decimal("45"))
        self.assertLessEqual(
            decision.market_exposure_usd[Market.CRYPTO],
            Decimal("30"),
        )

    def test_stale_opportunity_is_rejected(self):
        stale = Opportunity(
            market=Market.US_EQUITY,
            instrument="SPY",
            candidate_id="stale",
            strategy_family="test",
            direction=Direction.LONG,
            generated_utc=NOW - timedelta(hours=2),
            valid_until_utc=NOW - timedelta(minutes=1),
            horizon_seconds=3600,
            expected_gross_return=Decimal("0.02"),
            estimated_round_trip_cost_return=Decimal("0.001"),
            confidence=Decimal("0.70"),
            max_loss_return=Decimal("0.05"),
            evidence_id="evidence:stale",
            correlation_group="stocks",
            paper_executable=True,
        )
        decision = allocate_opportunities((stale,), as_of=NOW)
        self.assertEqual(decision.rejected[0].reason, "STALE_OPPORTUNITY")


if __name__ == "__main__":
    unittest.main()
