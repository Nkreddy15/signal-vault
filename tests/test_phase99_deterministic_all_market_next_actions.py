import unittest

from signal_vault.all_market_forward_status import (
    _equity_next_action,
    _kalshi_next_action,
)


class DeterministicAllMarketNextActionsTests(unittest.TestCase):
    def test_equity_collection_states_never_authorize_orders(self):
        self.assertEqual(
            _equity_next_action(
                status="NOT_STARTED",
                integrity_status="NOT_READY_RAW_EVIDENCE_INCOMPLETE",
                source_ready=False,
                due_open=0,
                missing_expired=0,
            ),
            "WAIT_FOR_NEXT_XNYS_PREMARKET_SESSION_PLAN",
        )
        self.assertEqual(
            _equity_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="NOT_READY_RAW_EVIDENCE_INCOMPLETE",
                source_ready=False,
                due_open=1,
                missing_expired=0,
            ),
            "CAPTURE_DUE_STOCK_CORE_HOURS_GET_ONLY",
        )
        self.assertEqual(
            _equity_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="NOT_READY_RAW_EVIDENCE_INCOMPLETE",
                source_ready=False,
                due_open=0,
                missing_expired=1,
            ),
            "CONTINUE_NEW_CLEAN_STOCK_SEGMENT_NO_BACKFILL",
        )

    def test_equity_verified_source_only_hands_off_to_offline_scoring(self):
        self.assertEqual(
            _equity_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="AVAILABLE",
                source_ready=True,
                due_open=0,
                missing_expired=0,
            ),
            "OFFLINE_STOCK_SHADOW_SCORING_INPUTS_REQUIRED",
        )
        self.assertEqual(
            _equity_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="FAILED",
                source_ready=False,
                due_open=0,
                missing_expired=0,
            ),
            "OPERATOR_REVIEW_STOCK_SOURCE_INTEGRITY_FAILED_NO_TRADING",
        )

    def test_kalshi_collection_states_prioritize_due_decisions_then_settlements(self):
        self.assertEqual(
            _kalshi_next_action(
                status="NOT_STARTED",
                integrity_status="NOT_READY_RAW_EVIDENCE_INCOMPLETE",
                source_ready=False,
                window_open=0,
                missing_expired=0,
                settlement_pending=0,
            ),
            "PRECOMMIT_PUBLIC_KALSHI_PROSPECTIVE_PLAN_GET_ONLY",
        )
        self.assertEqual(
            _kalshi_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="NOT_READY_RAW_EVIDENCE_INCOMPLETE",
                source_ready=False,
                window_open=2,
                missing_expired=0,
                settlement_pending=3,
            ),
            "CAPTURE_DUE_KALSHI_FIXED_HORIZON_QUOTES_GET_ONLY",
        )
        self.assertEqual(
            _kalshi_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="NOT_READY_RAW_EVIDENCE_INCOMPLETE",
                source_ready=False,
                window_open=0,
                missing_expired=0,
                settlement_pending=3,
            ),
            "RETRY_PUBLIC_KALSHI_SETTLEMENT_GETS",
        )

    def test_kalshi_misses_are_preserved_and_integrity_failure_stops_promotion(self):
        self.assertEqual(
            _kalshi_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="NOT_READY_RAW_EVIDENCE_INCOMPLETE",
                source_ready=False,
                window_open=0,
                missing_expired=2,
                settlement_pending=0,
            ),
            "CONTINUE_PRECOMMITTED_SAMPLE_WITH_MISSES_RECORDED_NO_BACKFILL",
        )
        self.assertEqual(
            _kalshi_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="FAILED",
                source_ready=False,
                window_open=0,
                missing_expired=0,
                settlement_pending=0,
            ),
            "OPERATOR_REVIEW_KALSHI_SOURCE_INTEGRITY_FAILED_NO_TRADING",
        )

    def test_kalshi_verified_source_only_hands_off_to_offline_scoring(self):
        self.assertEqual(
            _kalshi_next_action(
                status="EVIDENCE_PRESENT",
                integrity_status="AVAILABLE",
                source_ready=True,
                window_open=0,
                missing_expired=0,
                settlement_pending=0,
            ),
            "OFFLINE_KALSHI_SHADOW_SCORING_INPUTS_REQUIRED",
        )


if __name__=="__main__":
    unittest.main()
