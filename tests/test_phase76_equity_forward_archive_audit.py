import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.equity_forward_archive_audit import (
    audit_equity_forward_archive,
)
from signal_vault.equity_forward_collector import (
    archive_equity_forward_session_plan,
    archive_prospective_equity_hour,
    collect_precommitted_equity_hour,
    precommit_equity_forward_session,
)
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.research_universe import ResearchBar


UTC = timezone.utc


class FakeProvider:
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret

    def fetch(
        self,
        *,
        specs,
        start,
        end,
        as_of,
        equity_feed,
        equity_expected_open_minutes,
    ):
        bars = {
            symbol: (
                ResearchBar(
                    symbol=symbol,
                    start_utc=start,
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("99"),
                    close=Decimal("101"),
                    volume=Decimal("1000"),
                    feed="alpaca_equity_iex|adjustment=all",
                    captured_utc=as_of,
                    prospective=False,
                ),
            )
            for symbol in SYMBOLS
        }
        return HistoricalDataBatch(
            asset_class="us_equity",
            symbols=tuple(SYMBOLS),
            feed="alpaca_equity_iex",
            adjustment="all",
            start_utc=start.isoformat(),
            end_utc=end.isoformat(),
            downloaded_utc=as_of.isoformat(),
            page_count=1,
            bars=bars,
        )


def populate_session(root: Path, trading_date: date):
    plan = precommit_equity_forward_session(
        trading_date=trading_date,
        planned_at=datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            12,
            0,
            tzinfo=UTC,
        ),
    )
    plan_path = archive_equity_forward_session_plan(plan, output_root=root)
    receipts = []
    for raw_open in plan["expected_core_opens_utc"]:
        opened = datetime.fromisoformat(raw_open)
        item = collect_precommitted_equity_hour(
            plan=plan,
            core_open_utc=opened,
            captured_at=opened + timedelta(hours=1, minutes=7),
            key="paper-data-key",
            secret="paper-data-secret",
            provider_factory=FakeProvider,
        )
        receipts.append(
            archive_prospective_equity_hour(item, output_root=root)
        )
    return plan, plan_path, receipts


class EquityForwardArchiveAuditTests(unittest.TestCase):
    def make_root(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "equity-forward"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        return root

    def test_three_complete_sessions_form_one_clean_segment(self):
        root = self.make_root()
        expected_hours = 0
        for trading_date in (
            date(2026, 9, 28),
            date(2026, 9, 29),
            date(2026, 9, 30),
        ):
            plan, _, _ = populate_session(root, trading_date)
            expected_hours += plan["expected_core_hour_count"]
        result = audit_equity_forward_archive(root)
        self.assertEqual(result["current_segment_distinct_xnys_sessions"], 3)
        self.assertEqual(
            result["current_segment_prospective_core_hours_per_asset"],
            expected_hours,
        )
        self.assertEqual(
            result["current_segment_prospective_asset_bar_count"],
            expected_hours * 6,
        )
        self.assertEqual(result["prior_or_current_gap_count"], 0)
        self.assertTrue(
            result["current_segment_complete_six_stock_grid_verified"]
        )
        self.assertTrue(result["source_integrity_passed"])
        self.assertEqual(result["network_requests"], "NONE")
        self.assertEqual(result["broker_order_submission"], "DISABLED")
        self.assertEqual(result["live_order_submission"], "DISABLED")

    def test_missing_hour_breaks_segment_and_only_later_complete_session_counts(self):
        root = self.make_root()
        _, _, first = populate_session(root, date(2026, 9, 28))
        _, _, middle = populate_session(root, date(2026, 9, 29))
        final_plan, _, final = populate_session(root, date(2026, 9, 30))
        middle[len(middle) // 2].unlink()
        result = audit_equity_forward_archive(root)
        self.assertGreaterEqual(result["prior_or_current_gap_count"], 1)
        self.assertEqual(result["current_segment_distinct_xnys_sessions"], 1)
        self.assertEqual(
            result["current_segment_prospective_core_hours_per_asset"],
            final_plan["expected_core_hour_count"],
        )
        self.assertEqual(
            result["audited_xnys_sessions"][-2]["status"],
            "INCOMPLETE",
        )
        self.assertEqual(
            result["audited_xnys_sessions"][-1]["status"],
            "COMPLETE",
        )
        self.assertTrue(first)
        self.assertTrue(final)

    def test_missing_entire_premarket_plan_is_visible_as_session_gap(self):
        root = self.make_root()
        populate_session(root, date(2026, 9, 28))
        _, plan_path, receipts = populate_session(root, date(2026, 9, 29))
        final_plan, _, _ = populate_session(root, date(2026, 9, 30))
        plan_path.unlink()
        for path in receipts:
            path.unlink()
        result = audit_equity_forward_archive(root)
        middle = result["audited_xnys_sessions"][-2]
        self.assertEqual(
            middle["status"],
            "MISSING_PRECOMMITTED_SESSION_PLAN",
        )
        self.assertEqual(result["current_segment_distinct_xnys_sessions"], 1)
        self.assertEqual(
            result["current_segment_prospective_core_hours_per_asset"],
            final_plan["expected_core_hour_count"],
        )

    def test_tampered_receipt_is_rejected_instead_of_recounted(self):
        root = self.make_root()
        _, _, receipts = populate_session(root, date(2026, 9, 30))
        receipts[0].write_text('{"kind":"tampered"}\n')
        with self.assertRaises(ValueError):
            audit_equity_forward_archive(root)

    def test_unexpected_file_is_rejected(self):
        root = self.make_root()
        populate_session(root, date(2026, 9, 30))
        extra = root / "notes.txt"
        extra.write_text("not evidence")
        extra.chmod(0o600)
        with self.assertRaises(ValueError):
            audit_equity_forward_archive(root)


if __name__ == "__main__":
    unittest.main()
