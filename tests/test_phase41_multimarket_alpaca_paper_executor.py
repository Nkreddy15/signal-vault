import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.cross_market_risk import assess_new_risk
from signal_vault.multimarket_alpaca_paper_executor import (
    MultiMarketAlpacaPaperOnceExecutor,
)
from signal_vault.multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from signal_vault.multimarket_paper_router import (
    CRYPTO_PAPER_ACK,
    EQUITY_PAPER_ACK,
)
from signal_vault.paper_order_state import Stage

NOW=datetime(2026,9,30,19,0,tzinfo=timezone.utc)


def risk(lane):
    return assess_new_risk(
        lane=lane,
        proposed_max_loss_usd=Decimal("5"),
        exposure_by_lane={},
        open_positions=0,
        marked_equity_usd=Decimal("100"),
        daily_anchor_equity_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        operator_halted=False,
    )


class MultiMarketAlpacaPaperExecutorTests(unittest.TestCase):
    def test_equity_paper_submission_commits_before_single_post(self):
        calls=[]
        draft=MultiMarketOrderDraft(
            "eq1","us_equity","SPY",Decimal("5"),
            {
                "symbol":"SPY","side":"buy","type":"market","time_in_force":"day",
                "notional":"5","client_order_id":"eq1",
            },
        )
        with MultiMarketExecutionJournal(":memory:") as journal:
            journal.record_approved_draft(draft,at=NOW)
            def fake(payload,key,secret):
                self.assertEqual(journal.get_state("eq1").stage,Stage.SUBMISSION_PENDING)
                calls.append(dict(payload))
                return {
                    "id":"alpaca-paper-1",
                    "client_order_id":"eq1",
                    "status":"accepted",
                    "filled_qty":"0",
                    "filled_avg_price":None,
                }
            executor=MultiMarketAlpacaPaperOnceExecutor(
                paper_key="paper-key",
                paper_secret="paper-secret",
                journal=journal,
                transport=fake,
            )
            result=executor.submit_once(
                draft,
                risk_assessment=risk("us_equity"),
                acknowledgement=EQUITY_PAPER_ACK,
                at=NOW,
            )
            self.assertEqual(result.stage,Stage.BROKER_ACCEPTED)
            self.assertEqual(len(calls),1)
            with self.assertRaises(ValueError):
                executor.submit_once(
                    draft,
                    risk_assessment=risk("us_equity"),
                    acknowledgement=EQUITY_PAPER_ACK,
                    at=NOW,
                )
            self.assertEqual(len(calls),1)

    def test_crypto_timeout_becomes_unknown_and_never_blind_retries(self):
        calls=[]
        draft=MultiMarketOrderDraft(
            "cr1","crypto","BTC/USD",Decimal("5"),
            {
                "symbol":"BTC/USD","side":"buy","type":"market","time_in_force":"gtc",
                "notional":"5","client_order_id":"cr1",
            },
        )
        with MultiMarketExecutionJournal(":memory:") as journal:
            journal.record_approved_draft(draft,at=NOW)
            def timeout(*_):
                calls.append(1)
                raise TimeoutError("mock")
            executor=MultiMarketAlpacaPaperOnceExecutor(
                paper_key="paper-key",
                paper_secret="paper-secret",
                journal=journal,
                transport=timeout,
            )
            result=executor.submit_once(
                draft,
                risk_assessment=risk("crypto"),
                acknowledgement=CRYPTO_PAPER_ACK,
                at=NOW,
            )
            self.assertEqual(result.stage,Stage.UNKNOWN_RESULT)
            self.assertEqual(len(calls),1)
            self.assertTrue(journal.has_unresolved())
            with self.assertRaises(ValueError):
                executor.submit_once(
                    draft,
                    risk_assessment=risk("crypto"),
                    acknowledgement=CRYPTO_PAPER_ACK,
                    at=NOW,
                )
            self.assertEqual(len(calls),1)

    def test_wrong_ack_or_blocked_risk_never_reaches_transport(self):
        calls=[]
        draft=MultiMarketOrderDraft(
            "eq2","us_equity","AAPL",Decimal("5"),
            {
                "symbol":"AAPL","side":"buy","type":"market","time_in_force":"day",
                "notional":"5","client_order_id":"eq2",
            },
        )
        blocked=assess_new_risk(
            lane="us_equity",
            proposed_max_loss_usd=Decimal("5"),
            exposure_by_lane={},
            open_positions=0,
            marked_equity_usd=Decimal("100"),
            daily_anchor_equity_usd=Decimal("100"),
            peak_equity_usd=Decimal("100"),
            operator_halted=True,
        )
        with MultiMarketExecutionJournal(":memory:") as journal:
            journal.record_approved_draft(draft,at=NOW)
            executor=MultiMarketAlpacaPaperOnceExecutor(
                paper_key="paper-key",
                paper_secret="paper-secret",
                journal=journal,
                transport=lambda *_: calls.append(1),
            )
            with self.assertRaises(PermissionError):
                executor.submit_once(
                    draft,
                    risk_assessment=risk("us_equity"),
                    acknowledgement=CRYPTO_PAPER_ACK,
                    at=NOW,
                )
            with self.assertRaises(PermissionError):
                executor.submit_once(
                    draft,
                    risk_assessment=blocked,
                    acknowledgement=EQUITY_PAPER_ACK,
                    at=NOW,
                )
            self.assertFalse(calls)

    def test_kalshi_draft_cannot_enter_alpaca_executor(self):
        draft=MultiMarketOrderDraft(
            "k1","kalshi_event_contract","TEST",Decimal("5"),
            {
                "ticker":"TEST","side":"yes","action":"buy","count":"5",
                "client_order_id":"k1",
            },
        )
        with MultiMarketExecutionJournal(":memory:") as journal:
            journal.record_approved_draft(draft,at=NOW)
            executor=MultiMarketAlpacaPaperOnceExecutor(
                paper_key="paper-key",
                paper_secret="paper-secret",
                journal=journal,
                transport=lambda *_: {},
            )
            with self.assertRaises(PermissionError):
                executor.submit_once(
                    draft,
                    risk_assessment=risk("kalshi_event_contract"),
                    acknowledgement="I_ACKNOWLEDGE_KALSHI_DEMO_ORDERS_ONLY",
                    at=NOW,
                )

if __name__=="__main__":
    unittest.main()
