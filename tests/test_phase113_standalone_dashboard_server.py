import base64
import http.client
import tempfile
import threading
import unittest
from pathlib import Path

from signal_vault.all_market_dashboard import KIND
from signal_vault.dashboard_server import create_server
from signal_vault.dashboard_snapshot_archive import archive_dashboard_snapshot


TOKEN="t"*40


def auth():
    raw=base64.b64encode(f"operator:{TOKEN}".encode()).decode()
    return {"Authorization":"Basic "+raw}


class DashboardServerTests(unittest.TestCase):
    def make_root(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/"forward"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        archive_dashboard_snapshot({
            "kind":KIND,
            "checked_at_utc":"2026-10-01T05:07:00+00:00",
            "lanes":{
                "six_crypto":{
                    "prospective_source_hours":19,
                    "fully_scored_outcomes":18,
                    "source_hours_remaining":150,
                    "scored_outcomes_remaining":150,
                    "next_action":"CONTINUE_UNATTENDED_FORWARD_COLLECTION",
                },
                "us_equity":{
                    "session_plans":1,
                    "core_hour_receipts":0,
                    "session_plans_remaining":9,
                    "core_hour_receipts_remaining":60,
                    "capture_windows_open":0,
                    "next_action":"CONTINUE_UNATTENDED_STOCK_FORWARD_COLLECTION",
                },
                "kalshi":{
                    "plan_present":True,
                    "planned_markets":22,
                    "decision_snapshots":0,
                    "settlements":0,
                    "decision_snapshots_remaining":40,
                    "settlements_remaining":20,
                    "next_action":"CONTINUE_UNATTENDED_KALSHI_FORWARD_COLLECTION",
                },
            },
            "paper_runway_blockers":["SIX_CRYPTO_FROZEN_FORWARD_REVIEW_WINDOW_INCOMPLETE"],
            "all_forward_stages_complete":False,
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
            "network_requests":"NONE",
            "credential_access":"NONE",
        },base=root)
        return root

    def request(self,server,path,headers=None,method="GET"):
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        conn=http.client.HTTPConnection("127.0.0.1",server.server_address[1],timeout=2)
        self.addCleanup(conn.close)
        conn.request(method,path,headers=headers or {})
        response=conn.getresponse()
        return response.status,response.read(),dict(response.getheaders())

    def test_authenticated_html_and_json_are_read_only(self):
        root=self.make_root()
        server=create_server(forward_root=root,token=TOKEN,port=0)
        status,body,headers=self.request(server,"/",auth())
        self.assertEqual(status,200)
        self.assertIn(b"Six Crypto",body)
        self.assertIn(b"US Equities",body)
        self.assertIn(b"Kalshi",body)
        self.assertEqual(headers["Cache-Control"],"no-store")

        server2=create_server(forward_root=root,token=TOKEN,port=0)
        status,body,_=self.request(server2,"/api/status",auth())
        self.assertEqual(status,200)
        self.assertIn(b'"paper_order_submission":"DISABLED"',body)
        self.assertIn(b'"live_trading":"UNAVAILABLE"',body)

    def test_authentication_and_mutation_methods_fail_closed(self):
        root=self.make_root()
        server=create_server(forward_root=root,token=TOKEN,port=0)
        status,_,headers=self.request(server,"/")
        self.assertEqual(status,401)
        self.assertIn("WWW-Authenticate",headers)

        server2=create_server(forward_root=root,token=TOKEN,port=0)
        status,body,_=self.request(server2,"/",auth(),method="POST")
        self.assertEqual(status,405)
        self.assertIn(b"Read-only dashboard",body)

    def test_remote_bind_and_short_token_are_rejected(self):
        root=self.make_root()
        with self.assertRaises(ValueError):
            create_server(forward_root=root,token=TOKEN,host="0.0.0.0")
        with self.assertRaises(ValueError):
            create_server(forward_root=root,token="short")

    def test_missing_snapshot_returns_503_without_creating_files(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/"forward"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        server=create_server(forward_root=root,token=TOKEN,port=0)
        status,_,_=self.request(server,"/",auth())
        self.assertEqual(status,503)
        self.assertEqual(tuple(root.iterdir()),())


if __name__=="__main__":
    unittest.main()
