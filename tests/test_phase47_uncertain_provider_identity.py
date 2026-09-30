import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.cross_market_risk import assess_new_risk
from signal_vault.kalshi_demo_executor import KalshiDemoOnceExecutor
from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from signal_vault.multimarket_paper_router import KALSHI_DEMO_ACK
from signal_vault.paper_order_state import PaperOrderState, Stage

NOW=datetime(2026,9,30,19,0,tzinfo=timezone.utc)


def risk():
    return assess_new_risk(
        lane="kalshi_event_contract",
        proposed_max_loss_usd=Decimal("5"),
        exposure_by_lane={},
        open_positions=0,
        marked_equity_usd=Decimal("100"),
        daily_anchor_equity_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        operator_halted=False,
    )


def draft():
    return MultiMarketOrderDraft(
        "k-ident","kalshi_event_contract","TEST-MARKET",Decimal("5"),
        {
            "ticker":"TEST-MARKET","side":"bid","count":"5","price":"0.2500",
            "time_in_force":"good_till_canceled",
            "self_trade_prevention_type":"taker_at_cross",
            "client_order_id":"k-ident",
        },
    )


class UncertainProviderIdentityTests(unittest.TestCase):
    def test_state_identity_attachment_does_not_resolve_unknown(self):
        state=PaperOrderState("x").start_submission().mark_transport_uncertain()
        retained=state.attach_uncertain_broker_identity("provider-1")
        self.assertEqual(retained.stage,Stage.UNKNOWN_RESULT)
        self.assertEqual(retained.broker_order_id,"provider-1")
        self.assertIsNone(retained.provider_status)
        self.assertEqual(retained.cumulative_filled_qty,Decimal("0"))
        self.assertIsNone(retained.filled_avg_price)
        self.assertTrue(retained.blocks_new_execution)
        self.assertEqual(
            retained.attach_uncertain_broker_identity("provider-1"),
            retained,
        )
        with self.assertRaises(ValueError):
            retained.attach_uncertain_broker_identity("provider-2")

    def test_journal_persists_identity_without_unblocking_execution(self):
        d=draft()
        with MultiMarketExecutionJournal(":memory:") as journal:
            journal.record_approved_draft(d,at=NOW)
            journal.begin_submission(d,at=NOW)
            journal.mark_unknown(d.client_order_id,at=NOW)
            state=journal.attach_uncertain_provider_identity(
                d.client_order_id,"provider-1",at=NOW
            )
            self.assertEqual(state.stage,Stage.UNKNOWN_RESULT)
            self.assertEqual(state.broker_order_id,"provider-1")
            self.assertTrue(journal.has_unresolved())

    def test_immediate_kalshi_fill_retains_provider_id_but_no_fake_fill_price(self):
        d=draft()
        with MultiMarketExecutionJournal(":memory:") as journal:
            journal.record_approved_draft(d,at=NOW)
            executor=KalshiDemoOnceExecutor(
                key_id="demo-key",
                signer=lambda _:"sig",
                journal=journal,
                transport=lambda *_:{
                    "order_id":"kalshi-order-77",
                    "client_order_id":"k-ident",
                    "fill_count":"1.00",
                    "remaining_count":"4.00",
                    "ts_ms":1700000000000,
                },
            )
            result=executor.submit_once(
                d,risk_assessment=risk(),
                acknowledgement=KALSHI_DEMO_ACK,
                timestamp_ms=1700000000000,
                at=NOW,
            )
            self.assertEqual(result.stage,Stage.UNKNOWN_RESULT)
            self.assertEqual(result.state.broker_order_id,"kalshi-order-77")
            self.assertIsNone(result.state.provider_status)
            self.assertEqual(result.state.cumulative_filled_qty,Decimal("0"))
            self.assertIsNone(result.state.filled_avg_price)
            self.assertTrue(result.immediate_fill_requires_reconciliation)


if __name__=="__main__":
    unittest.main()
