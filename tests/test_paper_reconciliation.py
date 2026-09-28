import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.alpaca_paper import PaperAlpacaReadClient, build_non_executable_draft
from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.paper_executor import PaperOnceExecutor
from signal_vault.paper_order_state import Stage
from signal_vault.paper_reconciliation import (audit_terminal_paper_order, release_verified_terminal,
                                                release_verified_zero_fill)
from signal_vault.paper_store import PersistentPaperOrderStore

NOW = datetime(2026, 9, 28, 23, 0, tzinfo=timezone.utc)
ORDER = "12345678-1234-1234-1234-123456789abc"
SELL_ORDER = "87654321-4321-4321-4321-cba987654321"


def draft(store, order_id="reconcile-1"):
    i = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"), order_id, "sig-r", NOW)
    p = PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))
    d = build_non_executable_draft(i, p, checked_at=NOW, reference_price=Decimal("65000"))
    store.journal.record(i, p, checked_at=NOW, reference_price=Decimal("65000"))
    return d


def terminal_response(d, status="filled", qty="0.00020", price="65000"):
    return {"id": ORDER, "client_order_id": d.client_order_id, "status": status,
            "filled_qty": qty, "filled_avg_price": price if Decimal(qty) else None}


def client_for(d, *, status="filled", qty="0.00020", price="65000", position_qty="0.0001995", fees=True):
    def transport(path, *_):
        if path.startswith("/v2/orders:by_client_order_id"):
            return terminal_response(d, status=status, qty=qty, price=price)
        if path.startswith("/v2/account/activities/FILL"):
            if Decimal(qty) == 0: return []
            return [{"activity_type": "FILL", "type": "fill", "id": "act::1",
                     "order_id": ORDER, "symbol": "BTCUSD", "side": "buy",
                     "qty": qty, "price": price}]
        if path.startswith("/v2/account/activities/CFEE"):
            if Decimal(qty) == 0 or not fees: return []
            return [{"id":"fee::1", "activity_type":"CFEE", "order_id":ORDER,
                     "symbol":"BTCUSD", "qty":"-0.0000005", "price":price}]
        if path.startswith("/v2/account/activities/FEE"):
            return []
        if path == "/v2/account":
            return {"equity":"100000", "status":"ACTIVE", "trading_blocked":False,
                    "non_marginable_buying_power":"99985"}
        if path == "/v2/positions":
            return [] if Decimal(position_qty) == 0 else [{"symbol":"BTCUSD", "qty":position_qty}]
        raise AssertionError(path)
    return PaperAlpacaReadClient("p", "s", transport=transport)


class ReconciliationAuditTests(unittest.TestCase):
    def test_filled_buy_with_fee_activity_can_be_atomically_accounted_and_released(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = draft(store)
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: terminal_response(d))
            self.assertEqual(executor.submit_once(d, at=NOW).stage, Stage.BROKER_TERMINAL_UNRECONCILED)
            audit = audit_terminal_paper_order(store=store, reader=client_for(d), client_order_id=d.client_order_id)
            self.assertTrue(audit.order_verified and audit.fills_verified and audit.position_verified)
            self.assertTrue(audit.fees_final and audit.ready_to_release)
            release_verified_terminal(store=store, audit=audit, at=NOW)
            self.assertFalse(store.has_unresolved_provider_order())
            account = store.logical_account()
            self.assertEqual(account["cash_usd"], Decimal("87.00000"))
            self.assertEqual(account["btc_qty"], Decimal("0.0001995"))
            self.assertEqual(account["btc_cost_basis_usd"], Decimal("13.00000"))
            self.assertEqual(account["fees_usd_equiv"], Decimal("0.0325000"))


    def test_filled_buy_without_posted_fee_is_released_with_inferred_pending_fee(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = draft(store)
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: terminal_response(d))
            executor.submit_once(d, at=NOW)
            audit = audit_terminal_paper_order(store=store, reader=client_for(d, fees=False),
                                               client_order_id=d.client_order_id)
            self.assertFalse(audit.fees_final)
            self.assertTrue(audit.fee_pending)
            self.assertTrue(audit.ready_to_release)
            self.assertEqual(audit.inferred_btc_fee_qty, Decimal("0.0000005"))
            release_verified_terminal(store=store, audit=audit, at=NOW)
            self.assertFalse(store.has_unresolved_provider_order())
            self.assertEqual(store.pending_fee_order_ids(), (d.client_order_id,))
            # Later CFEE finalizes the provisional USD valuation without touching BTC inventory.
            final = client_for(d, fees=True).get_fee_activities(ORDER)
            from signal_vault.paper_audit import audit_crypto_fee_activities
            fee = audit_crypto_fee_activities(ORDER, final)
            store.settle_pending_buy_fee(d.client_order_id, at=NOW,
                                         final_fee_usd_equiv=fee.fee_usd_equivalent,
                                         final_btc_fee_qty=fee.btc_fee_qty,
                                         final_usd_fee_amount=fee.usd_fee_amount)
            self.assertEqual(store.pending_fee_order_ids(), ())

    def test_zero_fill_canceled_order_can_be_released_after_independent_get_checks(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = draft(store)
            response = terminal_response(d, status="canceled", qty="0", price="0")
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: response)
            executor.submit_once(d, at=NOW)
            audit = audit_terminal_paper_order(store=store,
                reader=client_for(d, status="canceled", qty="0", price="0", position_qty="0"),
                client_order_id=d.client_order_id)
            self.assertTrue(audit.ready_to_release)
            release_verified_zero_fill(store=store, audit=audit, at=NOW)
            self.assertFalse(store.has_unresolved_provider_order())
            self.assertEqual(store.get(d.client_order_id).stage, Stage.RECONCILED)

    def test_position_mismatch_halts_reconciliation(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = draft(store)
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: terminal_response(d))
            executor.submit_once(d, at=NOW)
            with self.assertRaisesRegex(ValueError, "position"):
                audit_terminal_paper_order(store=store, reader=client_for(d, position_qty="0"),
                                           client_order_id=d.client_order_id)

