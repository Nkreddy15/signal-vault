import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.backup import DailyBackupManager, create_sqlite_backup, verify_sqlite_backup
from signal_vault.paper_store import PersistentPaperOrderStore

NOW=datetime(2026,9,28,22,tzinfo=timezone.utc)


class BackupTests(unittest.TestCase):
    def test_online_backup_is_integrity_checked_hashed_and_owner_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db=root/"paper.db"
            with PersistentPaperOrderStore(db) as store:
                result=create_sqlite_backup(db,root/"backups",at=NOW,label="startup")
            self.assertTrue(verify_sqlite_backup(result.database_path,result.manifest_path))
            self.assertEqual(result.database_path.stat().st_mode & 0o777,0o600)
            self.assertEqual(result.manifest_path.stat().st_mode & 0o777,0o600)


    def test_daily_manager_backs_up_once_per_utc_day(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db=root/"paper.db"
            with PersistentPaperOrderStore(db): pass
            manager=DailyBackupManager(db,root/"b")
            first=manager.maybe_backup(at=NOW)
            second=manager.maybe_backup(at=NOW)
            self.assertIsNotNone(first)
            self.assertIsNone(second)

    def test_existing_named_backup_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db=root/"paper.db"
            with PersistentPaperOrderStore(db): pass
            create_sqlite_backup(db,root/"b",at=NOW,label="daily")
            with self.assertRaises(FileExistsError):
                create_sqlite_backup(db,root/"b",at=NOW,label="daily")

    def test_tampering_breaks_hash_verification(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db=root/"paper.db"
            with PersistentPaperOrderStore(db): pass
            result=create_sqlite_backup(db,root/"b",at=NOW)
            with result.database_path.open("ab") as f: f.write(b"tamper")
            self.assertFalse(verify_sqlite_backup(result.database_path,result.manifest_path))
