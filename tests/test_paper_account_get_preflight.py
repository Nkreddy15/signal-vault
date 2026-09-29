"""Offline-only tests: injected fixed-path GET fake, never a real Alpaca request."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from signal_vault.alpaca_paper import PaperAlpacaReadClient
from signal_vault.paper_account_get_preflight import inspect_account_get_only


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
ASSET = {
    "symbol": "BTC/USD", "class": "crypto", "status": "active",
    "tradable": True, "fractionable": True,
    "min_order_size": "0.00015", "min_trade_increment": "0.00001",
    "price_increment": "1",
}
ACCOUNT = {
    "equity": "100000", "status": "ACTIVE", "trading_blocked": False,
    "non_marginable_buying_power": "100000",
}
_ALLOWED_GET_PATHS = {
    "/v2/account", "/v2/assets/BTC%2FUSD", "/v2/positions", "/v2/orders?status=open",
}


class GetOnlyPaperPreflightTests(unittest.TestCase):
    def setUp(self):
        self.local = dict(LOCAL)
        self.account = dict(ACCOUNT)
        self.asset = dict(ASSET)
        self.positions = []
        self.orders = []
        self.paths = []
        self.credential_calls = 0

    def keychain(self):
        self.credential_calls += 1
        return SimpleNamespace(
            key_id="SENTINEL_KEY_SHOULD_NEVER_APPEAR",
            secret_key="SENTINEL_SECRET_SHOULD_NEVER_APPEAR")

    def fixed_get(self, path, key, secret):
        self.assertEqual(key, "SENTINEL_KEY_SHOULD_NEVER_APPEAR")
        self.assertEqual(secret, "SENTINEL_SECRET_SHOULD_NEVER_APPEAR")
        self.assertIn(path, _ALLOWED_GET_PATHS)
        self.paths.append(path)
        return {
            "/v2/account": self.account,
            "/v2/assets/BTC%2FUSD": self.asset,
            "/v2/positions": self.positions,
            "/v2/orders?status=open": self.orders,
        }[path]

    def check(self):
        return inspect_account_get_only(
            db="an-existing-journal-not-opened-in-fake-test",
            local_inspector=lambda _: self.local,
            credential_loader=self.keychain,
            client_factory=lambda key, secret: PaperAlpacaReadClient(
                key, secret, transport=self.fixed_get),
        )

    def test_clean_local_and_four_fixed_provider_gets_only(self):
        report = self.check()
        self.assertEqual(report["status"], "BASIC_PAPER_ACCOUNT_GET_CHECK_PASSED")
        self.assertEqual(self.paths, [
            "/v2/account", "/v2/assets/BTC%2FUSD",
            "/v2/positions", "/v2/orders?status=open"])
        self.assertEqual(self.credential_calls, 1)
        self.assertTrue(report["local_ledger_checked"])
        self.assertTrue(report["paper_account_get_attempted"])
        self.assertEqual(report["broker_order_submission"], "DISABLED")
        self.assertEqual(report["automatic_paper_trading"], "DISABLED")
        self.assertEqual(report["live_trading"], "UNAVAILABLE")
        output = json.dumps(report)
        self.assertNotIn("SENTINEL_KEY_SHOULD_NEVER_APPEAR", output)
        self.assertNotIn("SENTINEL_SECRET_SHOULD_NEVER_APPEAR", output)
        self.assertNotIn("100000", output)  # provider account balances never printed

    def test_local_halt_prevents_keychain_and_network(self):
        self.local["operator_halted"] = True
        r = self.check()
        self.assertEqual(r["reason_codes"], ["LOCAL_OPERATOR_HALTED_OR_UNKNOWN"])
        self.assertEqual(self.credential_calls, 0)
        self.assertEqual(self.paths, [])

    def test_pending_unknown_prevents_keychain_and_network(self):
        self.local["provider_lookup_required"] = True
        self.local["unresolved_paper_orders"] = 1
        r = self.check()
        self.assertEqual(r["reason_codes"], ["LOCAL_ORDER_RECONCILIATION_REQUIRED"])
        self.assertEqual(self.paths, [])
        self.assertEqual(self.credential_calls, 0)

    def test_local_preflight_bad_or_raises_cannot_leak(self):
        self.local["paper_order_post_enabled"] = True
        self.assertEqual(self.check()["reason_codes"],
                         ["INVALID_OR_UNSAFE_LOCAL_PAPER_PREFLIGHT"])
        self.assertEqual(self.credential_calls, 0)
        def fail(_):
            raise RuntimeError("SENTINEL_LOCAL_PATH_SECRET")
        r = inspect_account_get_only(
            local_inspector=fail, credential_loader=self.keychain)
        self.assertEqual(r["error_class"], "RuntimeError")
        self.assertNotIn("SENTINEL_LOCAL_PATH_SECRET", json.dumps(r))
        self.assertEqual(self.credential_calls, 0)

    def test_provider_existing_orders_and_positions_block(self):
        self.orders = [{"client_order_id": "other-test"}]
        self.positions = [{"symbol": "BTCUSD", "qty": "1"}]
        r = self.check()
        self.assertEqual(r["status"], "PAPER_ACCOUNT_REQUIRES_REVIEW")
        self.assertEqual(r["reason_codes"], [
            "EXISTING_PROVIDER_OPEN_ORDERS_NEED_REVIEW",
            "EXISTING_PROVIDER_POSITIONS_NEED_REVIEW"])
        self.assertEqual(self.paths, [
            "/v2/account", "/v2/assets/BTC%2FUSD",
            "/v2/positions", "/v2/orders?status=open"])

    def test_provider_blocked_account_is_reported_as_fixed_code(self):
        self.account["trading_blocked"] = True
        r = self.check()
        self.assertEqual(r["status"], "PAPER_ACCOUNT_REQUIRES_REVIEW")
        self.assertEqual(r["reason_codes"],
                         ["TRADING_STATUS_NOT_CONFIRMED_UNBLOCKED"])

    def test_invalid_asset_fails_closed_without_provider_payload_leak(self):
        self.asset["symbol"] = "OTHER_SECRET_SYMBOL"
        r = self.check()
        self.assertEqual(r["status"], "BLOCKED")
        self.assertEqual(r["reason_codes"],
                         ["PAPER_READ_ONLY_PROVIDER_PREFLIGHT_FAILED"])
        self.assertEqual(r["error_class"], "ValueError")
        self.assertNotIn("OTHER_SECRET_SYMBOL", json.dumps(r))

    def test_failed_keychain_prints_no_secret_and_issues_no_get(self):
        def fail():
            raise RuntimeError("SENTINEL_KEYCHAIN_SECRET")
        r = inspect_account_get_only(
            local_inspector=lambda _: LOCAL, credential_loader=fail,
            client_factory=lambda *_: self.fail("provider must not be created"))
        self.assertEqual(r["reason_codes"], ["PAPER_KEYCHAIN_ACCESS_BLOCKED"])
        self.assertFalse(r["paper_account_get_attempted"])
        self.assertNotIn("SENTINEL_KEYCHAIN_SECRET", json.dumps(r))

    def test_missing_real_local_db_is_not_created_and_keychain_not_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "missing.sqlite3"
            r = inspect_account_get_only(db=db, credential_loader=self.keychain,
                                         client_factory=lambda *_: self.fail("network"))
            self.assertEqual(r["reason_codes"],
                             ["LOCAL_PAPER_LEDGER_MISSING_OR_INVALID"])
            self.assertFalse(db.exists())
            self.assertEqual(self.credential_calls, 0)


if __name__ == "__main__":
    unittest.main()
