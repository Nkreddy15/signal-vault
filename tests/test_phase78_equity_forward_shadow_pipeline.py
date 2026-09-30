import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_equities import SYMBOLS, execute_manual_equity_history
from signal_vault.ci_long_equity_history import APPROVAL, execute_long_equity_history
from signal_vault.equity_forward_collector import (
    archive_equity_forward_session_plan,
    archive_prospective_equity_hour,
    collect_precommitted_equity_hour,
    precommit_equity_forward_session,
)
from signal_vault.equity_forward_shadow_pipeline import (
    build_equity_forward_shadow_pipeline,
)
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.offline_long_equity_validation import validate_long_equity_history
from signal_vault.research_universe import ResearchBar
from test_ci_historical_equities import FakeLiquidIEXProvider


UTC = timezone.utc
NOW = datetime(2026, 9, 30, 21, 0, tzinfo=UTC)
ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REPOSITORY": "Nkreddy15/signal-vault",
    "GITHUB_REF": "refs/heads/main",
    "SIGNAL_VAULT_LONG_EQUITY_READ_APPROVED": APPROVAL,
    "SIGNAL_VAULT_LONG_EQUITY_START_DATE": "2026-07-01",
    "SIGNAL_VAULT_LONG_EQUITY_END_DATE_EXCLUSIVE": "2026-09-17",
    "SIGNAL_VAULT_RESEARCH_DATA_KEY_ID": "FIXTURE_NEVER_REAL_KEY",
    "SIGNAL_VAULT_RESEARCH_DATA_SECRET": "FIXTURE_NEVER_REAL_SECRET",
}
CANDIDATE = "generic-momentum24bar50bps-v1-predeclared"


class ForwardProvider:
    counter = 0

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
        type(self).counter += 1
        step = Decimal(type(self).counter) / Decimal("100")
        bars = {}
        for idx, symbol in enumerate(SYMBOLS):
            base = Decimal("150") + Decimal(idx * 3) + step
            bars[symbol] = (
                ResearchBar(
                    symbol=symbol,
                    start_utc=start,
                    open=base,
                    high=base + Decimal("2"),
                    low=base - Decimal("2"),
                    close=base + Decimal("0.50"),
                    volume=Decimal("2000"),
                    feed="alpaca_equity_iex|adjustment=all",
                    captured_utc=as_of,
                    prospective=False,
                ),
            )
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


class EquityForwardShadowPipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.history_root = base / "history"
        self.forward_root = base / "forward"
        self.forward_root.mkdir(mode=0o700)
        self.forward_root.chmod(0o700)
        FakeLiquidIEXProvider.instances = []
        FakeLiquidIEXProvider.drop_session = None
        ForwardProvider.counter = 0

    @staticmethod
    def fake_runner(*, env, as_of, output_folder):
        return execute_manual_equity_history(
            env=env,
            as_of=as_of,
            provider_factory=FakeLiquidIEXProvider,
            output_folder=output_folder,
        )

    def build_history(self):
        execute_long_equity_history(
            env=ENV,
            as_of=NOW,
            output_root=self.history_root,
            runner=self.fake_runner,
        )
        return validate_long_equity_history(self.history_root, as_of=NOW)

    def build_forward(self):
        receipts = []
        for trading_date in (
            date(2026, 9, 17),
            date(2026, 9, 18),
            date(2026, 9, 21),
            date(2026, 9, 22),
            date(2026, 9, 23),
            date(2026, 9, 24),
            date(2026, 9, 25),
            date(2026, 9, 28),
            date(2026, 9, 29),
            date(2026, 9, 30),
        ):
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
            archive_equity_forward_session_plan(
                plan,
                output_root=self.forward_root,
            )
            for raw_open in plan["expected_core_opens_utc"]:
                opened = datetime.fromisoformat(raw_open)
                item = collect_precommitted_equity_hour(
                    plan=plan,
                    core_open_utc=opened,
                    captured_at=opened + timedelta(hours=1, minutes=7),
                    key="paper-data-key",
                    secret="paper-data-secret",
                    provider_factory=ForwardProvider,
                )
                receipts.append(
                    archive_prospective_equity_hour(
                        item,
                        output_root=self.forward_root,
                    )
                )
        return receipts

    @staticmethod
    def confirmation(source_sha):
        return {
            "kind": "EQUITY_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER",
            "phase48_source_manifest_sha256": source_sha,
            "candidate_added_by_untouched_test": False,
            "candidate_ranking_performed": False,
            "automatic_candidate_selection": "DISABLED",
            "paper_order_submission": "DISABLED",
            "live_order_submission": "DISABLED",
            "candidates_confirmed_on_untouched_test": [CANDIDATE],
        }

    def test_verified_history_and_ten_future_sessions_build_shadow_without_orders(self):
        baseline = self.build_history()
        self.build_forward()
        result = build_equity_forward_shadow_pipeline(
            historical_source_root=self.history_root,
            forward_root=self.forward_root,
            historical_confirmation=self.confirmation(
                baseline["source_manifest_sha256"]
            ),
            as_of=NOW,
        )
        self.assertEqual(
            result["kind"],
            "EQUITY_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS",
        )
        self.assertEqual(result["prospective_core_hours_per_asset"], 60)
        self.assertEqual(result["distinct_xnys_sessions"], 10)
        self.assertTrue(result["historical_source_replayed_before_shadow"])
        self.assertTrue(result["forward_archive_audited_before_shadow"])
        self.assertTrue(result["warmup_and_prospective_xnys_clock_adjacent"])
        self.assertFalse(result["historical_warmup_counted_as_prospective"])
        self.assertEqual(result["network_requests_during_pipeline"], "NONE")
        self.assertEqual(result["paper_order_submission"], "DISABLED")
        self.assertEqual(result["live_order_submission"], "DISABLED")

    def test_confirmation_from_another_historical_dataset_is_rejected(self):
        baseline = self.build_history()
        self.build_forward()
        wrong = self.confirmation(baseline["source_manifest_sha256"])
        wrong["phase48_source_manifest_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            build_equity_forward_shadow_pipeline(
                historical_source_root=self.history_root,
                forward_root=self.forward_root,
                historical_confirmation=wrong,
                as_of=NOW,
            )

    def test_forward_gap_breaks_segment_and_blocks_60_hour_summary(self):
        baseline = self.build_history()
        receipts = self.build_forward()
        receipts[len(receipts) // 2].unlink()
        with self.assertRaises(ValueError):
            build_equity_forward_shadow_pipeline(
                historical_source_root=self.history_root,
                forward_root=self.forward_root,
                historical_confirmation=self.confirmation(
                    baseline["source_manifest_sha256"]
                ),
                as_of=NOW,
            )


if __name__ == "__main__":
    unittest.main()
