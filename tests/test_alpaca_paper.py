import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.alpaca_paper import (PaperAlpacaReadClient, PAPER_ROOT,
                                        build_non_executable_draft)
from signal_vault.domain import TradeIntent, Side, PortfolioSnapshot

NOW = datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc)


def intent(**overrides):
    base = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                       "sv-paper-test-001", "signal-evidence-001", NOW)
    return replace(base, **overrides)


def portfolio(**overrides):
    base = PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))
    return replace(base, **overrides)


class PaperReadBoundaryTests(unittest.TestCase):
    def test_host_is_immutable_paper(self):
        self.assertEqual(PAPER_ROOT, "https://paper-api.alpaca.markets")
        self.assertFalse(hasattr(PaperAlpacaReadClient, "submit"))
        self.assertFalse(hasattr(PaperAlpacaReadClient, "withdraw"))

    def test_account_and_symbol_read_with_mock_transport(self):
        calls = []
        def transport(path, key, secret):
            calls.append(path)
            if path == "/v2/account":
                return {"equity": "100000"}
            if path == "/v2/assets/BTC%2FUSD":
                return {"symbol": "BTC/USD", "class": "crypto", "status": "active",
                        "tradable": True, "fractionable": True}
            return {"client_order_id": "known_1", "status": "accepted"}
        client = PaperAlpacaReadClient("PAPER_KEY", "PAPER_SECRET", transport=transport)
        self.assertEqual(client.get_account()["equity"], "100000")
        self.assertEqual(client.get_btc_asset()["symbol"], "BTC/USD")
        self.assertEqual(client.lookup_order("known_1")["status"], "accepted")
        self.assertTrue(all(path.startswith("/v2/") for path in calls))
        with self.assertRaises(ValueError):
            client.lookup_order("foo?token=steal")

    def test_rejects_untradable_or_wrong_asset(self):
        bad = PaperAlpacaReadClient("p", "s", transport=lambda *_: {"symbol": "ETH/USD", "tradable": True})
        with self.assertRaises(ValueError):
            bad.get_btc_asset()

    def test_buy_draft_validates_minimum_without_order_post(self):
        draft = build_non_executable_draft(intent(), portfolio(), checked_at=NOW,
                                          reference_price=Decimal("66000"))
        self.assertEqual(draft.payload["time_in_force"], "gtc")
        self.assertEqual(draft.payload["notional"], "15")
        self.assertIn("DRAFT ONLY", draft.note)
        with self.assertRaises((ValueError, PermissionError)):
            build_non_executable_draft(intent(notional_usd=Decimal("5")), portfolio(),
                                      checked_at=NOW, reference_price=Decimal("66000"))
        with self.assertRaises(ValueError):
            build_non_executable_draft(intent(notional_usd=Decimal("15.001")), portfolio(),
                                      checked_at=NOW, reference_price=Decimal("66000"))

    def test_sell_requires_reconciled_base_qty(self):
        p = portfolio(cash_usd=Decimal("85"), long_positions_usd={"BTC/USD": Decimal("15")})
        sell = intent(side=Side.SELL)
        with self.assertRaises(ValueError):
            build_non_executable_draft(sell, p, checked_at=NOW, reference_price=Decimal("60000"))
        draft = build_non_executable_draft(sell, p, checked_at=NOW,
                                         reference_price=Decimal("60000"),
                                         full_sell_quantity=Decimal("0.00025"))
        self.assertEqual(draft.payload["qty"], "0.00025")
        with self.assertRaises(ValueError):
            build_non_executable_draft(sell, p, checked_at=NOW,
                                     reference_price=Decimal("60000"),
                                     full_sell_quantity=Decimal("0.00000001"))


if __name__ == "__main__":
    unittest.main()

class PaperReadinessTests(unittest.TestCase):
    def test_default_large_paper_balance_does_not_change_100_logical_cap(self):
        def mock(path, key, secret):
            if path == "/v2/account":
                return {"equity": "100000", "status": "ACTIVE", "trading_blocked": False,
                        "non_marginable_buying_power": "100000"}
            if path == "/v2/assets/BTC%2FUSD":
                return {"symbol": "BTC/USD", "class": "crypto", "status": "active",
                        "tradable": True, "fractionable": True}
            return []
        client = PaperAlpacaReadClient("mock-paper", "mock-secret", transport=mock)
        result = client.readiness()
        self.assertTrue(result.ready)
        self.assertEqual(result.logical_cap_usd, Decimal("100"))

    def test_existing_positions_fail_readiness_without_canceling_anything(self):
        def mock(path, key, secret):
            if path == "/v2/account":
                return {"equity": "100000", "status": "ACTIVE", "trading_blocked": False,
                        "non_marginable_buying_power": "100000"}
            if path == "/v2/assets/BTC%2FUSD":
                return {"symbol": "BTC/USD", "class": "crypto", "status": "active",
                        "tradable": True, "fractionable": True}
            if path == "/v2/positions":
                return [{"symbol": "BTCUSD"}]
            return []
        self.assertFalse(PaperAlpacaReadClient("mock-paper", "mock-secret", transport=mock).readiness().ready)
