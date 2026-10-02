import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.experimental_paper_readiness import (
    build_readiness_report,
    _write_once,
)
from signal_vault.paper_credentials import PaperCredentials

UTC=timezone.utc


class Bar:
    def __init__(self,start,close):
        self.symbol="BTC/USD"
        self.start=start
        self.open=close
        self.high=close+Decimal("1")
        self.low=close-Decimal("1")
        self.close=close
        self.volume=Decimal("1")
        self.source="fixture"


class BarsFactory:
    prices=None
    def __init__(self,*args,**kwargs): pass
    def fetch(self,*,start,end,as_of):
        return tuple(
            Bar(start+timedelta(hours=i),price)
            for i,price in enumerate(self.prices)
        )


class ReadyReader:
    def __init__(self,*args,**kwargs): pass
    def readiness(self):
        return type("R",(),{
            "ready":True,
            "reasons":(),
            "logical_cap_usd":Decimal("100"),
        })()


class BlockedReader:
    def __init__(self,*args,**kwargs): pass
    def readiness(self):
        return type("R",(),{
            "ready":False,
            "reasons":("account has pre-existing positions; cannot assume empty test portfolio",),
            "logical_cap_usd":Decimal("100"),
        })()


class Phase156ExperimentalPaperReadinessTests(unittest.TestCase):
    def test_single_momentum_buy_is_surfaced_but_not_authorized(self):
        BarsFactory.prices=(
            [Decimal("100")]*48+
            [Decimal("100")+Decimal(i+1)/Decimal("10") for i in range(24)]
        )
        out=build_readiness_report(
            credentials=PaperCredentials("paper-key","paper-secret"),
            now=datetime(2026,10,2,4,5,tzinfo=UTC),
            bars_factory=BarsFactory,
            reader_factory=ReadyReader,
        )
        self.assertEqual(out["status"],"READY_FOR_EXPLICIT_EXPERIMENTAL_PAPER_REVIEW")
        self.assertEqual(
            out["selected_strategy_for_operator_review"],
            "generic-momentum24bar50bps-v1-predeclared",
        )
        self.assertEqual(
            out["strategy_actions"]["generic-momentum24bar50bps-v1-predeclared"]["hypothetical_action"],
            "buy",
        )
        self.assertFalse(out["actions_are_order_authority"])
        self.assertEqual(out["paper_order_submission"],"DISABLED")
        self.assertEqual(out["live_trading"],"UNAVAILABLE")

    def test_account_block_wins_even_when_signal_exists(self):
        BarsFactory.prices=(
            [Decimal("100")]*48+
            [Decimal("100")+Decimal(i+1)/Decimal("10") for i in range(24)]
        )
        out=build_readiness_report(
            credentials=PaperCredentials("paper-key","paper-secret"),
            now=datetime(2026,10,2,4,5,tzinfo=UTC),
            bars_factory=BarsFactory,
            reader_factory=BlockedReader,
        )
        self.assertEqual(out["status"],"BLOCKED_PAPER_ACCOUNT_PREFLIGHT")
        self.assertFalse(out["paper_account_ready"])
        self.assertIsNone(out["selected_strategy_for_operator_review"])

    def test_receipt_is_create_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"readiness.json"
            _write_once(p,{"kind":"fixture","paper_order_submission":"DISABLED"})
            self.assertTrue(p.exists())
            with self.assertRaises(ValueError):
                _write_once(p,{"kind":"overwrite"})


if __name__=="__main__":
    unittest.main()
