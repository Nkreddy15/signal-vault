import tempfile
import unittest
from pathlib import Path

from signal_vault.runtime_lock import RuntimeAlreadyLocked, RuntimeFileLock


class RuntimeLockTests(unittest.TestCase):
    def test_second_lock_is_rejected_and_release_allows_reacquire(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "paper.lock"
            first = RuntimeFileLock(path).acquire()
            try:
                with self.assertRaises(RuntimeAlreadyLocked):
                    RuntimeFileLock(path).acquire()
            finally:
                first.release()
            with RuntimeFileLock(path):
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlink_lock_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target"
            target.write_text("x")
            link = root / "lock"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                RuntimeFileLock(link).acquire()
