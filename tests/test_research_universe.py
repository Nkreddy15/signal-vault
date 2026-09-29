"""Offline-only multi-asset contracts and non-inflated parallel sample accounting."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.research_universe import (
    RESEARCH_CANDIDATES, AssetClass, CandidateAsset, ResearchBar,
    candidate, summarize_parallel_research, validate_asset_dataset,
)

HOUR = timedelta(hours=1)
CLOSE = datetime(2026, 9, 29, 19, tzinfo=timezone.utc)


def row(symbol: str, start: datetime, *, feed="synthetic_data_fixture",
        price="101", prospective=True) -> ResearchBar:
    px = Decimal(price)
    return ResearchBar(
        symbol=symbol,
        start_utc=start,
        open=px,
        high=px + Decimal("2"),
        low=px - Decimal("2"),
        close=px,
        volume=Decimal("10"),
        feed=feed,
        captured_utc=start + HOUR + timedelta(minutes=7),
        prospective=prospective,
    )


class ResearchUniverseTests(unittest.TestCase):
    def test_registry_is_proposed_only_never_authorizes_data_or_orders(self):
        self.assertGreaterEqual(len(RESEARCH_CANDIDATES), 10)
        self.assertTrue(any(x.asset_class is AssetClass.CRYPTO for x in RESEARCH_CANDIDATES))
        self.assertTrue(any(x.asset_class is AssetClass.US_EQUITY for x in RESEARCH_CANDIDATES))
        for item in RESEARCH_CANDIDATES:
            self.assertFalse(item.enabled_for_data_collection)
            self.assertFalse(item.enabled_for_order_submission)
            self.assertEqual(candidate(item.symbol), item)
        with self.assertRaises(ValueError):
            candidate("../BTC/USD")
        with self.assertRaises(ValueError):
            CandidateAsset("BTC/USD", AssetClass.CRYPTO, "XNYS", "crypto_us")
        with self.assertRaises(ValueError):
            CandidateAsset("BTC/USD", AssetClass.CRYPTO, "24_7_utc", "crypto_us",
                           enabled_for_order_submission=True)

    def test_concurrent_two_assets_not_four_distinct_hours(self):
        btc = (row("BTC/USD", CLOSE-2*HOUR), row("BTC/USD", CLOSE-HOUR))
        eth = (row("ETH/USD", CLOSE-2*HOUR), row("ETH/USD", CLOSE-HOUR))
        reviews = {
            "BTC/USD": validate_asset_dataset(btc, spec=candidate("BTC/USD"),
                                              as_of=CLOSE+timedelta(minutes=9)),
            "ETH/USD": validate_asset_dataset(eth, spec=candidate("ETH/USD"),
                                              as_of=CLOSE+timedelta(minutes=9)),
        }
        self.assertEqual(reviews["BTC/USD"].historical_bars, 0)
        self.assertEqual(reviews["BTC/USD"].prospective_bars, 2)
        self.assertEqual(len(reviews["BTC/USD"].content_sha256), 64)
        summary = summarize_parallel_research(
            {"BTC/USD":btc, "ETH/USD":eth}, reviews=reviews)
        self.assertEqual(summary["asset_count"], 2)
        self.assertEqual(summary["prospective_asset_bar_count"], 4)
        self.assertEqual(summary["distinct_prospective_clock_hours"], 2)
        self.assertFalse(summary["strategy_validated"])
        self.assertEqual(summary["broker_order_submission"], "DISABLED")

    def test_hash_binds_every_research_record(self):
        btc = (row("BTC/USD", CLOSE-HOUR),)
        original = validate_asset_dataset(
            btc, spec=candidate("BTC/USD"), as_of=CLOSE+timedelta(minutes=9))
        changed = (replace(btc[0], close=Decimal("102")),)
        with self.assertRaises(ValueError):
            summarize_parallel_research(
                {"BTC/USD":changed}, reviews={"BTC/USD":original})

    def test_crypto_missing_hour_or_duplicate_or_wrong_symbol_rejected(self):
        prior = row("BTC/USD", CLOSE-3*HOUR)
        later = row("BTC/USD", CLOSE-HOUR)
        same = row("BTC/USD", CLOSE-3*HOUR)
        other = row("ETH/USD", CLOSE-HOUR)
        for rows in ((prior,later), (prior,same), (prior,other), (later,prior)):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate_asset_dataset(
                    rows, spec=candidate("BTC/USD"),
                    as_of=CLOSE+timedelta(minutes=9))

    def test_never_label_old_data_prospective_from_a_boolean_alone(self):
        start = CLOSE-10*HOUR
        far_later_capture = replace(
            row("BTC/USD", start), captured_utc=CLOSE + timedelta(minutes=7))
        with self.assertRaises(ValueError):
            validate_asset_dataset(
                (far_later_capture,), spec=candidate("BTC/USD"),
                as_of=CLOSE+timedelta(minutes=9))
        allowed_historical = replace(far_later_capture, prospective=False)
        review = validate_asset_dataset(
            (allowed_historical,), spec=candidate("BTC/USD"),
            as_of=CLOSE+timedelta(minutes=9))
        self.assertEqual(review.historical_bars, 1)
        self.assertEqual(review.prospective_bars, 0)

    def test_future_unclosed_candle_rejected(self):
        with self.assertRaises(ValueError):
            validate_asset_dataset((row("BTC/USD", CLOSE),),
                                   spec=candidate("BTC/USD"), as_of=CLOSE)

    def test_no_mixed_provider_feeds_or_bad_ohlc(self):
        a = row("BTC/USD", CLOSE-2*HOUR)
        b = row("BTC/USD", CLOSE-HOUR, feed="different_provider_feed")
        with self.assertRaises(ValueError):
            validate_asset_dataset((a,b), spec=candidate("BTC/USD"),
                                   as_of=CLOSE+timedelta(minutes=9))
        with self.assertRaises(ValueError):
            validate_asset_dataset(
                (replace(a, high=Decimal("90")),), spec=candidate("BTC/USD"),
                as_of=CLOSE+timedelta(minutes=9))

    def test_equity_needs_explicit_calendar_and_can_start_at_half_hour(self):
        start = datetime(2026, 9, 29, 13, 30, tzinfo=timezone.utc)
        spy = (row("SPY", start, feed="synthetic_equity_fixture"),
               row("SPY", start+HOUR, feed="synthetic_equity_fixture"))
        with self.assertRaises(ValueError):
            validate_asset_dataset(
                spy, spec=candidate("SPY"),
                as_of=start+2*HOUR+timedelta(minutes=10))
        reviewed = validate_asset_dataset(
            spy, spec=candidate("SPY"),
            as_of=start+2*HOUR+timedelta(minutes=10),
            expected_session_opens_utc=(start, start+HOUR))
        self.assertEqual(reviewed.bar_count, 2)
        self.assertEqual(reviewed.asset_class, "us_equity")
        with self.assertRaises(ValueError):
            validate_asset_dataset(
                spy, spec=candidate("SPY"),
                as_of=start+2*HOUR+timedelta(minutes=10),
                expected_session_opens_utc=(start, start+2*HOUR))


if __name__ == "__main__":
    unittest.main()
