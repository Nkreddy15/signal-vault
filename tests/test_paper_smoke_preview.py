"""No real HTTP, Keychain, broker order, local journal mutation or scheduling."""
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from signal_vault.market_data import CryptoQuote
from signal_vault.paper_smoke_preview import (
    _QUOTE_URL, _strict_latest_quote_get, main, preview_supervised_smoke,
)

NOW = datetime(2026, 9, 29, 18, 25, tzinfo=timezone.utc)
LOCAL = {
    "status": "READ_ONLY_PREFLIGHT_OK",
    "mode": "ALPACA_PAPER_ONLY",
    "operator_halted": False,
    "provider_lookup_required": False,
    "unresolved_paper_orders": 0,
    "paper_order_post_enabled": False,
    "authenticated_provider_read_performed": False,
    "live_trading_available": False,
    "sqlite_wal": True,
}
SNAPSHOT = {
    "source": "LOCAL_SQLITE_LEDGER_NOT_LIVE_MARKET_DATA",
    "mode": "ALPACA_PAPER_ONLY",
    "operator_halted": False,
    "logical": {
        "cash_usd": "100", "btc_qty": "0", "reserved_usd": "0",
        "unreserved_cash_usd": "100",
    },
    "paper_orders": {"count": 0, "unresolved": 0},
}
ACCOUNT = {
    "equity": "100000", "status": "ACTIVE", "trading_blocked": False,
    "non_marginable_buying_power": "100000",
}
ASSET = {
    "symbol": "BTC/USD", "class": "crypto", "status": "active",
    "tradable": True, "fractionable": True,
    "min_order_size": "0.00015", "min_trade_increment": "0.00001",
    "price_increment": "1",
}


