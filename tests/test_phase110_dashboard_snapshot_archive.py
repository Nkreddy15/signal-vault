import tempfile
import unittest
from pathlib import Path

from signal_vault.dashboard_namespace import DASHBOARD_BASENAME
from signal_vault.dashboard_snapshot_archive import (
    archive_dashboard_snapshot,
    read_dashboard_snapshot,
)


class DashboardSnapshotArchiveTests(unittest.TestCase):
    def make_root(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/"forward"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        return root

    def test_atomic_private_snapshot_round_trip(self):
        root=self.make_root()
        payload={
            "kind":"SIGNAL_VAULT_ALL_MARKET_OPERATOR_DASHBOARD_READ_ONLY",
            "checked_at_utc":"2026-10-01T04:10:28+00:00",
            "paper_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }
        path=archive_dashboard_snapshot(payload,base=root)
        self.assertEqual(path.parent.name,DASHBOARD_BASENAME)
        self.assertEqual(path.parent.stat().st_mode&0o077,0)
        self.assertEqual(path.stat().st_mode&0o077,0)
        self.assertEqual(read_dashboard_snapshot(base=root),payload)

    def test_snapshot_replaces_previous_value_without_temp_residue(self):
        root=self.make_root()
        first={"kind":"one","value":1}
        second={"kind":"two","value":2}
        path=archive_dashboard_snapshot(first,base=root)
        archive_dashboard_snapshot(second,base=root)
        self.assertEqual(read_dashboard_snapshot(base=root),second)
        self.assertEqual(tuple(path.parent.glob("*.tmp")),())

    def test_symlink_namespace_fails_closed(self):
        root=self.make_root()
        outside=root/"outside"
        outside.mkdir(mode=0o700)
        (root/DASHBOARD_BASENAME).symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):
            archive_dashboard_snapshot({"kind":"x"},base=root)


if __name__=="__main__":
    unittest.main()
