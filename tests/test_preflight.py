import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from signal_vault.journal import OfflineDraftJournal
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.preflight import inspect_paper_runtime, PreflightError
from signal_vault.init_paper import main as initialize


class OfflinePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "paper.sqlite3"

    def test_explicit_initialization_creates_private_database(self):
        self.assertEqual(initialize(["--db", str(self.db)]), 0)
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        response = inspect_paper_runtime(self.db)
        self.assertEqual(response["status"], "READ_ONLY_PREFLIGHT_OK")
        self.assertFalse(response["paper_order_post_enabled"])
        self.assertFalse(response["authenticated_provider_read_performed"])
        self.assertFalse(response["live_trading_available"])

    def test_fails_when_database_missing(self):
        with self.assertRaises(PreflightError):
            inspect_paper_runtime(self.db)
        self.assertFalse(self.db.exists())

    def test_existing_world_readable_database_is_tightened_by_store(self):
        with PersistentPaperOrderStore(self.db):
            pass
        os.chmod(self.db, 0o644)
        with self.assertRaises(PreflightError):
            inspect_paper_runtime(self.db)
        with OfflineDraftJournal(self.db):
            pass
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        self.assertEqual(inspect_paper_runtime(self.db)["status"], "READ_ONLY_PREFLIGHT_OK")

    def test_disk_pressure_fails_closed(self):
        with PersistentPaperOrderStore(self.db):
            pass
        with self.assertRaises(PreflightError):
            inspect_paper_runtime(self.db, minimum_free_bytes=10**30)

    def test_corrupt_sqlite_fails_closed(self):
        self.db.write_bytes(b"not a sqlite db")
        os.chmod(self.db, 0o600)
        with self.assertRaises(PreflightError):
            inspect_paper_runtime(self.db)

    def test_symlink_rejected_by_both_store_and_preflight(self):
        with PersistentPaperOrderStore(self.db):
            pass
        link = Path(self.temp.name) / "linked.sqlite3"
        link.symlink_to(self.db)
        with self.assertRaises(ValueError):
            OfflineDraftJournal(link)
        with self.assertRaises(PreflightError):
            inspect_paper_runtime(link)

    def test_unresolved_paper_order_report_does_not_authorize_retry(self):
        with PersistentPaperOrderStore(self.db) as store:
            store.connection.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?,datetime('now'))",
                                     ("one", "hash", "signal", "DRAFT_APPROVED", "buy", "15", "{}"))
            store.connection.execute("INSERT INTO paper_order_states VALUES (?,?,datetime('now'))",
                                     ("one", '{"client_order_id":"one","stage":"unknown_result","broker_order_id":null,"provider_status":null,"cumulative_filled_qty":"0","filled_avg_price":null,"reconciled":false}'))
        status = inspect_paper_runtime(self.db)
        self.assertTrue(status["provider_lookup_required"])
        self.assertFalse(status["paper_order_post_enabled"])


if __name__ == "__main__":
    unittest.main()
