import unittest
from decimal import Decimal

from signal_vault.cross_market_risk import assess_new_risk
from signal_vault.multimarket_execution_journal import MultiMarketOrderDraft
from signal_vault.multimarket_paper_router import (
    ALPACA_PAPER_ROOT,
    CRYPTO_PAPER_ACK,
    EQUITY_PAPER_ACK,
    KALSHI_DEMO_ACK,
    paper_submission_authorized,
    route_paper_execution,
)


def risk(lane: str):
    return assess_new_risk(
        lane=lane,
        proposed_max_loss_usd=Decimal("5"),
        exposure_by_lane={},
        open_positions=0,
        marked_equity_usd=Decimal("100"),
        daily_anchor_equity_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        operator_halted=False,
    )


class MultiMarketPaperRouterTests(unittest.TestCase):
    def test_crypto_routes_only_to_alpaca_paper(self):
        draft = MultiMarketOrderDraft(
            "c1","crypto","BTC/USD",Decimal("5"),
            {
                "symbol":"BTC/USD","side":"buy","type":"market","time_in_force":"gtc",
                "notional":"5","client_order_id":"c1",
            },
        )
        route = route_paper_execution(draft,risk_assessment=risk("crypto"))
        self.assertEqual(route.provider,"alpaca")
        self.assertEqual(route.environment,"paper")
        self.assertTrue(route.endpoint.startswith(ALPACA_PAPER_ROOT))
        self.assertFalse(route.live_trading_available)
        self.assertFalse(paper_submission_authorized(route,""))
        self.assertTrue(paper_submission_authorized(route,CRYPTO_PAPER_ACK))

    def test_fractional_equity_requires_market_day_and_routes_to_paper(self):
        draft = MultiMarketOrderDraft(
            "e1","us_equity","SPY",Decimal("5"),
            {
                "symbol":"SPY","side":"buy","type":"market","time_in_force":"day",
                "notional":"5","client_order_id":"e1",
            },
        )
        route = route_paper_execution(draft,risk_assessment=risk("us_equity"))
        self.assertEqual(route.provider,"alpaca")
        self.assertEqual(route.environment,"paper")
        self.assertEqual(route.required_acknowledgement,EQUITY_PAPER_ACK)
        for bad in (
            {"type":"limit"},
            {"time_in_force":"gtc"},
            {"qty":"0.1","notional":"5"},
            {"symbol":"BTC/USD"},
        ):
            payload={**draft.payload,**bad}
            broken=MultiMarketOrderDraft(
                "e2","us_equity","SPY",Decimal("5"),
                {**payload,"client_order_id":"e2"},
            )
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                route_paper_execution(broken,risk_assessment=risk("us_equity"))

    def test_kalshi_stays_demo_and_has_no_endpoint_until_signed_adapter(self):
        draft = MultiMarketOrderDraft(
            "k1","kalshi_event_contract","TEST-MARKET",Decimal("5"),
            {
                "ticker":"TEST-MARKET","side":"yes","action":"buy",
                "count":"5","client_order_id":"k1",
            },
        )
        route = route_paper_execution(
            draft,risk_assessment=risk("kalshi_event_contract")
        )
        self.assertEqual(route.provider,"kalshi")
        self.assertEqual(route.environment,"demo")
        self.assertIsNone(route.endpoint)
        self.assertIn("NOT_YET_IMPLEMENTED",route.adapter)
        self.assertFalse(route.live_trading_available)
        self.assertTrue(paper_submission_authorized(route,KALSHI_DEMO_ACK))

    def test_risk_rejection_or_wrong_lane_blocks_before_route(self):
        draft = MultiMarketOrderDraft(
            "e3","us_equity","AAPL",Decimal("5"),
            {
                "symbol":"AAPL","side":"buy","type":"market","time_in_force":"day",
                "notional":"5","client_order_id":"e3",
            },
        )
        blocked = assess_new_risk(
            lane="us_equity",
            proposed_max_loss_usd=Decimal("5"),
            exposure_by_lane={},
            open_positions=0,
            marked_equity_usd=Decimal("100"),
            daily_anchor_equity_usd=Decimal("100"),
            peak_equity_usd=Decimal("100"),
            operator_halted=True,
        )
        with self.assertRaises(PermissionError):
            route_paper_execution(draft,risk_assessment=blocked)
        with self.assertRaises(PermissionError):
            route_paper_execution(draft,risk_assessment=risk("crypto"))

    def test_wrong_ack_never_becomes_authorized(self):
        draft = MultiMarketOrderDraft(
            "c2","crypto","ETH/USD",Decimal("5"),
            {
                "symbol":"ETH/USD","side":"buy","type":"market","time_in_force":"gtc",
                "notional":"5","client_order_id":"c2",
            },
        )
        route = route_paper_execution(draft,risk_assessment=risk("crypto"))
        self.assertFalse(paper_submission_authorized(route,EQUITY_PAPER_ACK))
        with self.assertRaises(PermissionError):
            route_paper_execution(
                draft,risk_assessment=risk("crypto"),acknowledgement="live"
            )


if __name__ == "__main__":
    unittest.main()
