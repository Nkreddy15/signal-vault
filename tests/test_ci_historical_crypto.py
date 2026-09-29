"""Human-only GitHub Actions historical DATA GET security boundary tests."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

from signal_vault.ci_historical_crypto import (
    APPROVAL_ENV,KEY_ENV,SECRET_ENV,
    ci_entry, main, resolve_manual_ci_configuration,
)

APPROVED={
    "GITHUB_ACTIONS":"true",
    "GITHUB_EVENT_NAME":"workflow_dispatch",
    "GITHUB_REPOSITORY":"Nkreddy15/signal-vault",
    "GITHUB_REF":"refs/heads/main",
    APPROVAL_ENV:"HISTORICAL_CRYPTO_DATA_GET_ONLY",
    "SIGNAL_VAULT_RESEARCH_SYMBOLS":"BTC/USD ETH/USD",
    "SIGNAL_VAULT_RESEARCH_START_UTC":"2026-07-01T00:00:00Z",
    "SIGNAL_VAULT_RESEARCH_END_UTC":"2026-09-01T00:00:00Z",
    KEY_ENV:"PRIVATE_GH_ACTIONS_SENTINEL_KEY",
    SECRET_ENV:"PRIVATE_GH_ACTIONS_SENTINEL_SECRET",
}


class ManualGithubHistoricalGetTests(unittest.TestCase):
    def test_manual_main_only_private_repo_data_only_approval(self):
        plan=resolve_manual_ci_configuration(env=APPROVED)
        self.assertEqual(plan["symbols"],("BTC/USD","ETH/USD"))
        self.assertEqual(plan["plan"]["credential_access"],"NONE")
        self.assertEqual(plan["plan"]["requests_triggered"],0)
        self.assertNotIn("PRIVATE_GH_ACTIONS",json.dumps(plan["plan"]))
        for change in (
            {"GITHUB_EVENT_NAME":"pull_request"},
            {"GITHUB_REF":"refs/pull/11/merge"},
            {"GITHUB_REPOSITORY":"other/fork"},
            {"GITHUB_ACTIONS":"false"},
            {APPROVAL_ENV:"AUTOMATIC_TRADE"},
            {"ALPACA_LIVE_KEY_ID":"unsafe"},
            {"SIGNAL_VAULT_ENABLE_PAPER_ORDERS":"true"},
        ):
            with self.subTest(change=change),self.assertRaises(PermissionError):
                resolve_manual_ci_configuration(env={**APPROVED,**change})

    def test_requires_both_separate_encrypted_research_secrets_not_forward_keys(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("signal_vault.ci_historical_crypto.OUTPUT",Path(d)/"history"):
                for removed in (KEY_ENV,SECRET_ENV):
                    env={k:v for k,v in APPROVED.items() if k!=removed}
                    with self.subTest(removed=removed),self.assertRaises(PermissionError):
                        ci_entry(env=env,downloader=lambda **kwargs:self.fail(
                            "must not invoke historical provider without secrets"))
                self.assertFalse((Path(d)/"history").exists())

    def test_no_secret_values_in_outputs_or_paths_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"history"
            captured=[]
            def only_fake_downloader(**kw):
                captured.append(kw)
                return {
                    "broker_order_submission":"DISABLED",
                    "credential_values_in_output":False,
                    "results":[{"archive_basename":"historical-crypto-dummy.json"}],
                }
            with patch("signal_vault.ci_historical_crypto.OUTPUT",out):
                receipt=ci_entry(env=APPROVED,downloader=only_fake_downloader)
            self.assertEqual(out.stat().st_mode & 0o777,0o700)
            self.assertEqual(captured[0]["key_id"],APPROVED[KEY_ENV])
            self.assertEqual(captured[0]["secret"],APPROVED[SECRET_ENV])
            self.assertNotIn("PRIVATE_GH_ACTIONS",json.dumps(receipt))
            self.assertNotIn("PRIVATE_GH_ACTIONS",str(out))

    def test_rejects_bad_history_context_and_conflicting_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"history"
            out.mkdir(mode=0o700)
            (out/"not-cleared.txt").write_text("original")
            with patch("signal_vault.ci_historical_crypto.OUTPUT",out):
                with self.assertRaises(ValueError):
                    ci_entry(env=APPROVED,downloader=lambda **kw:self.fail(
                        "no historical GET with conflicting prior run output"))
            self.assertEqual((out/"not-cleared.txt").read_text(),"original")
        with self.assertRaises(ValueError):
            resolve_manual_ci_configuration(
                env={**APPROVED,"SIGNAL_VAULT_RESEARCH_SYMBOLS":"BTC/USD ../ETH"})
        with self.assertRaises(ValueError):
            resolve_manual_ci_configuration(
                env={**APPROVED,"SIGNAL_VAULT_RESEARCH_END_UTC":
                     "2030-09-01T00:00:00Z"})

    def test_failure_output_discloses_class_only_without_user_secrets(self):
        with patch.dict("os.environ",{**APPROVED,"GITHUB_REF":"refs/heads/attack"},
                        clear=True):
            dest=io.StringIO()
            with redirect_stdout(dest):
                self.assertEqual(main(),2)
        output=dest.getvalue()
        self.assertNotIn("PRIVATE_GH_ACTIONS",output)
        self.assertEqual(json.loads(output)["broker_order_submission"],"DISABLED")


if __name__=="__main__":
    unittest.main()
