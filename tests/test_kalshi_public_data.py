import unittest
from urllib.parse import urlsplit

from signal_vault.kalshi_public_data import (
    public_collection_request,
    public_market_request,
    safety_snapshot,
)


class KalshiPublicDataFoundationTests(unittest.TestCase):
    def test_demo_and_production_market_gets_are_strict(self):
        demo = public_market_request("TEST-MARKET", environment="demo")
        prod = public_market_request("TEST-MARKET", environment="production")
        self.assertEqual(demo.method, "GET")
        self.assertEqual(urlsplit(demo.url).hostname, "demo-api.kalshi.co")
        self.assertEqual(urlsplit(prod.url).hostname, "api.elections.kalshi.com")
        self.assertFalse(demo.credentials_required)
        self.assertEqual(demo.order_submission, "DISABLED")

    def test_collection_query_is_encoded_and_allowlisted(self):
        req = public_collection_request(
            "markets", environment="demo", params={"status": "open", "limit": 50}
        )
        self.assertIn("/trade-api/v2/markets?", req.url)
        self.assertIn("status=open", req.url)
        self.assertIn("limit=50", req.url)

    def test_unknown_collection_environment_and_bad_ticker_fail_closed(self):
        with self.assertRaises(ValueError):
            public_collection_request("portfolio")
        with self.assertRaises(ValueError):
            public_collection_request("markets", environment="live")
        with self.assertRaises(ValueError):
            public_market_request("BAD TICKER")

    def test_no_order_or_signing_capability_exists(self):
        state = safety_snapshot()
        self.assertEqual(state["allowed_http_methods"], ["GET"])
        self.assertEqual(state["request_signing"], "NOT_IMPLEMENTED")
        self.assertEqual(state["paper_order_submission"], "DISABLED")
        self.assertEqual(state["live_order_submission"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
