import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.health import build_health_snapshot, write_health_snapshot
from signal_vault.paper_runtime import PaperCycleResult


class HealthTests(unittest.TestCase):
    def test_snapshot_has_only_logical_safe_fields_and_atomic_permissions(self):
        now = datetime(2026, 9, 28, 22, tzinfo=timezone.utc)
        result = PaperCycleResult("HOLD", "provider said account_id=SHOULD_NOT_LEAK secret=NO")
        logical = {"cash_usd": Decimal("100"), "btc_qty": Decimal("0"),
                   "realized_pnl_usd": Decimal("0"), "fees_usd_equiv": Decimal("0")}
        payload = build_health_snapshot(result=result, logical=logical,
                                        operator_halted=False, at=now)
        text = json.dumps(payload)
        self.assertNotIn("secret", text.lower())
        self.assertNotIn("account_id", text.lower())
        self.assertNotIn("should_not_leak", text.lower())
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "health.json"
            write_health_snapshot(path, payload)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["state"], "HOLD")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlink_health_target_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target"
            target.write_text("do not overwrite")
            link = root / "health.json"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                write_health_snapshot(link, {"state": "x"})
            self.assertEqual(target.read_text(), "do not overwrite")