class LogicalPortfolioAccountingTests(unittest.TestCase):
    def _buy_then_reconcile(self, store):
        d = draft(store, order_id="buy-cycle")
        executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                     transport=lambda *_: terminal_response(d))
        executor.submit_once(d, at=NOW)
        audit = audit_terminal_paper_order(store=store, reader=client_for(d),
                                           client_order_id=d.client_order_id)
        release_verified_terminal(store=store, audit=audit, at=NOW)
        return d

    def test_mark_to_market_uses_logical_100_not_provider_default_balance(self):
        with PersistentPaperOrderStore(":memory:") as store:
            self._buy_then_reconcile(store)
            snap = store.mark_portfolio(mark_price=Decimal("70000"), at=NOW)
            self.assertEqual(snap.cash_usd, Decimal("87.00000"))
            self.assertEqual(snap.equity_usd, Decimal("100.9650000"))
            self.assertEqual(snap.peak_equity_usd, Decimal("100.9650000"))
            lower = store.mark_portfolio(mark_price=Decimal("60000"), at=NOW)
            self.assertEqual(lower.equity_usd, Decimal("98.9700000"))
            self.assertEqual(lower.peak_equity_usd, Decimal("100.9650000"))
            self.assertEqual(lower.session_start_equity_usd, Decimal("100"))

    def test_full_sell_realizes_profit_and_usd_fee_atomically(self):
        with PersistentPaperOrderStore(":memory:") as store:
            self._buy_then_reconcile(store)
            qty = Decimal("0.0001995")
            sell_price = Decimal("70000")
            notional = qty * sell_price
            i = TradeIntent("crypto", "alpaca", "BTC/USD", Side.SELL, notional,
                            "sell-cycle", "sig-sell", NOW)
            p = PortfolioSnapshot(Decimal("100"), Decimal("87"), Decimal("100"), Decimal("100"),
                                  long_positions_usd={"BTC/USD": notional})
            d = build_non_executable_draft(i, p, checked_at=NOW, reference_price=sell_price,
                                           full_sell_quantity=qty)
            store.journal.record(i, p, checked_at=NOW, reference_price=sell_price,
                                 full_sell_quantity=qty)
            def post(*_):
                return {"id": SELL_ORDER, "client_order_id": d.client_order_id, "status":"filled",
                        "filled_qty":str(qty), "filled_avg_price":str(sell_price)}
            PaperOnceExecutor(paper_key="p", paper_secret="s", store=store, transport=post).submit_once(d, at=NOW)
            def transport(path, *_):
                if path.startswith("/v2/orders:by_client_order_id"): return post()
                if path.startswith("/v2/account/activities/FILL"):
                    return [{"activity_type":"FILL","type":"fill","id":"sellfill::1",
                             "order_id":SELL_ORDER,"symbol":"BTCUSD","side":"sell",
                             "qty":str(qty),"price":str(sell_price)}]
                if path.startswith("/v2/account/activities/CFEE"): return []
                if path.startswith("/v2/account/activities/FEE"):
                    return [{"id":"sellfee::1","activity_type":"FEE","order_id":SELL_ORDER,
                             "symbol":"BTCUSD","net_amount":"-0.03"}]
                if path == "/v2/account":
                    return {"equity":"100000","status":"ACTIVE","trading_blocked":False,
                            "non_marginable_buying_power":"100000"}
                if path == "/v2/positions": return []
                raise AssertionError(path)
            audit = audit_terminal_paper_order(store=store,
                reader=PaperAlpacaReadClient("p","s",transport=transport),
                client_order_id=d.client_order_id)
            self.assertTrue(audit.ready_to_release)
            release_verified_terminal(store=store, audit=audit, at=NOW)
            account = store.logical_account()
            self.assertEqual(account["btc_qty"], Decimal("0"))
            self.assertEqual(account["cash_usd"], Decimal("100.9350000"))
            self.assertEqual(account["realized_pnl_usd"], Decimal("0.9350000"))
            self.assertEqual(account["fees_usd_equiv"], Decimal("0.0625000"))

class DeferredFeeSettlementTests(unittest.TestCase):
    def test_pending_buy_fee_rejects_provider_quantity_rewrite(self):
        from signal_vault.paper_audit import audit_crypto_fee_activities
        with PersistentPaperOrderStore(":memory:") as store:
            d = draft(store, order_id="deferred-fee")
            PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                              transport=lambda *_: terminal_response(d)).submit_once(d, at=NOW)
            audit = audit_terminal_paper_order(store=store, reader=client_for(d, fees=False),
                                               client_order_id=d.client_order_id)
            release_verified_terminal(store=store, audit=audit, at=NOW)
            bad = audit_crypto_fee_activities(ORDER, [{
                "id":"fee-bad","activity_type":"CFEE","order_id":ORDER,
                "symbol":"BTCUSD","qty":"-0.0000004","price":"65000"}])
            with self.assertRaisesRegex(ValueError, "differs"):
                store.settle_pending_buy_fee(d.client_order_id, at=NOW,
                    final_fee_usd_equiv=bad.fee_usd_equivalent,
                    final_btc_fee_qty=bad.btc_fee_qty,
                    final_usd_fee_amount=bad.usd_fee_amount)
            self.assertEqual(store.pending_fee_order_ids(), (d.client_order_id,))
