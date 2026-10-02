import unittest
from decimal import Decimal

from signal_vault.cross_market_risk import assess_new_risk, assess_position_reduction
from signal_vault.experimental_paper_cleanup import cleanup_once
from signal_vault.multimarket_execution_journal import MultiMarketOrderDraft
from signal_vault.multimarket_paper_router import route_paper_execution
from signal_vault.paper_credentials import PaperCredentials


SOURCE={
    "kind":"EXPERIMENTAL_PAPER_ACCOUNT_READ_ONLY_INVENTORY",
    "status":"AVAILABLE",
    "position_count":1,
    "open_order_count":0,
    "all_positions_are_btc_only":True,
    "order_submission":"DISABLED",
    "automatic_close_position":"DISABLED",
    "live_trading":"UNAVAILABLE",
    "positions":[{
        "symbol":"BTCUSD",
        "side":"long",
        "qty":"0.000175497",
        "market_value_usd":"15.199638",
        "avg_entry_price":"83579.004083774",
        "current_price":"86609.103",
        "unrealized_pl_usd":"0.531774",
    }],
}


class Reader:
    qty="0.000175497"
    def __init__(self,*args,**kwargs): pass
    def get_positions(self):
        return ({
            "symbol":"BTCUSD","side":"long","qty":self.qty,
            "market_value":"15.199638","current_price":"86609.103",
        },)
    def get_open_orders(self): return ()
    def get_btc_asset(self):
        return {
            "symbol":"BTC/USD","class":"crypto","status":"active",
            "tradable":True,"fractionable":True,
            "min_order_size":"0.00001",
            "min_trade_increment":"0.000000001",
            "price_increment":"1",
        }
    def lookup_order(self,client_id): return None


class Phase164PaperCleanupTests(unittest.TestCase):
    def test_position_reduction_governor_projects_exposure_down(self):
        r=assess_position_reduction(
            lane="crypto",
            current_lane_exposure_usd=Decimal("15.20"),
            proposed_reduction_usd=Decimal("15.20"),
            open_positions=1,
            operator_halted=False,
        )
        self.assertTrue(r["risk_admissible"])
        self.assertEqual(r["projected_lane_exposure_usd"],"0.00")
        self.assertTrue(r["position_reduction_only"])

    def test_sell_route_requires_reduction_receipt(self):
        draft=MultiMarketOrderDraft(
            "cleanup1","crypto","BTC/USD",Decimal("15.20"),
            {
                "symbol":"BTC/USD","side":"sell","type":"market",
                "time_in_force":"gtc","qty":"0.000175497",
                "client_order_id":"cleanup1",
            },
        )
        reduction=assess_position_reduction(
            lane="crypto",
            current_lane_exposure_usd=Decimal("15.20"),
            proposed_reduction_usd=Decimal("15.20"),
            open_positions=1,
            operator_halted=False,
        )
        route=route_paper_execution(draft,risk_assessment=reduction)
        self.assertEqual(route.payload["side"],"sell")

        additive=assess_new_risk(
            lane="crypto",
            proposed_max_loss_usd=Decimal("5"),
            exposure_by_lane={},
            open_positions=0,
            marked_equity_usd=Decimal("100"),
            daily_anchor_equity_usd=Decimal("100"),
            peak_equity_usd=Decimal("100"),
            operator_halted=False,
        )
        with self.assertRaises(PermissionError):
            route_paper_execution(draft,risk_assessment=additive)

    def test_cleanup_preview_is_exact_qty_and_no_post(self):
        from datetime import datetime, timezone
        out=cleanup_once(
            source_inventory=SOURCE,
            credentials=PaperCredentials("paper-key","paper-secret"),
            now=datetime(2026,10,2,5,15,tzinfo=timezone.utc),
            reader_factory=Reader,
        )
        self.assertEqual(out["status"],"READY_FOR_EXPLICIT_PAPER_POSITION_CLEANUP")
        self.assertEqual(out["reviewed_qty"],"0.000175497")
        self.assertEqual(out["fresh_qty"],"0.000175497")
        self.assertFalse(out["paper_post_attempted"])
        self.assertEqual(out["paper_order_submission"],"DISABLED")
        self.assertEqual(out["risk_assessment"]["projected_lane_exposure_usd"],"0.000000")
        self.assertEqual(out["live_trading"],"UNAVAILABLE")

    def test_changed_provider_qty_blocks_cleanup(self):
        from datetime import datetime, timezone
        class Changed(Reader):
            qty="0.000175496"
        with self.assertRaises(PermissionError):
            cleanup_once(
                source_inventory=SOURCE,
                credentials=PaperCredentials("paper-key","paper-secret"),
                now=datetime(2026,10,2,5,15,tzinfo=timezone.utc),
                reader_factory=Changed,
            )


if __name__=="__main__":
    unittest.main()
