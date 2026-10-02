import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from signal_vault import railway_all_markets_research_cron as cron


UTC=timezone.utc


class Phase153ShadowNamespaceTests(unittest.TestCase):
    def test_cron_reads_shadow_from_exact_six_crypto_child(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            seen=[]

            def core_runner(**kwargs):
                return {
                    "crypto_btc_status":"SAFE_NO_NEW_OBSERVATION",
                    "equity_status":"NO_DUE_CORE_HOUR",
                    "btc_evidence_changed_during_equity_stage":False,
                    "broker_order_submission":"DISABLED",
                    "paper_order_submission":"DISABLED",
                    "live_order_submission":"DISABLED",
                }

            def kalshi_runner(**kwargs):
                return {
                    "status":"NO_DUE_KALSHI_CAPTURE",
                    "demo_order_submission":"DISABLED",
                    "live_order_submission":"DISABLED",
                }

            def shadow_reader(*,root):
                seen.append(root)
                return {
                    "kind":"OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY",
                    "latest_newly_observed_UTC_close":"2026-10-02T00:00:00+00:00",
                    "shadow_payload_sha256":"a"*64,
                    "predeclared_flat_and_held_hypothetical_decisions":{
                        "BTC/USD":{
                            "generic-ema12x26-v1-predeclared":{
                                "flat":{"hypothetical_action":"buy"}
                            }
                        }
                    },
                }

            with (
                patch.object(
                    cron,"fingerprint_btc_evidence_tree",
                    return_value={"tree_sha256":"same","file_count":1},
                ),
                patch.object(
                    cron,"all_market_forward_status",
                    return_value={"kind":"fixture"},
                ),
                patch.object(
                    cron,"build_dashboard_snapshot",
                    return_value={"strategy_research":{}},
                ),
                patch.object(
                    cron,"archive_dashboard_snapshot",
                    return_value=SimpleNamespace(name="dashboard.json"),
                ),
                patch.object(
                    cron,"inspect_six_crypto_shadow",
                    side_effect=shadow_reader,
                ),
            ):
                out=cron.combined_all_markets_once(
                    now=datetime(2026,10,2,0,7,tzinfo=UTC),
                    environ={},
                    btc_root=root,
                    core_runner=core_runner,
                    kalshi_runner=kalshi_runner,
                )

            self.assertEqual(seen,[root/cron.SIX_CRYPTO_BASENAME])
            self.assertEqual(out["current_btc_shadow_status"],"AVAILABLE")
            self.assertEqual(
                out["current_btc_flat_actions"]["generic-ema12x26-v1-predeclared"],
                "buy",
            )
            self.assertFalse(out["current_btc_actions_are_order_authority"])


if __name__=="__main__":
    unittest.main()
