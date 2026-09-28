import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.operator import main

class OperatorCLITests(unittest.TestCase):
    def test_persistent_operator_actions_are_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'realistic_paper.sqlite'
            with PersistentPaperOrderStore(db):pass
            def call(*args):
                stream=io.StringIO()
                with redirect_stdout(stream):
                    self.assertEqual(main(['--db',str(db),*args]),0)
                return json.loads(stream.getvalue())
            self.assertFalse(call('status')['operator_halt'])
            self.assertTrue(call('halt','--reason','owner intervention')['operator_halt'])
            self.assertTrue(call('status')['operator_halt'])
            self.assertFalse(call('resume','--reason','owner reviewed')['operator_halt'])
            with self.assertRaises(ValueError):
                call('resume','--reason','no active halt')
    def test_does_not_silently_initialize_an_empty_or_wrong_database(self):
        with tempfile.TemporaryDirectory() as td:
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                main(['--db',str(Path(td)/'missing.sqlite'),'halt','--reason','test'])
            self.assertFalse((Path(td)/'missing.sqlite').exists())

if __name__=='__main__':unittest.main()
