"""Only fake broker/data transports. No real broker POST or Keychain access."""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from signal_vault.alpaca_paper import PaperAlpacaReadClient
from signal_vault.market_data import CryptoQuote
from signal_vault.paper_order_state import Stage
from signal_vault.paper_smoke_once import (
    CONSENT, execute_one_paper_smoke, main, reconcile_one_paper_smoke,
)
from signal_vault.paper_store import PersistentPaperOrderStore

NOW = datetime(2026, 9, 29, 18, 45, tzinfo=timezone.utc)
ACCOUNT = {
    "equity": "100000", "status": "ACTIVE", "trading_blocked": False,
    "non_marginable_buying_power": "100000",
}
ASSET = {
    "symbol": "BTC/USD", "class": "crypto", "status": "active",
    "tradable": True, "fractionable": True,
    "min_order_size": "0.000012", "min_trade_increment": "0.000000001",
    "price_increment": "0.01",
}


class SupervisedPaperSmokeSafetyTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.db = Path(td.name) / "paper.sqlite3"
        with PersistentPaperOrderStore(self.db):
            pass
        self.account = dict(ACCOUNT)
        self.asset = dict(ASSET)
        self.positions = []
        self.orders = []
        self.posts = []
        self.get_paths = []
        self.quote_count = 0
        self.key_count = 0
        self.quote = CryptoQuote(
            "BTC/USD", Decimal("83549"), Decimal("83569.9"),
            NOW - timedelta(seconds=8),
        )
        self.lookup_state = "accepted"
        self.lookup_missing = False

    def credentials(self):
        self.key_count += 1
        return SimpleNamespace(key_id="SENTINEL_FAKE_KEY", secret_key="SENTINEL_FAKE_SECRET")

    def paper(self, key, secret):
        self.assertEqual((key, secret), ("SENTINEL_FAKE_KEY", "SENTINEL_FAKE_SECRET"))
        test = self
        def transport(path, *_):
            test.get_paths.append(path)
            if path == "/v2/account": return test.account
            if path == "/v2/assets/BTC%2FUSD": return test.asset
            if path == "/v2/positions": return test.positions
            if path == "/v2/orders?status=open": return test.orders
            if path.startswith("/v2/orders:by_client_order_id?client_order_id="):
                if test.lookup_missing: return {"found": False}
                cid = path.split("=", 1)[1]
                return {"id": "synthetic-broker-id", "client_order_id": cid,
                        "status": test.lookup_state, "filled_qty": "0",
                        "filled_avg_price": None}
            raise AssertionError("GET outside fake fixed-paper path: " + path)
        return PaperAlpacaReadClient(key, secret, transport=transport)

    def quotes(self, key, secret):
        test = self
        class Quotes:
            def latest_btc_usd(self, **kwargs):
                test.quote_count += 1
                return test.quote
        return Quotes()

    def fake_post(self, payload, key, secret):
        self.assertEqual((key, secret), ("SENTINEL_FAKE_KEY", "SENTINEL_FAKE_SECRET"))
        self.assertEqual(payload["symbol"], "BTC/USD")
        self.assertEqual(payload["side"], "buy")
        self.assertEqual(payload["notional"], "15.00")
        self.posts.append(dict(payload))
        return {"id": "synthetic-broker-id", "client_order_id": payload["client_order_id"],
                "status": "accepted", "filled_qty": "0", "filled_avg_price": None}

    def run_smoke(self, *, approval=CONSENT, transport=None):
        # Any accidental use of a production transport instead of an injected
        # fake will fail the offline unit test immediately.
        def no_network(*_args, **_kwargs):
            self.fail("real broker/data HTTP transport must never be called")
        with patch("signal_vault.paper_executor.build_opener", side_effect=no_network), (
             patch("signal_vault.alpaca_paper.build_opener", side_effect=no_network)), (
             patch("signal_vault.paper_smoke_preview.build_opener", side_effect=no_network)):
            return execute_one_paper_smoke(
                db=self.db, approval=approval, clock=lambda: NOW,
                credential_loader=self.credentials, paper_factory=self.paper,
                quote_factory=self.quotes,
                submit_transport=transport if transport is not None else self.fake_post,
                client_id_factory=lambda: "a1b2c3d4",
            )

    def test_one_approved_paper_simulated_post_is_durable_and_not_a_fill(self):
        out = self.run_smoke()
        self.assertEqual(out["status"],
                         "ONE_PAPER_POST_ATTEMPT_RECORDED_RECONCILIATION_REQUIRED")
        self.assertEqual(out["provider_stage"], Stage.BROKER_ACCEPTED.value)
        self.assertTrue(out["actual_paper_post_possibly_attempted"])
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.key_count, 1)
        self.assertEqual(self.quote_count, 1)
        self.assertEqual(self.get_paths[:4], [
            "/v2/account", "/v2/assets/BTC%2FUSD",
            "/v2/positions", "/v2/orders?status=open"])
        self.assertFalse(out["paper_order_filled_and_reconciled"])
        self.assertFalse(out["installed_mac_collector_modified"])
        self.assertEqual(out["automatic_paper_orders"], "DISABLED")
        with PersistentPaperOrderStore(self.db) as store:
            self.assertEqual(len(store.list_states()), 1)
            self.assertEqual(store.list_states()[0].stage, Stage.BROKER_ACCEPTED)
            self.assertEqual(store.journal.total_reserved_usd(), Decimal("15"))
            self.assertEqual(store.logical_account()["cash_usd"], Decimal("100"))
        serialized = json.dumps(out)
        self.assertNotIn("SENTINEL_FAKE_KEY", serialized)
        self.assertNotIn("SENTINEL_FAKE_SECRET", serialized)
        self.assertNotIn("100000", serialized)
        again = self.run_smoke()
        self.assertEqual(again["status"], "BLOCKED")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.key_count, 1)  # second call fails BEFORE Keychain

    def test_missing_consent_refuses_before_even_db_access(self):
        self.db.unlink()
        out = self.run_smoke(approval="yes")
        self.assertEqual(out["reason_code"], "EXACT_LOCAL_CONSENT_REQUIRED")
        self.assertFalse(self.db.exists())
        self.assertEqual((self.key_count, self.quote_count, len(self.posts)), (0, 0, 0))

    def test_live_mode_environment_refused_before_any_credential(self):
        with patch.dict("os.environ", {"SIGNAL_VAULT_MODE": "live"}):
            out = self.run_smoke()
        self.assertEqual(out["reason_code"], "LIVE_MODE_ENVIRONMENT_FORBIDDEN")
        self.assertEqual((self.key_count, len(self.posts)), (0, 0))

    def test_operator_halt_or_nonempty_ledger_refuses_before_keychain(self):
        with PersistentPaperOrderStore(self.db) as store:
            store.set_operator_halt(True, reason="maintenance", at=NOW)
        out = self.run_smoke()
        self.assertEqual(out["reason_code"], "NOT_THE_EMPTY_INITIAL_100_USD_LEDGER")
        self.assertEqual(self.key_count, 0)
        with PersistentPaperOrderStore(self.db) as store:
            store.set_operator_halt(False, reason="", at=NOW)
            store.connection.execute("UPDATE logical_portfolio SET cash_usd='95' WHERE singleton=1")
        out = self.run_smoke()
        self.assertEqual(out["reason_code"], "NOT_THE_EMPTY_INITIAL_100_USD_LEDGER")
        self.assertEqual(self.key_count, 0)

    def test_provider_positions_or_insufficient_power_block_without_draft(self):
        self.positions = [{"symbol": "BTCUSD", "qty": "0.01"}]
        out = self.run_smoke()
        self.assertEqual(out["reason_code"], "CURRENT_PAPER_ACCOUNT_QUOTE_OR_RULES_FAILED")
        self.assertEqual(len(self.posts), 0)
        self.assertEqual(self.quote_count, 0)
        self.positions = []
        self.account["non_marginable_buying_power"] = "14.99"
        out = self.run_smoke()
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(len(self.posts), 0)
        with PersistentPaperOrderStore(self.db) as store:
            self.assertEqual(store.connection.execute(
                "SELECT COUNT(*) FROM drafts").fetchone()[0], 0)

    def test_bad_dynamic_minimum_or_stale_quote_blocks_before_draft(self):
        self.asset["min_order_size"] = "0.00020"
        out = self.run_smoke()
        self.assertEqual(out["reason_code"], "CURRENT_PAPER_ACCOUNT_QUOTE_OR_RULES_FAILED")
        self.assertEqual(len(self.posts), 0)
        self.asset = dict(ASSET)
        self.quote = CryptoQuote("BTC/USD", Decimal("83549"), Decimal("83569.9"),
                                 NOW - timedelta(seconds=92))
        out = self.run_smoke()
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(len(self.posts), 0)

    def test_fake_post_timeout_becomes_unknown_and_reconciliation_never_posts(self):
        attempts = []
        def timeout(payload, *_):
            attempts.append(dict(payload))
            raise TimeoutError("simulated HTTP response lost")
        out = self.run_smoke(transport=timeout)
        self.assertEqual(out["status"], "UNKNOWN_RESULT_RECONCILE_NO_RETRY")
        self.assertEqual(out["provider_stage"], Stage.UNKNOWN_RESULT.value)
        self.assertEqual(len(attempts), 1)
        with PersistentPaperOrderStore(self.db) as store:
            self.assertEqual(store.journal.total_reserved_usd(), Decimal("15"))
        self.lookup_missing = True
        pending = reconcile_one_paper_smoke(
            db=self.db, clock=lambda: NOW, credential_loader=self.credentials,
            paper_factory=self.paper)
        self.assertEqual(pending["provider_stage"], Stage.UNKNOWN_RESULT.value)
        self.assertEqual(pending["broker_order_submission"],
                         "DISABLED_ALWAYS_FOR_RECONCILIATION")
        self.assertEqual(len(attempts), 1)
        self.lookup_missing = False
        recovered = reconcile_one_paper_smoke(
            db=self.db, clock=lambda: NOW, credential_loader=self.credentials,
            paper_factory=self.paper)
        self.assertEqual(recovered["provider_stage"], Stage.BROKER_ACCEPTED.value)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(recovered["status"],
                         "PROVIDER_LOOKUP_OR_FEE_FINALIZATION_STILL_REQUIRED")

    def test_synthetic_accepted_order_can_be_polled_without_new_post(self):
        initial = self.run_smoke()
        self.assertEqual(initial["provider_stage"], "broker_accepted")
        state = reconcile_one_paper_smoke(
            db=self.db, clock=lambda: NOW, credential_loader=self.credentials,
            paper_factory=self.paper)
        self.assertEqual(state["provider_stage"], "broker_accepted")
        self.assertEqual(state["broker_order_submission"],
                         "DISABLED_ALWAYS_FOR_RECONCILIATION")
        self.assertEqual(len(self.posts), 1)

    def test_non_tty_cli_cannot_obtain_order_consent(self):
        fake_stdin = SimpleNamespace(isatty=lambda: False)
        fake_stdout = SimpleNamespace(isatty=lambda: False)
        output = io.StringIO()
        with patch("signal_vault.paper_smoke_once.sys.stdin", fake_stdin), (
             patch("signal_vault.paper_smoke_once.sys.stdout", fake_stdout)), (
             contextlib.redirect_stdout(output)):
            rc = main(["--execute", "--db", str(self.db)])
        self.assertEqual(rc, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["reason_code"], "INTERACTIVE_LOCAL_TERMINAL_REQUIRED")
        self.assertEqual(len(self.posts), 0)
        self.assertEqual(self.key_count, 0)


if __name__ == "__main__":
    unittest.main()
