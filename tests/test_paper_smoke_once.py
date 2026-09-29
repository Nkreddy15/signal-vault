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
BROKER_ORDER_ID = "12345678-1234-1234-1234-123456789abc"
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
        self.fee_posted = False
        self.fee_qty = "-0.00000045"

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
                filled = test.lookup_state == "filled"
                return {"id": BROKER_ORDER_ID, "client_order_id": cid,
                        "status": test.lookup_state,
                        "filled_qty": "0.00018" if filled else "0",
                        "filled_avg_price": "83000" if filled else None}
            if path == "/v2/account/activities/FILL?order_id=" + BROKER_ORDER_ID:
                return [{
                    "activity_type": "FILL", "type": "fill", "id": "synthetic-fill-1",
                    "order_id": BROKER_ORDER_ID, "symbol": "BTCUSD",
                    "side": "buy", "qty": "0.00018", "price": "83000",
                }]
            if path == "/v2/account/activities/CFEE?order_id=" + BROKER_ORDER_ID:
                if not test.fee_posted:
                    return []
                return [{
                    "id": "synthetic-fee-1", "activity_type": "CFEE",
                    "order_id": BROKER_ORDER_ID, "symbol": "BTCUSD",
                    "qty": test.fee_qty, "price": "83000",
                }]
            if path == "/v2/account/activities/FEE?order_id=" + BROKER_ORDER_ID:
                return []
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
        return {"id": BROKER_ORDER_ID, "client_order_id": payload["client_order_id"],
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

    def test_deferred_buy_fee_rechecks_original_fill_and_finalizes_without_post(self):
        initial = self.run_smoke()
        self.assertEqual(initial["provider_stage"], Stage.BROKER_ACCEPTED.value)
        self.lookup_state = "filled"
        self.positions = [{"symbol": "BTCUSD", "qty": "0.00017955"}]
        self.fee_posted = False

        def reconcile():
            with patch("signal_vault.alpaca_paper.build_opener",
                       side_effect=AssertionError("real network not allowed in fixture")):
                return reconcile_one_paper_smoke(
                    db=self.db, clock=lambda: NOW, credential_loader=self.credentials,
                    paper_factory=self.paper)

        first = reconcile()
        self.assertEqual(first["status"], "PAPER_ORDER_RECONCILED")
        self.assertEqual(first["pending_fee_audits"], 1)
        self.assertEqual(len(self.posts), 1)

        pending = reconcile()
        self.assertEqual(pending["status"], "PAPER_ORDER_RECONCILED_FEE_STILL_PENDING")
        self.assertEqual(pending["pending_fee_audits"], 1)
        self.assertEqual(pending["broker_order_submission"],
                         "DISABLED_ALWAYS_FOR_RECONCILIATION")
        with PersistentPaperOrderStore(self.db) as store:
            self.assertEqual(store.pending_fee_order_ids(), (first["client_order_id"],))
            provisional_fee = store.logical_account()["fees_usd_equiv"]

        # Provider CFEE could post after the original accepted and filled
        # transitions; its base amount MUST match position-inferred BTC fee.
        self.fee_posted = True
        final = reconcile()
        self.assertEqual(final["status"], "PAPER_ORDER_RECONCILED_FEE_FINALIZED")
        self.assertEqual(final["pending_fee_audits"], 0)
        self.assertFalse(final["actual_paper_post_possibly_attempted"])
        self.assertEqual(len(self.posts), 1)
        with PersistentPaperOrderStore(self.db) as store:
            self.assertEqual(store.pending_fee_order_ids(), ())
            self.assertEqual(store.logical_account()["fees_usd_equiv"],
                             Decimal("0.00000045") * Decimal("83000"))
            self.assertEqual(store.logical_account()["btc_qty"], Decimal("0.00017955"))
        repeated = reconcile()
        self.assertEqual(repeated["status"], "ALREADY_RECONCILED_FEES_FINAL")
        self.assertEqual(repeated["pending_fee_audits"], 0)
        self.assertEqual(len(self.posts), 1)

    def test_deferred_buy_fee_wrong_provider_amount_fails_closed_without_rewriting(self):
        self.run_smoke()
        self.lookup_state = "filled"
        self.positions = [{"symbol": "BTCUSD", "qty": "0.00017955"}]
        first = reconcile_one_paper_smoke(
            db=self.db, clock=lambda: NOW, credential_loader=self.credentials,
            paper_factory=self.paper)
        self.assertEqual(first["status"], "PAPER_ORDER_RECONCILED")
        self.assertEqual(first["pending_fee_audits"], 1)
        self.fee_posted = True
        self.fee_qty = "-0.00000040"  # conflicts with exact provider net inventory
        failed = reconcile_one_paper_smoke(
            db=self.db, clock=lambda: NOW, credential_loader=self.credentials,
            paper_factory=self.paper)
        self.assertEqual(failed["status"],
                         "RECONCILED_ORDER_FEE_AUDIT_REQUIRES_REVIEW")
        self.assertEqual(failed["reason_code"],
                         "PROVIDER_FEE_FINALIZATION_FAILED_CLOSED")
        self.assertEqual(failed["failure_class"], "ValueError")
        self.assertEqual(failed["pending_fee_audits"], 1)
        self.assertEqual(len(self.posts), 1)
        with PersistentPaperOrderStore(self.db) as store:
            self.assertEqual(store.pending_fee_order_ids(), (first["client_order_id"],))
            self.assertEqual(store.logical_account()["btc_qty"], Decimal("0.00017955"))

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
