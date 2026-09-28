"""Fake-source evidence tests. These are NOT actual Alpaca confirmations."""
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from signal_vault.alpaca_paper import PaperAlpacaReadClient
from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.paper_audit import (
    PaperHoldings, parse_paper_holdings, validate_terminal_evidence,
)
from signal_vault.paper_order_state import BrokerObservation, Stage
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_executor import PaperOnceExecutor

T0 = datetime(2026, 9, 28, 22, 30, tzinfo=timezone.utc)
BASE = PaperHoldings("paper-isolated-1", Decimal("10000"), Decimal("0"), T0)
POST = PaperHoldings("paper-isolated-1", Decimal("9985.027"),
                     Decimal("0.000229425"), T0 + timedelta(seconds=2))


def intent(n="audit1"):
    return TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY,
                       Decimal("15"), n, f"sig-{n}", T0)


def snap():
    return PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))


def order(client_id, **override):
    defaults = {"id": "broker1", "client_order_id": client_id, "symbol": "BTC/USD",
                "side": "buy", "type": "market", "time_in_force": "gtc",
                "status": "filled", "notional": "15", "qty": None,
                "filled_qty": "0.00023", "filled_avg_price": "65100"}
    return {**defaults, **override}


class EvidenceTests(unittest.TestCase):
    def test_paper_only_holdings_validate_identity_and_isolation(self):
        acc = {"id": "paper-isolated-1", "status": "ACTIVE", "trading_blocked": False,
               "cash": "10000", "non_marginable_buying_power": "10000",
               "crypto_status": "ACTIVE"}
        positions = [{"symbol": "BTC/USD", "side": "long", "qty": "0.00025"}]
        observed = parse_paper_holdings(acc, positions, observed_at=T0)
        self.assertEqual(observed.btc_qty, Decimal("0.00025"))
        for change in ({"cash": "NaN"}, {"cash": "-3"}, {"id": None},
                       {"status": "INACTIVE"}, {"trading_blocked": True},
                       {"non_marginable_buying_power": "-1"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_paper_holdings({**acc, **change}, positions, observed_at=T0)
        for wrong in ([{"symbol": "ETH/USD", "side": "long", "qty": "10"}],
                      [{"symbol": "BTC/USD", "side": "short", "qty": "1"}],
                      positions + positions):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                parse_paper_holdings(acc, wrong, observed_at=T0)

    def test_terminal_buy_needs_cash_and_base_crypto_fee_evidence(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = store.journal.record(intent(), snap(), checked_at=T0, reference_price=Decimal("65000"))
            store.begin_submission(d, at=T0, baseline=BASE)
            store.observe_provider(BrokerObservation(d.client_order_id, "broker1", "filled",
                                                     Decimal("0.00023"), Decimal("65100")), at=T0)
            state = store.get(d.client_order_id)
            proof = validate_terminal_evidence(state, d.payload, BASE, POST,
                                               order(d.client_order_id), at=T0 + timedelta(seconds=3))
            self.assertEqual(len(proof), 64)
            for badpost in (
                replace(POST, cash_usd=Decimal("10000")),
                replace(POST, btc_qty=Decimal("0.00025")),
                replace(POST, account_id="other-account"),
                replace(POST, observed_at=T0),
            ):
                with self.subTest(badpost=badpost), self.assertRaises(ValueError):
                    validate_terminal_evidence(state, d.payload, BASE, badpost,
                                               order(d.client_order_id), at=T0 + timedelta(seconds=3))
            for changed in ({"side": "sell"}, {"symbol": "ETH/USD"}, {"notional": "100"},
                            {"filled_qty": "0.00021"}, {"filled_avg_price": "70000"},
                            {"id": "unrelated"}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    validate_terminal_evidence(state, d.payload, BASE, POST,
                                               order(d.client_order_id, **changed), at=T0 + timedelta(seconds=3))
            with self.assertRaises(TypeError):
                store.finish_reconciliation(d.client_order_id, at=T0,
                                            provider_cash_verified=True,
                                            provider_position_verified=True,
                                            provider_order_verified=True)
            self.assertEqual(store.journal.total_reserved_usd(), Decimal("15"))

    def test_failed_audit_never_releases_or_changes_state_even_after_restart(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "audit.sqlite"
            with PersistentPaperOrderStore(db) as store:
                d = store.journal.record(intent("audit2"), snap(), checked_at=T0,
                                         reference_price=Decimal("65000"))
                store.begin_submission(d, at=T0, baseline=BASE)
                store.observe_provider(BrokerObservation(d.client_order_id, "broker1", "filled",
                                                         Decimal("0.00023"), Decimal("65100")), at=T0)
                with self.assertRaises(ValueError):
                    store.finish_reconciliation(d.client_order_id, at=T0 + timedelta(seconds=3),
                                                post=replace(POST, cash_usd=Decimal("9999")),
                                                provider_order=order(d.client_order_id))
            with PersistentPaperOrderStore(db) as store:
                self.assertEqual(store.journal.total_reserved_usd(), Decimal("15"))
                self.assertEqual(store.get("audit2").stage, Stage.BROKER_TERMINAL_UNRECONCILED)
                closed = store.finish_reconciliation("audit2", at=T0 + timedelta(seconds=3),
                                                     post=POST, provider_order=order("audit2"))
                self.assertEqual(closed.stage, Stage.RECONCILED)
                self.assertEqual(store.journal.total_reserved_usd(), Decimal("0"))
                self.assertIn("PROVIDER_EVIDENCE_RECONCILED",
                              [x["type"] for x in store.journal.recent_events()])

    def test_zero_fill_cancellation_requires_unchanged_account_balances(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = store.journal.record(intent("audit-cancel"), snap(), checked_at=T0,
                                     reference_price=Decimal("65000"))
            store.begin_submission(d, at=T0, baseline=BASE)
            store.observe_provider(BrokerObservation(d.client_order_id, "broker1", "canceled"), at=T0)
            post = replace(BASE, observed_at=T0 + timedelta(seconds=2))
            o = order(d.client_order_id, status="canceled", filled_qty="0", filled_avg_price=None)
            self.assertEqual(store.finish_reconciliation(d.client_order_id,
                             at=T0 + timedelta(seconds=3), post=post,
                             provider_order=o).stage, Stage.RECONCILED)

    def test_preflight_mismatched_account_or_open_orders_does_not_post(self):
        def fake_transport(path, key, secret):
            if path == "/v2/assets/BTC%2FUSD":
                return {"symbol":"BTC/USD", "class":"crypto", "status":"active",
                        "tradable":True, "fractionable":True,
                        "min_order_size":"0.0001", "min_trade_increment":"0.000000001", "price_increment":"1"}
            if path == "/v2/account":
                return {"id":"paper-isolated-1", "cash":"10000", "equity":"10000",
                        "non_marginable_buying_power":"10000", "status":"ACTIVE",
                        "crypto_status":"ACTIVE", "trading_blocked":False}
            if path == "/v2/positions":
                return []
            if path == "/v2/orders?status=open":
                return [{"id":"someone-else"}]
            raise AssertionError(path)
        with PersistentPaperOrderStore(":memory:") as store:
            d = store.journal.record(intent("audit-preflight"), snap(),
                                     checked_at=T0, reference_price=Decimal("65000"))
            posts = []
            executor = PaperOnceExecutor(paper_key="my-paper", paper_secret="my-secret", store=store,
                                         transport=lambda *_: posts.append("POST"))
            wrong = PaperAlpacaReadClient("another-account", "wrong-secret", transport=fake_transport)
            with self.assertRaises(PermissionError):
                executor.submit_once(d, at=T0, reader=wrong)
            correct = PaperAlpacaReadClient("my-paper", "my-secret", transport=fake_transport)
            with self.assertRaises(PermissionError):
                executor.submit_once(d, at=T0, reader=correct)
            self.assertFalse(posts)
            self.assertFalse(store.has_unresolved_provider_order())

if __name__ == "__main__":
    unittest.main()

class PaperReadOnlyAuditorTests(unittest.TestCase):
    def test_order_and_account_three_way_evidence_with_injected_provider_reads(self):
        # All provider responses below are deterministic fakes; no HTTP is used.
        with PersistentPaperOrderStore(":memory:") as store:
            d = store.journal.record(intent("audit-reader"), snap(),
                                     checked_at=T0, reference_price=Decimal("65000"))
            store.begin_submission(d, at=T0, baseline=BASE)
            store.observe_provider(BrokerObservation(d.client_order_id, "broker1", "filled",
                                                     Decimal("0.00023"), Decimal("65100")), at=T0)
            paths = []
            def fake(path, key, secret):
                paths.append(path)
                if path == "/v2/orders?status=open":
                    return []
                if path.startswith("/v2/orders:by_client_order_id?"):
                    return order(d.client_order_id)
                if path == "/v2/account":
                    return {"id":"paper-isolated-1", "cash":"9985.027", "equity":"10000",
                            "non_marginable_buying_power":"9985.027", "status":"ACTIVE",
                            "crypto_status":"ACTIVE", "trading_blocked":False}
                if path == "/v2/positions":
                    return [{"symbol":"BTC/USD", "side":"long", "qty":"0.000229425"}]
                raise AssertionError(f"unapproved fake provider GET: {path}")
            reader = PaperAlpacaReadClient("paper-key", "paper-secret", transport=fake)
            executor = PaperOnceExecutor(paper_key="paper-key", paper_secret="paper-secret", store=store,
                                         transport=lambda *_: self.fail("must never POST during audit"))
            outcome = executor.reconcile_terminal_once(d.client_order_id,
                            at=T0 + timedelta(seconds=3), reader=reader)
            self.assertEqual(outcome.stage, Stage.RECONCILED)
            self.assertEqual(store.journal.total_reserved_usd(), Decimal("0"))
            self.assertEqual(paths, ["/v2/orders?status=open",
                f"/v2/orders:by_client_order_id?client_order_id={d.client_order_id}",
                "/v2/account", "/v2/positions"])

    def test_auditor_stays_unreconciled_on_unexpected_cash(self):
        with PersistentPaperOrderStore(":memory:") as store:
            d = store.journal.record(intent("audit-reader-bad"), snap(),
                                     checked_at=T0, reference_price=Decimal("65000"))
            store.begin_submission(d, at=T0, baseline=BASE)
            store.observe_provider(BrokerObservation(d.client_order_id, "broker1", "filled",
                                                     Decimal("0.00023"), Decimal("65100")), at=T0)
            def fake(path, *_):
                if path == "/v2/orders?status=open": return []
                if path.startswith("/v2/orders:by_client_order_id?"):
                    return order(d.client_order_id)
                if path == "/v2/account":
                    return {"id":"paper-isolated-1", "cash":"10000", "equity":"10000",
                            "non_marginable_buying_power":"10000", "status":"ACTIVE",
                            "crypto_status":"ACTIVE", "trading_blocked":False}
                if path == "/v2/positions":
                    return [{"symbol":"BTC/USD", "side":"long", "qty":"0.000229425"}]
                raise AssertionError(path)
            reader = PaperAlpacaReadClient("paper-key", "paper-secret", transport=fake)
            executor = PaperOnceExecutor(paper_key="paper-key", paper_secret="paper-secret", store=store,
                                         transport=lambda *_: self.fail("not a submission test"))
            with self.assertRaises(ValueError):
                executor.reconcile_terminal_once(d.client_order_id,
                                at=T0 + timedelta(seconds=3), reader=reader)
            self.assertEqual(store.journal.total_reserved_usd(), Decimal("15"))
            self.assertEqual(store.get(d.client_order_id).stage, Stage.BROKER_TERMINAL_UNRECONCILED)

class VirtualPaperBudgetTests(unittest.TestCase):
    def _filled_first_buy(self, store):
        d = store.journal.record(intent("budget-buy1"), snap(),
                                 checked_at=T0, reference_price=Decimal("65000"))
        store.begin_submission(d, at=T0, baseline=BASE)
        self.assertEqual(store.budget_snapshot()["virtual_cash"], "100")
        store.observe_provider(BrokerObservation(d.client_order_id, "broker1", "filled",
                                                 Decimal("0.00023"), Decimal("65100")), at=T0)
        store.finish_reconciliation(d.client_order_id, at=T0 + timedelta(seconds=3),
                                    post=POST, provider_order=order(d.client_order_id))
        return d

    def test_default_paper_account_does_not_replace_virtual_100_budget(self):
        with PersistentPaperOrderStore(":memory:") as store:
            self._filled_first_buy(store)
            b = store.budget_snapshot()
            self.assertEqual(Decimal(b["virtual_cash"]), Decimal("85.027"))
            self.assertEqual(Decimal(b["virtual_btc"]), Decimal("0.000229425"))
            self.assertEqual(b["last_provider_cash"], "9985.027")
            self.assertEqual(b["account_id"], BASE.account_id)

    def test_external_manual_trading_or_deposit_blocks_next_order(self):
        with PersistentPaperOrderStore(":memory:") as store:
            self._filled_first_buy(store)
            later = T0 + timedelta(seconds=4)
            second_intent = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY,
                             Decimal("15"), "budget-buy2", "new-evidence", later)
            d = store.journal.record(second_intent, snap(), checked_at=later,
                                     reference_price=Decimal("65100"))
            changed = replace(POST, observed_at=later, cash_usd=POST.cash_usd + Decimal("1"))
            with self.assertRaises(PermissionError):
                store.begin_submission(d, at=later, baseline=changed)
            self.assertFalse(store.has_unresolved_provider_order())
            unchanged = replace(POST, observed_at=later)
            self.assertEqual(store.begin_submission(d, at=later, baseline=unchanged).stage,
                             Stage.SUBMISSION_PENDING)

    def test_virtual_account_prevents_overallocation_from_incorrect_caller_snapshot(self):
        with PersistentPaperOrderStore(":memory:") as store:
            self._filled_first_buy(store)
            later = T0 + timedelta(seconds=4)
            d = store.journal.record(TradeIntent("crypto", "alpaca", "BTC/USD",
                             Side.BUY, Decimal("15"), "budget-over", "new-evidence", later),
                             snap(), checked_at=later, reference_price=Decimal("100000"))
            with self.assertRaisesRegex(PermissionError, "fixed \\$30 cap"):
                store.begin_submission(d, at=later, baseline=replace(POST, observed_at=later))
            self.assertEqual(store.budget_snapshot()["virtual_cash"], "85.027")

    def test_account_loss_pause_is_independent_of_caller_portfolio(self):
        with PersistentPaperOrderStore(":memory:") as store:
            self._filled_first_buy(store)
            later = T0 + timedelta(seconds=4)
            # $85.027 cash + ~ $10 BTC marked = <$97, so an allegedly fresh
            # $100 external PortfolioSnapshot cannot approve a new buy.
            d = store.journal.record(TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY,
                           Decimal("15"), "budget-loss", "new-evidence", later),
                           snap(), checked_at=later, reference_price=Decimal("40000"))
            with self.assertRaisesRegex(PermissionError, "daily equity loss"):
                store.begin_submission(d, at=later, baseline=replace(POST, observed_at=later))
            self.assertFalse(store.has_unresolved_provider_order())

class MarkToMarketRiskTests(unittest.TestCase):
    def _book_after_fill(self):
        store=PersistentPaperOrderStore(':memory:')
        d=store.journal.record(intent('mark-first'),snap(),checked_at=T0,
                               reference_price=Decimal('65000'))
        store.begin_submission(d,at=T0,baseline=BASE)
        store.observe_provider(BrokerObservation(d.client_order_id,'broker1','filled',
                                                 Decimal('0.00023'),Decimal('65100')),at=T0)
        store.finish_reconciliation(d.client_order_id,at=T0+timedelta(seconds=3),
                       post=POST,provider_order=order(d.client_order_id))
        return store

    def test_peak_equity_mark_is_persistent_and_blocks_later_peak_drawdown(self):
        with self._book_after_fill() as store:
            peak=store.mark_virtual_quote(mark_price=Decimal('100000'),
                       at=T0+timedelta(seconds=4),evidence_id='validated-market-high')
            self.assertGreater(Decimal(peak['peak_equity']),Decimal('107'))
            low=store.mark_virtual_quote(mark_price=Decimal('55000'),
                       at=T0+timedelta(seconds=5),evidence_id='validated-market-low')
            self.assertEqual(low['peak_equity'],peak['peak_equity'])
            at=T0+timedelta(seconds=6)
            d=store.journal.record(TradeIntent('crypto','alpaca','BTC/USD',Side.BUY,
                 Decimal('15'),'mark-next','evidence-mark-next',at),snap(),
                 checked_at=at,reference_price=Decimal('55000'))
            with self.assertRaisesRegex(PermissionError,'peak drawdown'):
                store.begin_submission(d,at=at,baseline=replace(POST,observed_at=at))
            self.assertEqual(store.journal.total_reserved_usd(),Decimal('15'))

    def test_same_time_conflicting_price_is_not_allowed(self):
        with self._book_after_fill() as store:
            at=T0+timedelta(seconds=4)
            x=store.mark_virtual_quote(mark_price=Decimal('65000'),at=at,evidence_id='e1')
            self.assertEqual(x,store.mark_virtual_quote(mark_price=Decimal('65000'),at=at,evidence_id='e1'))
            with self.assertRaises(PermissionError):
                store.mark_virtual_quote(mark_price=Decimal('65001'),at=at,evidence_id='e2')

    def test_utc_rollover_uses_previous_observed_equity_as_session_open(self):
        with self._book_after_fill() as store:
            older=store.risk_mark_snapshot()
            tomorrow=(T0+timedelta(days=1)).replace(hour=0,minute=0,second=3)
            new=store.mark_virtual_quote(mark_price=Decimal('50000'),at=tomorrow,
                                         evidence_id='validated-first-next-day-close')
            self.assertEqual(new['session_start_equity'],older['current_equity'])
            self.assertNotEqual(new['session_day'],older['session_day'])

class ProvenVirtualProfitTests(unittest.TestCase):
    def test_audited_mark_allows_proposal_above_initial_cap_but_forged_profits_fail(self):
        store=MarkToMarketRiskTests()._book_after_fill()
        with store:
            px=Decimal('100000')
            at=T0+timedelta(seconds=4)
            mark=store.mark_virtual_quote(mark_price=px,at=at,evidence_id='independent-market-mark')
            b=store.budget_snapshot()
            cash=Decimal(b['virtual_cash']);btc=Decimal(b['virtual_btc'])
            equity=cash+btc*px
            self.assertGreater(equity,Decimal('100'))
            proven=PortfolioSnapshot(equity,cash,Decimal(mark['peak_equity']),
              Decimal(mark['session_start_equity']),long_positions_usd={'BTC/USD':btc*px})
            i=TradeIntent('crypto','alpaca','BTC/USD',Side.SELL,btc*px,
                 'source-proven-gain','confirmed-exit-signal',at)
            draft=store.journal.record(i,proven,checked_at=at,reference_price=px,
                                       full_sell_quantity=btc)
            self.assertEqual(draft.payload['qty'],str(btc))
            forged=replace(proven,equity_usd=equity+Decimal('1'))
            with self.assertRaises(ValueError):
                store.journal.record(replace(i,client_order_id='fake-profit-gain'),forged,
                            checked_at=at,reference_price=px,full_sell_quantity=btc)
