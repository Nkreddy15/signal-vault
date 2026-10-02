import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.experimental_paper_sandbox import run_once
from signal_vault.paper_credentials import PaperCredentials
from signal_vault.research_universe import ResearchBar

UTC=timezone.utc


class Bars:
    def __init__(self,*args,**kwargs): pass
    def fetch(self,*,start,end,as_of):
        # flat data -> no EMA cross, so sandbox must not submit.
        rows=[]
        for i in range(72):
            s=start.replace(tzinfo=UTC)
            at=s.replace()+__import__("datetime").timedelta(hours=i)
            rows.append(type("B",(),{
                "symbol":"BTC/USD","start":at,
                "open":Decimal("100"),"high":Decimal("101"),
                "low":Decimal("99"),"close":Decimal("100"),
                "volume":Decimal("1"),"source":"fixture"
            })())
        return tuple(rows)


class Reader:
    def __init__(self,*args,**kwargs): pass
    def readiness(self):
        return type("R",(),{"ready":True,"reasons":()})()
    def lookup_order(self,client_id): return None


class Phase152ExperimentalPaperSandboxTests(unittest.TestCase):
    def test_hold_never_reaches_paper_preflight_or_order(self):
        result=run_once(
            strategy_name="generic-ema12x26-v1-predeclared",
            credentials=PaperCredentials("paper-key","paper-secret"),
            now=datetime(2026,10,2,1,5,tzinfo=UTC),
            bars_factory=Bars,
            reader_factory=Reader,
        )
        self.assertEqual(result["status"],"NO_CURRENT_BUY_NO_PAPER_ORDER")
        self.assertFalse(result["paper_post_attempted"])
        self.assertFalse(result["strategy_validated"])
        self.assertFalse(result["independent_prospective_gate_passed"])
        self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_execute_requires_exact_paper_ack_before_any_data(self):
        with self.assertRaises(PermissionError):
            run_once(
                strategy_name="generic-momentum24bar50bps-v1-predeclared",
                credentials=PaperCredentials("paper-key","paper-secret"),
                execute=True,
                acknowledgement="wrong",
                now=datetime(2026,10,2,1,5,tzinfo=UTC),
                bars_factory=Bars,
                reader_factory=Reader,
            )


if __name__=="__main__":
    unittest.main()
