import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.journal import OfflineDraftJournal

NOW = datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc)


def portfolio():
    return PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))


def intent(idx):
    return TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                       f"sv-draft-{idx}", f"evidence-{idx}", NOW)


class JournalTests(unittest.TestCase):
    def test_draft_persists_across_reopen_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "drafts.sqlite3"
            with OfflineDraftJournal(path) as first:
                draft = first.record(intent(1), portfolio(), checked_at=NOW,
                                     reference_price=Decimal("65000"))
                self.assertEqual(first.total_reserved_usd(), Decimal("15"))
                self.assertIn("DRAFT ONLY", draft.note)
            with OfflineDraftJournal(path) as again:
                self.assertEqual(again.record(intent(1), portfolio(), checked_at=NOW,
                                              reference_price=Decimal("65000")), draft)
                self.assertEqual(len(again.recent_events()), 1)
                self.assertEqual(again.total_reserved_usd(), Decimal("15"))
                with self.assertRaisesRegex(ValueError, "collision"):
                    again.record(replace(intent(1), signal_id="something-else"), portfolio(),
                                 checked_at=NOW, reference_price=Decimal("65000"))
                self.assertEqual(len(again.recent_events()), 1)

    def test_pending_reservations_count_towards_global_cap(self):
        with OfflineDraftJournal(":memory:") as book:
            book.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            book.record(intent(2), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            with self.assertRaises(PermissionError):
                book.record(intent(3), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            self.assertEqual(book.total_reserved_usd(), Decimal("30"))
            self.assertEqual(len(book.recent_events()), 2)

    def test_void_releases_reservation_with_immutable_audit(self):
        with OfflineDraftJournal(":memory:") as book:
            book.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            book.void("sv-draft-1", reason="offline cancellation test", at=NOW)
            self.assertEqual(book.total_reserved_usd(), Decimal("0"))
            self.assertEqual([e["type"] for e in book.recent_events()],
                             ["DRAFT_APPROVED", "DRAFT_VOIDED"])
            with self.assertRaises(ValueError):
                book.record(intent(1), portfolio(), checked_at=NOW, reference_price=Decimal("65000"))
            with self.assertRaises(Exception):
                book.connection.execute("DELETE FROM events")

    def test_no_broker_submission_or_transfer_capability(self):
        self.assertFalse(hasattr(OfflineDraftJournal, "submit_order"))
        self.assertFalse(hasattr(OfflineDraftJournal, "transfer"))
        with OfflineDraftJournal(":memory:") as book:
            too_big = replace(portfolio(), cash_usd=Decimal("100000"), equity_usd=Decimal("100000"),
                              peak_equity_usd=Decimal("100000"), session_start_equity_usd=Decimal("100000"))
            with self.assertRaisesRegex(ValueError, r"logical \$100"):
                book.record(intent(1), too_big, checked_at=NOW, reference_price=Decimal("65000"))


if __name__ == "__main__":
    unittest.main()

class LogicalGainSnapshotTests(unittest.TestCase):
    def test_unverified_snapshot_above_initial_100_still_rejected(self):
        from signal_vault.journal import OfflineDraftJournal
        from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
        from datetime import datetime, timezone
        from decimal import Decimal
        now = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)
        intent = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                             "gain-untrusted", "sig-gain", now)
        p = PortfolioSnapshot(Decimal("101"), Decimal("101"), Decimal("101"), Decimal("101"))
        with OfflineDraftJournal(":memory:") as journal:
            with self.assertRaisesRegex(ValueError, "initial capital"):
                journal.record(intent, p, checked_at=now, reference_price=Decimal("65000"))
