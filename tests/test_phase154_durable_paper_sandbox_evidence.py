import json
import stat
import tempfile
import unittest
from pathlib import Path

from signal_vault.experimental_paper_sandbox import _write_receipt


class Phase154DurableSandboxEvidenceTests(unittest.TestCase):
    def test_receipt_is_private_create_only_json(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"receipt.json"
            _write_receipt(p,{"status":"fixture","paper_post_attempted":False})
            self.assertEqual(json.loads(p.read_text())["status"],"fixture")
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            with self.assertRaises(ValueError):
                _write_receipt(p,{"status":"overwrite-forbidden"})


if __name__=="__main__":
    unittest.main()
