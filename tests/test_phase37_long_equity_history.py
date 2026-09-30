import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.ci_long_equity_history import (
    APPROVAL,
    execute_long_equity_history,
    resolve_long_equity_plan,
)

NOW=datetime(2026,9,30,18,0,tzinfo=timezone.utc)
BASE={
    "GITHUB_ACTIONS":"true",
    "GITHUB_EVENT_NAME":"workflow_dispatch",
    "GITHUB_REPOSITORY":"Nkreddy15/signal-vault",
    "GITHUB_REF":"refs/heads/main",
    "SIGNAL_VAULT_LONG_EQUITY_READ_APPROVED":APPROVAL,
    "SIGNAL_VAULT_LONG_EQUITY_START_DATE":"2026-01-05",
    "SIGNAL_VAULT_LONG_EQUITY_END_DATE_EXCLUSIVE":"2026-09-01",
}

class LongEquityHistoryTests(unittest.TestCase):
    def test_manual_main_only_plan_is_multi_chunk_and_no_order(self):
        plan=resolve_long_equity_plan(env=BASE,as_of=NOW)
        self.assertGreater(plan["chunk_count"],1)
        self.assertEqual(plan["broker_order_submission"],"DISABLED")
        self.assertEqual(plan["live_trading"],"UNAVAILABLE")

    def test_orchestrator_uses_separate_folders_and_manifest(self):
        seen=[]
        def fake_runner(*,env,as_of,output_folder):
            seen.append((dict(env),Path(output_folder)))
            Path(output_folder).mkdir(mode=0o700)
            report=(Path(output_folder)/"offline_equity_research.json")
            report.write_text("{}")
            report.chmod(0o600)
            return {
                "completed_exchange_sessions":10,
                "historical_bars_per_asset":60,
                "report_sha256":"a"*64,
                "broker_order_submission":"DISABLED",
            }
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"long"
            result=execute_long_equity_history(
                env=BASE,as_of=NOW,output_root=root,runner=fake_runner
            )
            self.assertEqual(result["chunk_count"],len(seen))
            self.assertGreater(len(seen),1)
            self.assertEqual(len({p for _,p in seen}),len(seen))
            self.assertTrue((root/"long_horizon_manifest.json").is_file())
            self.assertEqual(result["broker_order_submission"],"DISABLED")
            self.assertEqual(result["live_trading"],"UNAVAILABLE")

    def test_wrong_context_or_approval_fails_before_runner(self):
        for change in (
            {"GITHUB_REF":"refs/heads/feature"},
            {"GITHUB_EVENT_NAME":"push"},
            {"SIGNAL_VAULT_LONG_EQUITY_READ_APPROVED":"wrong"},
        ):
            with self.subTest(change=change), self.assertRaises(PermissionError):
                resolve_long_equity_plan(env={**BASE,**change},as_of=NOW)

if __name__=="__main__":
    unittest.main()
