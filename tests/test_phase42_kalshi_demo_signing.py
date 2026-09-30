import unittest
from decimal import Decimal

from signal_vault.cross_market_risk import assess_new_risk
from signal_vault.kalshi_demo_signing import build_kalshi_demo_signed_order_request
from signal_vault.multimarket_execution_journal import MultiMarketOrderDraft
from signal_vault.multimarket_paper_router import (
    KALSHI_DEMO_ACK,
    KALSHI_DEMO_ROOT,
    KALSHI_ORDER_PATH,
    route_paper_execution,
)


def risk():
    return assess_new_risk(
        lane="kalshi_event_contract",
        proposed_max_loss_usd=Decimal("5"),
        exposure_by_lane={},
        open_positions=0,
        marked_equity_usd=Decimal("100"),
        daily_anchor_equity_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        operator_halted=False,
    )


class KalshiDemoSigningContractTests(unittest.TestCase):
    def test_presign_message_matches_current_documented_contract(self):
        draft=MultiMarketOrderDraft(
            "k1","kalshi_event_contract","TEST-MARKET",Decimal("5"),
            {
                "ticker":"TEST-MARKET","side":"bid","count":"1","price":"0.0100",
                "time_in_force":"good_till_canceled",
                "self_trade_prevention_type":"taker_at_cross",
                "client_order_id":"k1",
            },
        )
        route=route_paper_execution(draft,risk_assessment=risk())
        seen=[]
        req=build_kalshi_demo_signed_order_request(
            route,
            key_id="demo-key-id",
            timestamp_ms=1700000000123,
            signer=lambda text:(seen.append(text) or "base64-signature"),
            acknowledgement=KALSHI_DEMO_ACK,
        )
        self.assertEqual(
            seen,
            ["1700000000123POST/trade-api/v2/portfolio/events/orders"],
        )
        self.assertEqual(req.method,"POST")
        self.assertEqual(req.path,KALSHI_ORDER_PATH)
        self.assertEqual(req.url,KALSHI_DEMO_ROOT+KALSHI_ORDER_PATH)
        self.assertEqual(req.headers["KALSHI-ACCESS-KEY"],"demo-key-id")
        self.assertEqual(req.headers["KALSHI-ACCESS-SIGNATURE"],"base64-signature")
        self.assertEqual(req.headers["KALSHI-ACCESS-TIMESTAMP"],"1700000000123")
        self.assertFalse(req.as_dict()["live_trading"]!="UNAVAILABLE")

    def test_wrong_ack_empty_key_or_empty_signature_fail_before_network(self):
        draft=MultiMarketOrderDraft(
            "k2","kalshi_event_contract","TEST",Decimal("5"),
            {
                "ticker":"TEST","side":"ask","count":"2.50","price":"0.500000",
                "time_in_force":"immediate_or_cancel",
                "self_trade_prevention_type":"maker",
                "client_order_id":"k2",
            },
        )
        route=route_paper_execution(draft,risk_assessment=risk())
        with self.assertRaises(PermissionError):
            build_kalshi_demo_signed_order_request(
                route,key_id="demo",timestamp_ms=1,
                signer=lambda _:"sig",acknowledgement="live",
            )
        with self.assertRaises(ValueError):
            build_kalshi_demo_signed_order_request(
                route,key_id="",timestamp_ms=1,
                signer=lambda _:"sig",acknowledgement=KALSHI_DEMO_ACK,
            )
        with self.assertRaises(ValueError):
            build_kalshi_demo_signed_order_request(
                route,key_id="demo",timestamp_ms=1,
                signer=lambda _:"",acknowledgement=KALSHI_DEMO_ACK,
            )


if __name__=="__main__":
    unittest.main()
