import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.alpaca_paper import PaperAlpacaReadClient, PAPER_ROOT
from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_order_state import Stage
from signal_vault.paper_executor import PaperOnceExecutor, _check_draft_payload, parse_paper_observation

NOW = datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc)


def draft(book, num=1):
    intent = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                         f"paper-{num}", f"sig-{num}", NOW)
    snap = PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))
    return book.journal.record(intent, snap, checked_at=NOW, reference_price=Decimal("65000"))


def accepted(d):
    return {"id": "provider-1", "client_order_id": d.client_order_id,
            "status": "accepted", "filled_qty": "0", "filled_avg_price": None}


class PaperOrderIntegrationTests(unittest.TestCase):
    def test_valid_paper_response_records_broker_accepted_not_fill(self):
        calls = []
        with PersistentPaperOrderStore(":memory:") as book:
            d = draft(book)
            def fake(payload, key, secret):
                calls.append(dict(payload))
                return accepted(d)
            executor = PaperOnceExecutor(paper_key="mock-paper", paper_secret="mock-secret",
                                         store=book, transport=fake)
            result = executor.submit_once(d, at=NOW)
            self.assertEqual(result.stage, Stage.BROKER_ACCEPTED)
            self.assertTrue(result.state.blocks_new_execution)
            self.assertEqual(len(calls), 1)
            with self.assertRaises(ValueError):
                executor.submit_once(d, at=NOW)
            self.assertEqual(len(calls), 1)  # impossible to POST twice using same id

    def test_timeout_is_ambiguous_no_retry_or_release(self):
        calls = []
        with PersistentPaperOrderStore(":memory:") as book:
            d = draft(book)
            def timeout(payload, key, secret):
                calls.append(1)
                raise TimeoutError("mock paper transport failure")
            executor = PaperOnceExecutor(paper_key="mock-paper", paper_secret="mock-secret",
                                         store=book, transport=timeout)
            result = executor.submit_once(d, at=NOW)
            self.assertEqual(result.stage, Stage.UNKNOWN_RESULT)
            self.assertEqual(book.journal.total_reserved_usd(), Decimal("15"))
            no_order = PaperAlpacaReadClient("mock-paper", "mock-secret", transport=lambda *_: {"found": False})
            self.assertEqual(executor.lookup_unknown_once(d.client_order_id, at=NOW, reader=no_order).stage,
                             Stage.UNKNOWN_RESULT)
            with self.assertRaises(ValueError):
                executor.submit_once(d, at=NOW)
            self.assertEqual(len(calls), 1)
            lookup = PaperAlpacaReadClient("mock-paper", "mock-secret",
                                          transport=lambda *_: accepted(d))
            recovered = executor.lookup_unknown_once(d.client_order_id, at=NOW, reader=lookup)
            self.assertEqual(recovered.stage, Stage.BROKER_ACCEPTED)
            self.assertEqual(len(calls), 1)

    def test_malformed_post_response_fails_unknown_not_fake_fill(self):
        with PersistentPaperOrderStore(":memory:") as book:
            d = draft(book)
            bad = PaperOnceExecutor(paper_key="mock-paper", paper_secret="mock-secret", store=book,
                                    transport=lambda *_: {"id": "provider-1", "status": "filled"})
            self.assertEqual(bad.submit_once(d, at=NOW).stage, Stage.UNKNOWN_RESULT)
            self.assertTrue(book.has_unresolved_provider_order())

    def test_invalid_order_cannot_get_to_transport(self):
        count = []
        with PersistentPaperOrderStore(":memory:") as book:
            d = draft(book)
            executor = PaperOnceExecutor(paper_key="mock-paper", paper_secret="mock-secret", store=book,
                                         transport=lambda *_: count.append(1))
            from signal_vault.alpaca_paper import PaperOrderDraft
            altered = PaperOrderDraft(d.client_order_id, {**d.payload, "notional": "100"})
            with self.assertRaises(ValueError):
                executor.submit_once(altered, at=NOW)
            self.assertFalse(count)

    def test_paper_root_constant_and_payload_allowlist(self):
        self.assertEqual(PAPER_ROOT, "https://paper-api.alpaca.markets")
        good={"symbol":"BTC/USD","side":"buy","type":"market","time_in_force":"gtc",
              "notional":"15","client_order_id":"test1"}
        self.assertEqual(_check_draft_payload(good), good)
        for change in ({"time_in_force":"day"}, {"symbol":"ETH/USD"},
                       {"amount":"200000"}, {"notional":"5"}, {"notional":"NaN"}, {"notional":"garbage"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                _check_draft_payload({**good, **change})


if __name__ == "__main__":
    unittest.main()

class PaperStatusPollingTests(unittest.TestCase):
    def test_known_order_can_be_polled_without_new_post(self):
        with PersistentPaperOrderStore(":memory:") as book:
            d = draft(book)
            calls = []
            executor = PaperOnceExecutor(paper_key="mock-paper", paper_secret="mock-secret", store=book,
                                         transport=lambda *_: (calls.append(1) or accepted(d)))
            executor.submit_once(d, at=NOW)
            observed = PaperAlpacaReadClient("mock-paper", "mock-secret", transport=lambda *_:
                {"id":"provider-1","client_order_id":d.client_order_id,
                 "status":"filled","filled_qty":"0.00023","filled_avg_price":"65100"})
            completed = executor.poll_known_once(d.client_order_id, at=NOW, reader=observed)
            self.assertEqual(completed.stage, Stage.BROKER_TERMINAL_UNRECONCILED)
            self.assertEqual(len(calls), 1)
            self.assertEqual(book.journal.total_reserved_usd(), Decimal("15"))
