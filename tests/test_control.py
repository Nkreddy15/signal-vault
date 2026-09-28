import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signal_vault.control import main
from signal_vault.paper_store import PersistentPaperOrderStore


class ControlCliTests(unittest.TestCase):
    def test_halt_status_resume_is_local_and_persistent(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "paper.db"
            env = {"SIGNAL_VAULT_PAPER_DB": str(db)}
            with patch.dict(os.environ, env, clear=True):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["halt", "--reason", "operator test"]), 0)
                with PersistentPaperOrderStore(db) as store:
                    self.assertEqual(store.operator_halt(), (True, "operator test"))
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["status"]), 0)
                self.assertIn("HALTED operator test", output.getvalue())
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["resume"]), 0)
                with PersistentPaperOrderStore(db) as store:
                    self.assertEqual(store.operator_halt(), (False, ""))

    def test_halt_requires_reason(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                main(["halt"])
