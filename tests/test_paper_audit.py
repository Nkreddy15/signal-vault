import unittest
from decimal import Decimal

from signal_vault.paper_audit import audit_fill_activities
from signal_vault.paper_order_state import PaperOrderState, Stage

ORDER = "12345678-1234-1234-1234-123456789abc"


def terminal(qty="0.00020", price="65000"):
    return PaperOrderState("client-1", Stage.BROKER_TERMINAL_UNRECONCILED,
                           ORDER, "filled", Decimal(qty), Decimal(price), False)


def fill(activity_id, qty, price, side="buy"):
    return {"activity_type": "FILL", "type": "fill", "id": activity_id,
            "order_id": ORDER, "symbol": "BTCUSD", "side": side,
            "qty": qty, "price": price}


class FillAuditTests(unittest.TestCase):
    def test_multiple_fill_activities_reconcile_quantity_and_weighted_price(self):
        a = [fill("a::1", "0.00010", "64000"), fill("b::2", "0.00010", "66000")]
        result = audit_fill_activities(terminal(), a)
        self.assertTrue(result.verified)
        self.assertEqual(result.cumulative_qty, Decimal("0.00020"))
        self.assertEqual(result.weighted_avg_price, Decimal("65000"))

    def test_wrong_order_duplicate_or_quantity_mismatch_fails(self):
        wrong = fill("a::1", "0.00020", "65000"); wrong["order_id"] = "other"
        with self.assertRaises(ValueError): audit_fill_activities(terminal(), [wrong])
        with self.assertRaises(ValueError): audit_fill_activities(terminal(), [fill("a::1", "0.00010", "65000")])
        with self.assertRaises(ValueError): audit_fill_activities(terminal(), [fill("a::1", "0.00010", "65000"), fill("a::1", "0.00010", "65000")])

    def test_zero_fill_terminal_requires_no_fill_activities(self):
        state = PaperOrderState("client-1", Stage.BROKER_TERMINAL_UNRECONCILED,
                                ORDER, "canceled", Decimal("0"), None, False)
        self.assertTrue(audit_fill_activities(state, []).verified)
        with self.assertRaises(ValueError):
            audit_fill_activities(state, [fill("a::1", "0.0001", "65000")])

    def test_order_average_must_match_activity_weighted_price(self):
        with self.assertRaises(ValueError):
            audit_fill_activities(terminal(price="65010"), [fill("a::1", "0.00020", "65000")])

from signal_vault.paper_audit import audit_crypto_fee_activities

class CryptoFeeAuditTests(unittest.TestCase):
    def test_empty_fee_result_is_not_final(self):
        result = audit_crypto_fee_activities(ORDER, [])
        self.assertFalse(result.final)
        self.assertEqual(result.fee_usd_equivalent, Decimal("0"))

    def test_cfee_and_fee_are_converted_to_usd_equivalent(self):
        result = audit_crypto_fee_activities(ORDER, [
            {"id":"fee::1", "activity_type":"CFEE", "order_id":ORDER,
             "symbol":"BTCUSD", "qty":"-0.000001", "price":"65000"},
            {"id":"fee::2", "activity_type":"FEE", "order_id":ORDER,
             "symbol":"BTCUSD", "net_amount":"-0.02"},
        ])
        self.assertTrue(result.final)
        self.assertEqual(result.fee_usd_equivalent, Decimal("0.085000"))

    def test_positive_or_wrong_order_fee_fails(self):
        with self.assertRaises(ValueError):
            audit_crypto_fee_activities(ORDER, [{"id":"x","activity_type":"CFEE",
                "order_id":ORDER,"symbol":"BTCUSD","qty":"0.1","price":"65000"}])
        with self.assertRaises(ValueError):
            audit_crypto_fee_activities(ORDER, [{"id":"x","activity_type":"FEE",
                "order_id":"other","net_amount":"-0.01"}])