class SupervisedPaperSmokePreviewTests(unittest.TestCase):
    def setUp(self):
        self.local = dict(LOCAL)
        self.snapshot = {**SNAPSHOT,
                         "logical": dict(SNAPSHOT["logical"]),
                         "paper_orders": dict(SNAPSHOT["paper_orders"])}
        self.account = dict(ACCOUNT)
        self.asset = dict(ASSET)
        self.positions = []
        self.open_orders = []
        self.quote = CryptoQuote(
            "BTC/USD", Decimal("83990"), Decimal("84010"),
            NOW - timedelta(seconds=10))
        self.key_reads = 0
        self.provider_paths = []
        self.quote_reads = 0

    def keys(self):
        self.key_reads += 1
        return SimpleNamespace(
            key_id="SENTINEL_PAPER_KEY", secret_key="SENTINEL_PAPER_SECRET")

    def paper(self, key, secret):
        self.assertEqual((key, secret),
                         ("SENTINEL_PAPER_KEY", "SENTINEL_PAPER_SECRET"))
        test = self
        class ReadOnlyPaper:
            def get_account(self):
                test.provider_paths.append("/v2/account")
                return test.account
            def get_btc_asset(self):
                test.provider_paths.append("/v2/assets/BTC%2FUSD")
                return test.asset
            def get_positions(self):
                test.provider_paths.append("/v2/positions")
                return test.positions
            def get_open_orders(self):
                test.provider_paths.append("/v2/orders?status=open")
                return test.open_orders
        return ReadOnlyPaper()

    def quote_factory(self, key, secret):
        self.assertEqual((key, secret),
                         ("SENTINEL_PAPER_KEY", "SENTINEL_PAPER_SECRET"))
        test = self
        class Quotes:
            def latest_btc_usd(self, *, as_of, max_age_seconds, max_spread_bps):
                test.quote_reads += 1
                test.assertEqual(as_of, NOW)
                test.assertEqual(max_age_seconds, 90)
                test.assertEqual(max_spread_bps, Decimal("50"))
                return test.quote
        return Quotes()

    def check(self):
        with patch("signal_vault.paper_smoke_preview.build_opener",
                   side_effect=AssertionError("real quote HTTP forbidden in offline test")), (
             patch("signal_vault.alpaca_paper.build_opener",
                   side_effect=AssertionError("real paper HTTP forbidden in offline test"))):
            return preview_supervised_smoke(
                db="FAKE_ONLY",
                now=NOW,
                local_reader=lambda _: self.local,
                snapshot_reader=lambda _: self.snapshot,
                credential_loader=self.keys,
                paper_factory=self.paper,
                quote_factory=self.quote_factory,
            )

    def assert_no_provider_reads(self):
        self.assertEqual(self.provider_paths, [])
        self.assertEqual(self.quote_reads, 0)
        self.assertEqual(self.key_reads, 0)

    def test_success_is_ephemeral_preview_not_broker_order(self):
        r = self.check()
        self.assertEqual(r["status"], "BASIC_SMOKE_PREVIEW_PASSED_NO_ORDER")
        self.assertEqual(self.provider_paths, [
            "/v2/account", "/v2/assets/BTC%2FUSD",
            "/v2/positions", "/v2/orders?status=open",
        ])
        self.assertEqual((self.key_reads, self.quote_reads), (1, 1))
        self.assertEqual(r["reference_ask_usd"], "84010")
        self.assertEqual(r["hypothetical_market_buy_notional_usd"], "15.00")
        self.assertEqual(r["provider_minimum_usd_at_reference_ask"], "12.60150")
        self.assertFalse(r["draft_created"])
        self.assertFalse(r["order_id_created"])
        self.assertFalse(r["local_journal_modified"])
        self.assertFalse(r["automatic_collector_modified"])
        self.assertFalse(r["paper_order_post_attempted"])
        self.assertEqual(r["broker_order_submission"], "DISABLED")
        self.assertEqual(r["live_trading"], "UNAVAILABLE")
        self.assertTrue(r["requires_separate_supervised_order_authorization"])
        serialized = json.dumps(r)
        self.assertNotIn("SENTINEL_PAPER_KEY", serialized)
        self.assertNotIn("SENTINEL_PAPER_SECRET", serialized)
        self.assertNotIn("100000", serialized)

    def test_halted_or_unresolved_local_blocks_before_keychain(self):
        self.local["operator_halted"] = True
        self.assertEqual(self.check()["reason_code"],
                         "LOCAL_LEDGER_NOT_EMPTY_CLEAN_INITIAL_100_USD")
        self.assert_no_provider_reads()
        self.local = {**LOCAL, "unresolved_paper_orders": 1,
                      "provider_lookup_required": True}
        self.assertEqual(self.check()["status"], "BLOCKED")
        self.assert_no_provider_reads()

    def test_local_cash_position_or_existing_draft_blocks(self):
        self.snapshot["logical"]["cash_usd"] = "85"
        self.assertEqual(self.check()["status"], "BLOCKED")
        self.assert_no_provider_reads()
        self.snapshot["logical"] = dict(SNAPSHOT["logical"])
        self.snapshot["logical"]["reserved_usd"] = "15"
        self.assertEqual(self.check()["status"], "BLOCKED")
        self.assert_no_provider_reads()
        self.snapshot["logical"] = dict(SNAPSHOT["logical"])
        self.snapshot["paper_orders"]["count"] = 1
        self.assertEqual(self.check()["status"], "BLOCKED")
        self.assert_no_provider_reads()

    def test_existing_provider_order_or_position_blocks_before_quote(self):
        self.positions = [{"symbol": "BTCUSD", "qty": "0.01"}]
        r = self.check()
        self.assertEqual(r["reason_code"], "PROVIDER_ACCOUNT_NOT_EMPTY")
        self.assertEqual(self.quote_reads, 0)
        self.positions = []
        self.open_orders = [{"id": "someone-elses-order"}]
        self.assertEqual(self.check()["status"], "BLOCKED")
        self.assertEqual(self.quote_reads, 0)

    def test_paper_account_status_and_power_are_required(self):
        self.account["non_marginable_buying_power"] = "14.99"
        self.assertEqual(self.check()["reason_code"],
                         "PAPER_ACCOUNT_BLOCKED_OR_INSUFFICIENT_BUYING_POWER")
        self.assertEqual(self.quote_reads, 0)
        self.account["non_marginable_buying_power"] = "100000"
        self.account["trading_blocked"] = True
        self.assertEqual(self.check()["status"], "BLOCKED")
        self.assertEqual(self.quote_reads, 0)

    def test_dynamic_venue_minimum_not_silently_bypassed(self):
        self.asset["min_order_size"] = "0.00020"  # > $15 at the fake ask
        r = self.check()
        self.assertEqual(r["reason_code"], "QUOTE_OR_DYNAMIC_VENUE_MINIMUM_FAILED")
        self.assertEqual(r["failure_class"], "ValueError")
        self.assertFalse(r["draft_created"])
        self.assertFalse(r["order_id_created"])

    def test_stale_crossed_future_or_wide_spread_quote_blocks(self):
        cases = (
            CryptoQuote("BTC/USD", Decimal("83990"), Decimal("84010"),
                        NOW - timedelta(seconds=91)),
            CryptoQuote("BTC/USD", Decimal("84011"), Decimal("84010"),
                        NOW - timedelta(seconds=1)),
            CryptoQuote("BTC/USD", Decimal("80000"), Decimal("84010"),
                        NOW - timedelta(seconds=1)),
            CryptoQuote("BTC/USD", Decimal("83990"), Decimal("84010"),
                        NOW + timedelta(seconds=3)),
        )
        for quote in cases:
            with self.subTest(quote=quote):
                self.quote = quote
                self.assertEqual(self.check()["reason_code"],
                                 "QUOTE_OR_DYNAMIC_VENUE_MINIMUM_FAILED")

    def test_bad_keychain_or_provider_errors_do_not_leak_exception_messages(self):
        def fail_keys():
            raise RuntimeError("SENTINEL_UNSAFE_KEYCHAIN_DETAIL")
        r = preview_supervised_smoke(
            now=NOW, local_reader=lambda _: LOCAL,
            snapshot_reader=lambda _: SNAPSHOT,
            credential_loader=fail_keys, paper_factory=self.paper,
            quote_factory=self.quote_factory)
        self.assertEqual(r["reason_code"], "LOCAL_PAPER_KEYCHAIN_UNAVAILABLE")
        self.assertEqual(r["failure_class"], "RuntimeError")
        self.assertNotIn("SENTINEL_UNSAFE_KEYCHAIN_DETAIL", json.dumps(r))
        self.assertEqual(self.provider_paths, [])
        self.assertEqual(self.quote_reads, 0)

    def test_missing_real_db_does_not_create_db_or_access_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "absent.sqlite3"
            r = preview_supervised_smoke(db=db, now=NOW,
                                         credential_loader=self.keys,
                                         paper_factory=self.paper,
                                         quote_factory=self.quote_factory)
            self.assertEqual(r["reason_code"], "LOCAL_LEDGER_PREFLIGHT_UNAVAILABLE")
            self.assertFalse(db.exists())
            self.assert_no_provider_reads()

    def test_readonly_quote_url_is_exact_and_rejects_unsafe_redirect_target(self):
        self.assertEqual(
            _QUOTE_URL,
            "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD")
        with patch("signal_vault.paper_smoke_preview.build_opener",
                   side_effect=AssertionError("must not connect")):
            with self.assertRaisesRegex(ValueError, "allowlist"):
                _strict_latest_quote_get("https://evil.invalid/quotes", "k", "s")
            with self.assertRaisesRegex(ValueError, "allowlist"):
                _strict_latest_quote_get(_QUOTE_URL + "&redirect=evil", "k", "s")


if __name__ == "__main__":
    unittest.main()
