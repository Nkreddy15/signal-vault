import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.equity_forward_collector import (
    archive_prospective_equity_hour,
    collect_precommitted_equity_hour,
    precommit_equity_forward_session,
)
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.research_universe import ResearchBar


UTC = timezone.utc
TRADING_DATE = date(2026, 9, 30)
PLANNED_AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


class FakeProvider:
    instances = []
    omit_symbol = None
    wrong_hour = False

    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
        self.calls = []
        type(self).instances.append(self)

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
        self.calls.append(
            {
                "specs": specs,
                "start": start,
                "end": end,
                "as_of": as_of,
                "feed": equity_feed,
                "calendar": equity_expected_open_minutes,
            }
        )
        bars = {}
        for symbol in SYMBOLS:
            if symbol == type(self).omit_symbol:
                continue
            opened = start + (timedelta(hours=1) if type(self).wrong_hour else timedelta())
            bars[symbol] = (
                ResearchBar(
                    symbol=symbol,
                    start_utc=opened,
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
        return HistoricalDataBatch(
            asset_class="us_equity",
            symbols=tuple(sorted(bars)),
            feed="alpaca_equity_iex",
            adjustment="all",
            start_utc=start.isoformat(),
            end_utc=end.isoformat(),
            downloaded_utc=as_of.isoformat(),
            page_count=1,
            bars=bars,
        )


class EquityForwardCollectorTests(unittest.TestCase):
    def setUp(self):
        FakeProvider.instances = []
        FakeProvider.omit_symbol = None
        FakeProvider.wrong_hour = False
        self.plan = precommit_equity_forward_session(
            trading_date=TRADING_DATE,
            planned_at=PLANNED_AT,
        )
        self.core_open = datetime.fromisoformat(
            self.plan["expected_core_opens_utc"][0]
        )
        self.captured = self.core_open + timedelta(hours=1, minutes=7)

    def test_plan_is_precommitted_before_open_and_no_order(self):
        self.assertEqual(
            self.plan["kind"],
            "PRECOMMITTED_XNYS_SIX_STOCK_FORWARD_SESSION_PLAN",
        )
        self.assertEqual(self.plan["symbols"], list(SYMBOLS))
        self.assertEqual(self.plan["feed"], "iex")
        self.assertFalse(self.plan["historical_backfill_allowed"])
        self.assertEqual(self.plan["broker_order_submission"], "DISABLED")
        self.assertEqual(self.plan["live_order_submission"], "DISABLED")
        self.assertEqual(len(self.plan["plan_sha256"]), 64)
        self.assertGreaterEqual(self.plan["expected_core_hour_count"], 3)

    def test_precommit_after_market_open_is_rejected(self):
        opened = datetime.fromisoformat(self.plan["exchange_open_utc"])
        with self.assertRaises(ValueError):
            precommit_equity_forward_session(
                trading_date=TRADING_DATE,
                planned_at=opened,
            )

    def test_one_planned_closed_hour_records_exact_six_prospective_bars(self):
        item = collect_precommitted_equity_hour(
            plan=self.plan,
            core_open_utc=self.core_open,
            captured_at=self.captured,
            key="paper-data-key",
            secret="paper-data-secret",
            provider_factory=FakeProvider,
        )
        receipt = item.receipt
        self.assertEqual(receipt["symbols"], list(SYMBOLS))
        self.assertEqual(receipt["prospective_core_hours_per_asset_added"], 1)
        self.assertEqual(receipt["prospective_asset_bar_count_added"], 6)
        self.assertTrue(receipt["complete_six_stock_grid_verified"])
        self.assertEqual(receipt["historical_backfill_count"], 0)
        self.assertEqual(receipt["network_methods"], ["GET"])
        self.assertEqual(receipt["paper_order_submission"], "DISABLED")
        self.assertEqual(receipt["live_order_submission"], "DISABLED")
        self.assertNotIn("paper-data-key", json.dumps(receipt))
        self.assertNotIn("paper-data-secret", json.dumps(receipt))
        self.assertEqual(set(item.bars), set(SYMBOLS))
        self.assertTrue(all(rows[0].prospective for rows in item.bars.values()))
        self.assertEqual(len(FakeProvider.instances), 1)
        self.assertEqual(FakeProvider.instances[0].calls[0]["feed"], "iex")

    def test_premature_or_missed_capture_window_never_backfills(self):
        closed = self.core_open + timedelta(hours=1)
        for captured in (
            closed + timedelta(minutes=2),
            closed + timedelta(minutes=30),
            closed + timedelta(hours=2),
        ):
            with self.subTest(captured=captured), self.assertRaises(ValueError):
                collect_precommitted_equity_hour(
                    plan=self.plan,
                    core_open_utc=self.core_open,
                    captured_at=captured,
                    key="paper-data-key",
                    secret="paper-data-secret",
                    provider_factory=FakeProvider,
                )
        self.assertEqual(FakeProvider.instances, [])

    def test_unplanned_hour_and_tampered_plan_fail_before_credentials_are_used(self):
        with self.assertRaises(ValueError):
            collect_precommitted_equity_hour(
                plan=self.plan,
                core_open_utc=self.core_open + timedelta(days=1),
                captured_at=self.captured + timedelta(days=1),
                key="paper-data-key",
                secret="paper-data-secret",
                provider_factory=FakeProvider,
            )
        tampered = dict(self.plan)
        tampered["feed"] = "sip"
        with self.assertRaises(ValueError):
            collect_precommitted_equity_hour(
                plan=tampered,
                core_open_utc=self.core_open,
                captured_at=self.captured,
                key="paper-data-key",
                secret="paper-data-secret",
                provider_factory=FakeProvider,
            )
        self.assertEqual(FakeProvider.instances, [])

    def test_missing_or_wrong_provider_bar_fails_closed(self):
        FakeProvider.omit_symbol = "SPY"
        with self.assertRaises(ValueError):
            collect_precommitted_equity_hour(
                plan=self.plan,
                core_open_utc=self.core_open,
                captured_at=self.captured,
                key="paper-data-key",
                secret="paper-data-secret",
                provider_factory=FakeProvider,
            )
        FakeProvider.omit_symbol = None
        FakeProvider.wrong_hour = True
        with self.assertRaises(ValueError):
            collect_precommitted_equity_hour(
                plan=self.plan,
                core_open_utc=self.core_open,
                captured_at=self.captured,
                key="paper-data-key",
                secret="paper-data-secret",
                provider_factory=FakeProvider,
            )

    def test_archive_is_private_create_only_and_idempotent_only_for_same_bytes(self):
        item = collect_precommitted_equity_hour(
            plan=self.plan,
            core_open_utc=self.core_open,
            captured_at=self.captured,
            key="paper-data-key",
            secret="paper-data-secret",
            provider_factory=FakeProvider,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "equity-forward"
            root.mkdir(mode=0o700)
            root.chmod(0o700)
            path = archive_prospective_equity_hour(item, output_root=root)
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            before = path.read_bytes()
            self.assertEqual(
                archive_prospective_equity_hour(item, output_root=root),
                path,
            )
            self.assertEqual(path.read_bytes(), before)
            path.write_text("tampered")
            with self.assertRaises(ValueError):
                archive_prospective_equity_hour(item, output_root=root)


if __name__ == "__main__":
    unittest.main()
