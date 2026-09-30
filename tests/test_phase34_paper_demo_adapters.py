"""Paper/demo execution adapters use non-live hosts and durable journal."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.alpaca_equity_paper_executor import (
    EquityPaperOnceExecutor,build_equity_paper_buy_draft,
)
from signal_vault.kalshi_demo_executor import (
    KalshiDemoOnceExecutor,build_kalshi_demo_bid_draft,
)
from signal_vault.multimarket_execution_journal import MultiMarketExecutionJournal
from signal_vault.paper_order_state import Stage

NOW=datetime(2026,9,30,tzinfo=timezone.utc)
ZERO={"crypto":Decimal("0"),"us_equity":Decimal("0"),
      "kalshi_event_contract":Decimal("0")}

def common():
    return dict(
        exposure_by_lane=ZERO,open_positions=0,
        marked_equity_usd=Decimal("100"),
        daily_anchor_equity_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),operator_halted=False)

class PaperDemoAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"mm.sqlite3"

    def test_equity_paper_fake_post_is_committed_first_and_accepted(self):
        draft=build_equity_paper_buy_draft(
            symbol="AAPL",notional_usd=Decimal("5.00"),
            client_order_id="eq1",**common())
        calls=[]
        def transport(payload,key,secret):
            calls.append((dict(payload),key,secret))
            return {"client_order_id":"eq1","id":"paper-order-1",
                    "status":"accepted","filled_qty":"0","filled_avg_price":None}
        with MultiMarketExecutionJournal(self.path) as journal:
            journal.record_approved_draft(draft,at=NOW)
            ex=EquityPaperOnceExecutor(
                paper_key="paper-key",paper_secret="paper-secret",
                journal=journal,transport=transport)
            self.assertEqual(ex.submit_once(draft,at=NOW),Stage.BROKER_ACCEPTED)
            self.assertEqual(len(calls),1)

    def test_equity_transport_failure_becomes_unknown_and_blocks_second_market(self):
        equity=build_equity_paper_buy_draft(
            symbol="SPY",notional_usd=Decimal("5.00"),
            client_order_id="eq2",**common())
        kalshi=build_kalshi_demo_bid_draft(
            ticker="KXTEST",price=Decimal("0.5000"),count=Decimal("2.00"),
            client_order_id="k2",**common())
        with MultiMarketExecutionJournal(self.path) as journal:
            journal.record_approved_draft(equity,at=NOW)
            journal.record_approved_draft(kalshi,at=NOW)
            ex=EquityPaperOnceExecutor(
                paper_key="paper-key",paper_secret="paper-secret",
                journal=journal,transport=lambda *args:(_ for _ in ()).throw(TimeoutError()))
            self.assertEqual(ex.submit_once(equity,at=NOW),Stage.UNKNOWN_RESULT)
            demo=KalshiDemoOnceExecutor(
                api_key_id="demo-key",signer=lambda *args:"sig",
                journal=journal,
                transport=lambda *args:{"order_id":"demo-order"})
            with self.assertRaises(PermissionError):
                demo.submit_once(kalshi,at=NOW)

    def test_kalshi_demo_fake_post_is_accepted_not_filled(self):
        draft=build_kalshi_demo_bid_draft(
            ticker="KXBTC-TEST",price=Decimal("0.2500"),count=Decimal("4.00"),
            client_order_id="k1",**common())
        calls=[]
        def transport(payload,key,signer):
            calls.append((dict(payload),key,signer("1","POST","/x")))
            return {"order":{"order_id":"demo-order-1","remaining_count":"4.00"}}
        with MultiMarketExecutionJournal(self.path) as journal:
            journal.record_approved_draft(draft,at=NOW)
            demo=KalshiDemoOnceExecutor(
                api_key_id="demo-key",signer=lambda *args:"signature",
                journal=journal,transport=transport)
            self.assertEqual(demo.submit_once(draft,at=NOW),Stage.BROKER_ACCEPTED)
            self.assertEqual(len(calls),1)

    def test_risk_and_payload_bounds_fail_closed_before_network(self):
        with self.assertRaises(ValueError):
            build_equity_paper_buy_draft(
                symbol="NOT-APPROVED",notional_usd=Decimal("5.00"),
                client_order_id="bad",**common())
        with self.assertRaises(ValueError):
            build_kalshi_demo_bid_draft(
                ticker="KXTEST",price=Decimal("1.0000"),count=Decimal("1.00"),
                client_order_id="bad2",**common())

if __name__=="__main__":
    unittest.main()
