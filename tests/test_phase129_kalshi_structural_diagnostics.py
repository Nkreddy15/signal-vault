import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.kalshi_cloud_sidecar import (
    ACTIVATION_ENV,
    ACTIVATION_VALUE,
    ROOT_ENV,
    run_kalshi_sidecar_once,
)


UTC=timezone.utc
NOW=datetime(2026,10,1,18,0,tzinfo=UTC)


class ResponseClient:
    def __init__(self,response):
        self.response=response

    def live_public_events(self,**kwargs):
        del kwargs
        return self.response


class KalshiStructuralDiagnosticTests(unittest.TestCase):
    def _run(self,response):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            root.chmod(0o700)
            return run_kalshi_sidecar_once(
                env={
                    ACTIVATION_ENV:ACTIVATION_VALUE,
                    ROOT_ENV:str(root),
                },
                now=NOW,
                client_factory=lambda:ResponseClient(response),
            )

    def test_event_discovery_without_events_has_specific_fail_closed_code(self):
        result=self._run({"markets":[],"cursor":None})
        self.assertEqual(result["status"],"PLANNING_BLOCKED_FAIL_CLOSED")
        self.assertEqual(
            result["planning_failure_code"],
            "MALFORMED_PUBLIC_EVENT_DISCOVERY",
        )
        self.assertFalse(result["filesystem_writes"])
        self.assertEqual(result["network_method_allowlist"],["GET"])
        self.assertEqual(result["credentials_accessed"],"NONE")
        self.assertEqual(result["demo_order_submission"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")

    def test_event_without_nested_markets_has_specific_fail_closed_code(self):
        result=self._run({
            "events":[{"event_ticker":"EVENT-01"}],
            "cursor":None,
        })
        self.assertEqual(
            result["planning_failure_code"],
            "PUBLIC_EVENT_MISSING_NESTED_MARKETS",
        )
        self.assertFalse(result["filesystem_writes"])

    def test_event_identity_mismatch_has_specific_fail_closed_code(self):
        result=self._run({
            "events":[{
                "event_ticker":"EVENT-01",
                "markets":[{
                    "ticker":"MARKET-01",
                    "event_ticker":"EVENT-02",
                }],
            }],
            "cursor":None,
        })
        self.assertEqual(
            result["planning_failure_code"],
            "NESTED_MARKET_EVENT_IDENTITY_MISMATCH",
        )
        self.assertFalse(result["filesystem_writes"])


if __name__=="__main__":
    unittest.main()
