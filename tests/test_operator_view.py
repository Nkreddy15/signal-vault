"""Offline, no-broker tests of authenticated PAPER ledger inspection."""
import base64
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from signal_vault.operator_server import create_server, _authorize, build_handler
from signal_vault.operator_view import OperatorSnapshotError, read_local_paper_snapshot
from signal_vault.paper_store import PersistentPaperOrderStore


TOKEN = "sample-dev-token-not-a-real-credential-please-change"


class OperatorViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "paper.sqlite3"
        with PersistentPaperOrderStore(self.db):
            pass

    def test_reads_ledger_without_mutating_it(self):
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO events (client_order_id,event_type,event_json,created_utc) VALUES (?,?,?,?)",
                        ("private-account-id", "TEST_EVENT", '{"secret":"do not show"}',
                         datetime.now(timezone.utc).isoformat()))
            con.commit()
        result = read_local_paper_snapshot(self.db)
        self.assertEqual(result["logical"]["cash_usd"], "100")
        self.assertEqual(result["logical"]["btc_qty"], "0")
        self.assertEqual(result["paper_orders"]["unresolved"], 0)
        self.assertEqual(result["recent_events"][0]["type"], "TEST_EVENT")
        self.assertNotIn("private-account-id", json.dumps(result))
        self.assertNotIn("do not show", json.dumps(result))
        self.assertEqual(result["source"], "LOCAL_SQLITE_LEDGER_NOT_LIVE_MARKET_DATA")
        with sqlite3.connect(self.db) as con:
            count = con.execute("SELECT count(*) FROM events").fetchone()[0]
        self.assertEqual(count, 1)

    def test_missing_database_fails_closed_and_never_creates_one(self):
        ghost = Path(self.tmp.name) / "missing.db"
        with self.assertRaises(OperatorSnapshotError):
            read_local_paper_snapshot(ghost)
        self.assertFalse(ghost.exists())

    def test_nan_ledger_fails_closed(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE logical_portfolio SET cash_usd='NaN' WHERE singleton=1")
        with self.assertRaises(OperatorSnapshotError):
            read_local_paper_snapshot(self.db)

    def test_reserved_exceeding_cash_fails_closed(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE logical_portfolio SET cash_usd='1' WHERE singleton=1")
            con.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?)",
                        ("private-id", "hash", "signal", "DRAFT_APPROVED", "buy", "5", "{}",
                         datetime.now(timezone.utc).isoformat()))
        with self.assertRaises(OperatorSnapshotError):
            read_local_paper_snapshot(self.db)

    def test_symlink_database_refused(self):
        shortcut = Path(self.tmp.name) / "shortcut.db"
        shortcut.symlink_to(self.db)
        with self.assertRaises(OperatorSnapshotError):
            read_local_paper_snapshot(shortcut)

    def test_rejects_oversized_page_request(self):
        with self.assertRaises(ValueError):
            read_local_paper_snapshot(self.db, max_items=50000)

    def test_auth_validation_and_no_public_binding(self):
        self.assertFalse(_authorize(None, TOKEN))
        self.assertFalse(_authorize("Basic not-base64!", TOKEN))
        self.assertFalse(_authorize("Bearer " + TOKEN, TOKEN))
        self.assertFalse(_authorize("Basic " + base64.b64encode(b"operator:wrong").decode(), TOKEN))
        self.assertTrue(_authorize("Basic " + base64.b64encode(("operator:" + TOKEN).encode()).decode(), TOKEN))
        with self.assertRaises(ValueError):
            build_handler(self.db, token="short")
        for host in ("0.0.0.0", "localhost", "::", "192.168.1.1"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                create_server(self.db, token=TOKEN, host=host, port=0)

    def test_http_is_authenticated_and_read_only(self):
        with create_server(self.db, token=TOKEN, port=0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            root = f"http://127.0.0.1:{server.server_address[1]}"
            auth = "Basic " + base64.b64encode(("operator:" + TOKEN).encode()).decode()
            with self.assertRaises(HTTPError) as unauth:
                urlopen(root + "/api/status", timeout=3)
            self.assertEqual(unauth.exception.code, 401)
            req = Request(root + "/api/status", headers={"Authorization": auth})
            with urlopen(req, timeout=3) as result:
                self.assertEqual(result.status, 200)
                self.assertEqual(result.headers["Cache-Control"], "no-store")
                data = json.load(result)
            self.assertEqual(data["mode"], "ALPACA_PAPER_ONLY")
            lanes={x["market"]:x for x in data["market_capabilities"]["markets"]}
            self.assertEqual(set(lanes),{"crypto","us_equity","kalshi_event_contract"})
            self.assertTrue(lanes["crypto"]["historical_research"])
            self.assertTrue(lanes["us_equity"]["historical_research"])
            self.assertTrue(lanes["kalshi_event_contract"]["historical_research"])
            self.assertFalse(any(x["live_execution"] for x in lanes.values()))
            readiness=data["market_readiness"]
            self.assertEqual(
                set(readiness["lanes"]),
                {"crypto","us_equity","kalshi_event_contract"},
            )
            self.assertFalse(
                readiness["lanes"]["crypto"][
                    "technically_ready_for_live_activation_review"
                ]
            )
            self.assertIn(
                "prospective_or_shadow_complete",
                readiness["lanes"]["crypto"][
                    "technical_blockers_before_live_activation_review"
                ],
            )
            self.assertFalse(readiness["any_live_activation_permitted"])
            req = Request(root + "/", headers={"Authorization": auth})
            with urlopen(req, timeout=3) as result:
                page = result.read().decode()
            self.assertIn("Signal Vault", page)
            self.assertIn("LOCAL LEDGER ONLY", page)
            self.assertIn("Market lanes", page)
            self.assertIn("crypto", page)
            self.assertIn("us_equity", page)
            self.assertIn("kalshi_event_contract", page)
            self.assertIn("Technical live-review ready", page)
            self.assertIn("Blockers:", page)
            self.assertNotIn("<script", page)
            req = Request(root + "/api/status", data=b"{}", method="POST",
                          headers={"Authorization": auth})
            with self.assertRaises(HTTPError) as blocked:
                urlopen(req, timeout=3)
            self.assertEqual(blocked.exception.code, 405)
            req = Request(root + "/api/status?token=bad", headers={"Authorization": auth})
            with self.assertRaises(HTTPError) as bad_query:
                urlopen(req, timeout=3)
            self.assertEqual(bad_query.exception.code, 404)
            server.shutdown()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
