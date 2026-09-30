import unittest
from datetime import date, datetime, timezone

from signal_vault.historical_chunk_plan import (
    crypto_history_chunks,
    equity_history_chunks,
    research_plan_summary,
)


class HistoricalChunkPlanTests(unittest.TestCase):
    def test_crypto_long_history_is_split_without_gaps_or_overlap(self):
        chunks = crypto_history_chunks(
            start_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_utc_exclusive=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].start, "2026-01-01T00:00:00+00:00")
        self.assertEqual(chunks[-1].end_exclusive, "2026-04-01T00:00:00+00:00")
        for before, after in zip(chunks, chunks[1:]):
            self.assertEqual(before.end_exclusive, after.start)

    def test_equity_long_history_is_split_into_safe_calendar_chunks(self):
        chunks = equity_history_chunks(
            start_date=date(2025, 10, 1),
            end_date_exclusive=date(2026, 10, 1),
        )
        self.assertGreater(len(chunks), 10)
        self.assertEqual(chunks[0].start, "2025-10-01")
        self.assertEqual(chunks[-1].end_exclusive, "2026-10-01")
        for before, after in zip(chunks, chunks[1:]):
            self.assertEqual(before.end_exclusive, after.start)

    def test_summary_is_planning_only_and_does_not_enable_orders(self):
        result = research_plan_summary(
            crypto_start_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            crypto_end_utc_exclusive=datetime(2026, 9, 30, tzinfo=timezone.utc),
            equity_start_date=date(2025, 10, 1),
            equity_end_date_exclusive=date(2026, 9, 30),
        )
        self.assertEqual(result["network_requests"], "NONE")
        self.assertEqual(result["credentials_accessed"], "NONE")
        self.assertEqual(result["broker_order_submission"], "DISABLED")
        self.assertEqual(result["live_trading"], "UNAVAILABLE")
        self.assertEqual(
            result["kalshi_history"],
            "SEPARATE_RESOLVED_MARKET_DATASET_REQUIRED",
        )

    def test_bad_bounds_fail_closed(self):
        with self.assertRaises(ValueError):
            crypto_history_chunks(
                start_utc=datetime(2026, 1, 1),
                end_utc_exclusive=datetime(2026, 2, 1, tzinfo=timezone.utc),
            )
        with self.assertRaises(ValueError):
            equity_history_chunks(
                start_date=date(2026, 2, 1),
                end_date_exclusive=date(2026, 1, 1),
            )


if __name__ == "__main__":
    unittest.main()
