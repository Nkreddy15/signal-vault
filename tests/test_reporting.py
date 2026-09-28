import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.reporting import build_performance_report, write_report


NOW=datetime(2026,9,28,22,tzinfo=timezone.utc)


class ReportingTests(unittest.TestCase):
    def test_cash_only_empty_account_reports_zero_return_not_fake_profit(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"paper.db"
            with PersistentPaperOrderStore(path) as store:
                report=build_performance_report(store,at=NOW)
            self.assertEqual(report["logical_equity_usd"],"100")
            self.assertEqual(Decimal(report["total_return_pct"]),Decimal("0"))
            self.assertEqual(report["provider_order_count"],0)
            self.assertIn("Paper/research",report["performance_warning"])

    def test_marked_equity_drives_total_return(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"paper.db"
            with PersistentPaperOrderStore(path) as store:
                # With no BTC, changing mark doesn't manufacture equity.
                store.mark_portfolio(mark_price=Decimal("65000"),at=NOW)
                report=build_performance_report(store,at=NOW)
            self.assertEqual(report["logical_equity_usd"],"100")
            self.assertEqual(report["last_mark_price_btc_usd"],"65000")

    def test_report_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"report.json"
            write_report(path,{"mode":"ALPACA_PAPER_ONLY"})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
