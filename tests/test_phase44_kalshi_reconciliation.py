import unittest
from decimal import Decimal

from signal_vault.kalshi_reconciliation import kalshi_order_and_fills_observation


def order(status="resting",fill="0.00",remaining="10.00",initial="10.00"):
    return {"order":{
        "order_id":"oid-1",
        "client_order_id":"cid-1",
        "status":status,
        "fill_count_fp":fill,
        "remaining_count_fp":remaining,
        "initial_count_fp":initial,
    }}


class KalshiReconciliationTests(unittest.TestCase):
    def test_resting_zero_fill_maps_to_accepted(self):
        obs=kalshi_order_and_fills_observation(
            order_payload=order(),
            fills_payload={"fills":[]},
            expected_client_order_id="cid-1",
        )
        self.assertEqual(obs.provider_status,"accepted")
        self.assertEqual(obs.cumulative_filled_qty,Decimal("0"))
        self.assertIsNone(obs.filled_avg_price)

    def test_resting_partial_fill_uses_weighted_provider_fill_price(self):
        obs=kalshi_order_and_fills_observation(
            order_payload=order(fill="3.00",remaining="7.00"),
            fills_payload={"fills":[
                {"fill_id":"f1","order_id":"oid-1","count_fp":"1.00",
                 "yes_price_dollars":"0.2000"},
                {"fill_id":"f2","order_id":"oid-1","count_fp":"2.00",
                 "yes_price_dollars":"0.3500"},
            ]},
            expected_client_order_id="cid-1",
        )
        self.assertEqual(obs.provider_status,"partially_filled")
        self.assertEqual(obs.cumulative_filled_qty,Decimal("3.00"))
        self.assertEqual(obs.filled_avg_price,Decimal("0.3"))

    def test_executed_maps_to_filled_only_when_counts_fully_reconcile(self):
        obs=kalshi_order_and_fills_observation(
            order_payload=order(status="executed",fill="10",remaining="0"),
            fills_payload={"fills":[
                {"fill_id":"f1","order_id":"oid-1","count_fp":"10",
                 "yes_price_dollars":"0.42"},
            ]},
            expected_client_order_id="cid-1",
        )
        self.assertEqual(obs.provider_status,"filled")
        self.assertEqual(obs.filled_avg_price,Decimal("0.42"))

    def test_canceled_with_partial_fill_preserves_fill_economics(self):
        obs=kalshi_order_and_fills_observation(
            order_payload=order(status="canceled",fill="2",remaining="8"),
            fills_payload={"fills":[
                {"fill_id":"f1","order_id":"oid-1","count_fp":"2",
                 "yes_price_dollars":"0.61"},
            ]},
            expected_client_order_id="cid-1",
        )
        self.assertEqual(obs.provider_status,"canceled")
        self.assertEqual(obs.cumulative_filled_qty,Decimal("2"))
        self.assertEqual(obs.filled_avg_price,Decimal("0.61"))

    def test_mismatch_duplicate_foreign_or_unsupported_records_fail_closed(self):
        cases=[
            (order(fill="2",remaining="8"),{"fills":[]},"cid-1"),
            (order(fill="1",remaining="9"),{"fills":[
                {"fill_id":"f1","order_id":"other","count_fp":"1",
                 "yes_price_dollars":"0.5"}]},"cid-1"),
            (order(fill="2",remaining="8"),{"fills":[
                {"fill_id":"f1","order_id":"oid-1","count_fp":"1",
                 "yes_price_dollars":"0.5"},
                {"fill_id":"f1","order_id":"oid-1","count_fp":"1",
                 "yes_price_dollars":"0.5"}]},"cid-1"),
            (order(status="executed",fill="9",remaining="1"),{"fills":[
                {"fill_id":"f1","order_id":"oid-1","count_fp":"9",
                 "yes_price_dollars":"0.5"}]},"cid-1"),
            (order(status="unknown"),{"fills":[]},"cid-1"),
            (order(),{"fills":[]},"wrong-client"),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                kalshi_order_and_fills_observation(
                    order_payload=args[0],
                    fills_payload=args[1],
                    expected_client_order_id=args[2],
                )


if __name__=="__main__":
    unittest.main()
