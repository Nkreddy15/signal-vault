import tempfile
import unittest
from pathlib import Path

from signal_vault.experimental_paper_reconcile import _write_once


class Phase155ExperimentalPaperReconcileTests(unittest.TestCase):
    def test_reconciliation_receipt_is_create_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"reconcile.json"
            _write_once(p,{"kind":"fixture","order_submission":"DISABLED"})
            self.assertTrue(p.exists())
            with self.assertRaises(ValueError):
                _write_once(p,{"kind":"overwrite"})


if __name__=="__main__":
    unittest.main()
