import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.local_backup import private_paper_backup
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.operator_view import read_local_paper_snapshot


class PrivatePaperBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "paper.sqlite3"
        with PersistentPaperOrderStore(self.db):
            pass
        self.dest = self.root / "backup" / "snapshot.sqlite3"

    def test_copy_is_consistent_private_and_never_grants_trading_authority(self):
        with PersistentPaperOrderStore(self.db) as store:
            store.set_operator_halt(True, reason="maintenance", at=datetime.now(timezone.utc))
            result = private_paper_backup(self.db, self.dest)
        self.assertEqual(len(result.sha256), 64)
        self.assertGreater(result.bytes, 0)
        self.assertFalse(result.automatic_trading_resume_allowed)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.dest.parent.stat().st_mode & 0o777, 0o700)
        copy_state = read_local_paper_snapshot(self.dest)
        self.assertTrue(copy_state["operator_halted"])
        with sqlite3.connect(self.dest) as con:
            self.assertEqual(con.execute("PRAGMA quick_check").fetchone()[0], "ok")

    def test_existing_backup_is_not_overwritten(self):
        self.dest.parent.mkdir(mode=0o700)
        self.dest.write_text("important earlier backup")
        with self.assertRaises(FileExistsError):
            private_paper_backup(self.db, self.dest)
        self.assertEqual(self.dest.read_text(), "important earlier backup")

    def test_backup_directory_must_be_private(self):
        self.dest.parent.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            private_paper_backup(self.db, self.dest)
        self.assertFalse(self.dest.exists())

    def test_missing_source_never_creates_backup(self):
        self.db.unlink()
        with self.assertRaises(Exception):
            private_paper_backup(self.db, self.dest)
        self.assertFalse(self.dest.exists())

    def test_destination_symlink_is_refused(self):
        self.dest.parent.mkdir(mode=0o700)
        old = self.root / "untouched.txt"
        old.write_text("do not overwrite")
        self.dest.symlink_to(old)
        with self.assertRaises(FileExistsError):
            private_paper_backup(self.db, self.dest)
        self.assertEqual(old.read_text(), "do not overwrite")


if __name__ == "__main__":
    unittest.main()
