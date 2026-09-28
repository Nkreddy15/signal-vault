import io
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.paper_runtime import PaperCycleResult
from signal_vault.safe_log import emit_cycle_log


class SafeLogTests(unittest.TestCase):
    def test_raw_explanation_and_provider_payload_do_not_enter_logs(self):
        output=io.StringIO()
        result=PaperCycleResult("BLOCKED_PROVIDER_DRIFT", "account_id=SECRET token=LEAK")
        logical={"cash_usd":Decimal("100"),"btc_qty":Decimal("0"),
                 "realized_pnl_usd":Decimal("0"),"fees_usd_equiv":Decimal("0")}
        emit_cycle_log(result=result, logical=logical, operator_halted=False,
                       at=datetime(2026,9,28,tzinfo=timezone.utc), stream=output)
        text=output.getvalue()
        self.assertIn('"state":"BLOCKED_PROVIDER_DRIFT"', text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("account_id", text)
