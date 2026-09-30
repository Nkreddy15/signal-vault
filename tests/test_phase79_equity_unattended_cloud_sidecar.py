import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.ci_historical_equities import SYMBOLS
from signal_vault.equity_cloud_sidecar import (
    ACTIVATION,
    ACTIVATION_ENV,
    KEY_ENV,
    ROOT_ENV,
    SECRET_ENV,
    run_equity_sidecar_once,
)
from signal_vault.multi_asset_historical import HistoricalDataBatch
from signal_vault.research_universe import ResearchBar


UTC = timezone.utc


class FakeProvider:
    instances = []

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
        self.calls.append((start, end, as_of, equity_feed))
        bars = {}
        for idx, symbol in enumerate(SYMBOLS):
            base = Decimal("100") + Decimal(idx)
            bars[symbol] = (
                ResearchBar(
                    symbol=symbol,
                    start_utc=start,
                    open=base,
                    high=base + Decimal("1"),
                    low=base - Decimal("1"),
                    close=base + Decimal("0.25"),
                    volume=Decimal("1000"),
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


class EquityCloudSidecarTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "forward"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        FakeProvider.instances = []
        self.base_env = {
            ACTIVATION_ENV: ACTIVATION,
            ROOT_ENV: str(self.root),
        }

    def test_inactive_sidecar_does_not_touch_filesystem_or_credentials(self):
        result = run_equity_sidecar_once(
            env={ROOT_ENV: str(self.root)},
            now=datetime(2026, 9, 30, 13, 7, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        self.assertEqual(result["status"], "INACTIVE")
        self.assertFalse(result["credentials_accessed"])
        self.assertFalse((self.root / "isolated-six-stock-prospective").exists())
        self.assertEqual(FakeProvider.instances, [])

    def test_premarket_tick_precommits_plan_without_data_credentials(self):
        result = run_equity_sidecar_once(
            env=self.base_env,
            now=datetime(2026, 9, 30, 13, 7, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        self.assertEqual(result["status"], "PRECOMMITTED_SESSION_PLAN")
        self.assertFalse(result["credentials_accessed"])
        self.assertGreaterEqual(result["expected_core_hour_count"], 3)
        sidecar = self.root / "isolated-six-stock-prospective"
        self.assertEqual(
            len(tuple(sidecar.glob("equity-forward-plan-20260930-*.json"))),
            1,
        )
        self.assertEqual(FakeProvider.instances, [])

    def test_due_hour_uses_one_get_then_duplicate_tick_uses_no_provider(self):
        run_equity_sidecar_once(
            env=self.base_env,
            now=datetime(2026, 9, 30, 13, 7, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        env = {
            **self.base_env,
            KEY_ENV: "paper-data-key",
            SECRET_ENV: "paper-data-secret",
        }
        first = run_equity_sidecar_once(
            env=env,
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        self.assertEqual(
            first["status"],
            "ONE_SIX_STOCK_CORE_HOUR_CAPTURED",
        )
        self.assertTrue(first["credentials_accessed"])
        self.assertFalse(first["credential_values_in_output"])
        self.assertEqual(first["prospective_asset_bar_count_added"], 6)
        self.assertEqual(len(FakeProvider.instances), 1)
        self.assertEqual(len(FakeProvider.instances[0].calls), 1)
        self.assertEqual(FakeProvider.instances[0].calls[0][3], "iex")

        repeated = run_equity_sidecar_once(
            env=env,
            now=datetime(2026, 9, 30, 15, 8, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        self.assertEqual(repeated["status"], "ALREADY_CAPTURED")
        self.assertFalse(repeated["credentials_accessed"])
        self.assertEqual(len(FakeProvider.instances), 1)
        self.assertEqual(repeated["broker_order_submission"], "DISABLED")
        self.assertEqual(repeated["live_order_submission"], "DISABLED")

    def test_missing_premarket_plan_never_backfills_after_open(self):
        env = {
            **self.base_env,
            KEY_ENV: "paper-data-key",
            SECRET_ENV: "paper-data-secret",
        }
        result = run_equity_sidecar_once(
            env=env,
            now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        self.assertEqual(
            result["status"],
            "NO_CAPTURE_NO_PRECOMMITTED_PLAN",
        )
        self.assertFalse(result["credentials_accessed"])
        self.assertEqual(FakeProvider.instances, [])
        sidecar = self.root / "isolated-six-stock-prospective"
        self.assertEqual(tuple(sidecar.glob("equity-forward-20260930T1400Z-*.json")), ())

    def test_weekend_tick_is_noop_and_never_uses_provider(self):
        result = run_equity_sidecar_once(
            env=self.base_env,
            now=datetime(2026, 10, 3, 15, 7, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        self.assertEqual(
            result["status"],
            "NO_CAPTURE_NO_PRECOMMITTED_PLAN",
        )
        self.assertFalse(result["credentials_accessed"])
        self.assertEqual(FakeProvider.instances, [])

    def test_plan_tamper_blocks_capture_before_provider(self):
        run_equity_sidecar_once(
            env=self.base_env,
            now=datetime(2026, 9, 30, 13, 7, tzinfo=UTC),
            provider_factory=FakeProvider,
        )
        sidecar = self.root / "isolated-six-stock-prospective"
        plan = next(sidecar.glob("equity-forward-plan-20260930-*.json"))
        plan.write_text('{"kind":"tampered"}')
        plan.chmod(0o600)
        with self.assertRaises(ValueError):
            run_equity_sidecar_once(
                env={
                    **self.base_env,
                    KEY_ENV: "paper-data-key",
                    SECRET_ENV: "paper-data-secret",
                },
                now=datetime(2026, 9, 30, 15, 7, tzinfo=UTC),
                provider_factory=FakeProvider,
            )
        self.assertEqual(FakeProvider.instances, [])


if __name__ == "__main__":
    unittest.main()
