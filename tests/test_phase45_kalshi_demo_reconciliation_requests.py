import unittest

from signal_vault.kalshi_demo_reconciliation_requests import (
    build_kalshi_demo_fills_lookup,
    build_kalshi_demo_order_lookup,
)
from signal_vault.multimarket_paper_router import KALSHI_DEMO_ROOT


class KalshiDemoReconciliationRequestTests(unittest.TestCase):
    def test_order_lookup_signs_exact_queryless_order_path(self):
        seen=[]
        req=build_kalshi_demo_order_lookup(
            order_id="abc-123",
            key_id="demo-key",
            timestamp_ms=1700000000123,
            signer=lambda text:(seen.append(text) or "sig"),
        )
        self.assertEqual(
            seen,
            ["1700000000123GET/trade-api/v2/portfolio/orders/abc-123"],
        )
        self.assertEqual(
            req.url,
            KALSHI_DEMO_ROOT+"/trade-api/v2/portfolio/orders/abc-123",
        )
        self.assertEqual(
            req.path_for_signature,
            "/trade-api/v2/portfolio/orders/abc-123",
        )
        self.assertEqual(req.headers["KALSHI-ACCESS-SIGNATURE"],"sig")

    def test_fills_lookup_query_is_not_in_presign_text(self):
        seen=[]
        req=build_kalshi_demo_fills_lookup(
            order_id="abc-123",
            key_id="demo-key",
            timestamp_ms=1700000000999,
            signer=lambda text:(seen.append(text) or "sig"),
            limit=250,
        )
        self.assertEqual(
            seen,
            ["1700000000999GET/trade-api/v2/portfolio/fills"],
        )
        self.assertEqual(
            req.path_for_signature,
            "/trade-api/v2/portfolio/fills",
        )
        self.assertIn("order_id=abc-123",req.url)
        self.assertIn("limit=250",req.url)
        self.assertNotIn("?",seen[0])

    def test_redacted_view_never_exposes_key_or_signature(self):
        req=build_kalshi_demo_order_lookup(
            order_id="abc",
            key_id="secret-key-id",
            timestamp_ms=1,
            signer=lambda _:"secret-signature",
        )
        shown=str(req.as_dict())
        self.assertNotIn("secret-key-id",shown)
        self.assertNotIn("secret-signature",shown)
        self.assertIn("<redacted>",shown)

    def test_bad_identity_timestamp_limit_or_signature_fail_closed(self):
        with self.assertRaises(ValueError):
            build_kalshi_demo_order_lookup(
                order_id="bad id",key_id="demo",timestamp_ms=1,signer=lambda _:"sig"
            )
        with self.assertRaises(ValueError):
            build_kalshi_demo_order_lookup(
                order_id="ok",key_id="",timestamp_ms=1,signer=lambda _:"sig"
            )
        with self.assertRaises(ValueError):
            build_kalshi_demo_order_lookup(
                order_id="ok",key_id="demo",timestamp_ms=0,signer=lambda _:"sig"
            )
        with self.assertRaises(ValueError):
            build_kalshi_demo_order_lookup(
                order_id="ok",key_id="demo",timestamp_ms=1,signer=lambda _:""
            )
        with self.assertRaises(ValueError):
            build_kalshi_demo_fills_lookup(
                order_id="ok",key_id="demo",timestamp_ms=1,
                signer=lambda _:"sig",limit=1001,
            )


if __name__=="__main__":
    unittest.main()
