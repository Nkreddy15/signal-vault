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
from signal_vault.paper_order_state import Stage

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


def draft(client_id="k1",count="5"):
    return MultiMarketOrderDraft(
        client_id,"kalshi_event_contract","TEST-MARKET",Decimal("5"),
        {
            "ticker":"TEST-MARKET",
            "side":"bid",
            "count":count,
            "price":"0.2500",
            "time_in_force":"good_till_canceled",
            "self_trade_prevention_type":"taker_at_cross",
            "client_order_id":client_id,
        },
    )


class KalshiDemoOnceExecutorTests(unittest.TestCase):
    def test_zero_fill_create_response_is_recorded_accepted_once(self):
        calls=[]
        with MultiMarketExecutionJournal(":memory:") as journal:
            d=draft()
            journal.record_approved_draft(d,at=NOW)
            def fake(url,headers,payload):
                self.assertEqual(journal.get_state("k1").stage,Stage.SUBMISSION_PENDING)
                calls.append((url,dict(headers),dict(payload)))
                return {
                    "order_id":"demo-order-1",
                    "client_order_id":"k1",
                    "fill_count":"0.00",
                    "remaining_count":"5.00",
                    "ts_ms":1700000000123,
                }
            executor=KalshiDemoOnceExecutor(
                key_id="demo-key",
                signer=lambda text:"signature-for-"+text,
                journal=journal,
                transport=fake,
            )
            result=executor.submit_once(
                d,
                risk_assessment=risk(),
                acknowledgement=KALSHI_DEMO_ACK,
                timestamp_ms=1700000000123,
                at=NOW,
            )
            self.assertEqual(result.stage,Stage.BROKER_ACCEPTED)
            self.assertFalse(result.immediate_fill_requires_reconciliation)
            self.assertEqual(len(calls),1)
            self.assertIn("external-api.demo.kalshi.co",calls[0][0])
            with self.assertRaises(ValueError):
                executor.submit_once(
                    d,
                    risk_assessment=risk(),
                    acknowledgement=KALSHI_DEMO_ACK,
                    timestamp_ms=1700000000124,
                    at=NOW,
                )
            self.assertEqual(len(calls),1)

    def test_immediate_fill_is_unknown_until_authoritative_reconciliation(self):
        with MultiMarketExecutionJournal(":memory:") as journal:
            d=draft()
            journal.record_approved_draft(d,at=NOW)
            executor=KalshiDemoOnceExecutor(
                key_id="demo-key",
                signer=lambda _:"sig",
                journal=journal,
                transport=lambda *_:{
                    "order_id":"demo-order-2",
                    "client_order_id":"k1",
                    "fill_count":"2.00",
                    "remaining_count":"3.00",
                    "ts_ms":1700000000123,
                },
            )
            result=executor.submit_once(
                d,risk_assessment=risk(),
                acknowledgement=KALSHI_DEMO_ACK,
                timestamp_ms=1700000000123,at=NOW,
            )
            self.assertEqual(result.stage,Stage.UNKNOWN_RESULT)
            self.assertTrue(result.immediate_fill_requires_reconciliation)
            self.assertTrue(journal.has_unresolved())

    def test_timeout_or_malformed_count_becomes_unknown_without_retry(self):
        for response in ("timeout","bad-count"):
            with self.subTest(response=response), MultiMarketExecutionJournal(":memory:") as journal:
                d=draft()
                journal.record_approved_draft(d,at=NOW)
                calls=[]
                def fake(*_):
                    calls.append(1)
                    if response=="timeout":
                        raise TimeoutError("mock")
                    return {
                        "order_id":"demo-order-3",
                        "client_order_id":"k1",
                        "fill_count":"0",
                        "remaining_count":"4",
                        "ts_ms":1,
                    }
                executor=KalshiDemoOnceExecutor(
                    key_id="demo-key",signer=lambda _:"sig",
                    journal=journal,transport=fake,
                )
                result=executor.submit_once(
                    d,risk_assessment=risk(),acknowledgement=KALSHI_DEMO_ACK,
                    timestamp_ms=1,at=NOW,
                )
                self.assertEqual(result.stage,Stage.UNKNOWN_RESULT)
                self.assertEqual(len(calls),1)
                with self.assertRaises(ValueError):
                    executor.submit_once(
                        d,risk_assessment=risk(),
                        acknowledgement=KALSHI_DEMO_ACK,
                        timestamp_ms=2,at=NOW,
                    )
                self.assertEqual(len(calls),1)

    def test_wrong_ack_or_blocked_risk_never_posts(self):
        blocked=assess_new_risk(
            lane="kalshi_event_contract",
            proposed_max_loss_usd=Decimal("5"),
            exposure_by_lane={},
            open_positions=0,
            marked_equity_usd=Decimal("100"),
            daily_anchor_equity_usd=Decimal("100"),
            peak_equity_usd=Decimal("100"),
            operator_halted=True,
        )
        for receipt,ack in ((risk(),"live"),(blocked,KALSHI_DEMO_ACK)):
            with self.subTest(ack=ack), MultiMarketExecutionJournal(":memory:") as journal:
                d=draft()
                journal.record_approved_draft(d,at=NOW)
                calls=[]
                executor=KalshiDemoOnceExecutor(
                    key_id="demo-key",signer=lambda _:"sig",
                    journal=journal,transport=lambda *_:calls.append(1),
                )
                with self.assertRaises(PermissionError):
                    executor.submit_once(
                        d,risk_assessment=receipt,acknowledgement=ack,
                        timestamp_ms=1,at=NOW,
                    )
                self.assertFalse(calls)
                with self.assertRaises(KeyError):
                    journal.get_state("k1")


if __name__=="__main__":
    unittest.main()
