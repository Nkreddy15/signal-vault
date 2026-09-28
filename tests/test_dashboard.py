import json
import tempfile
import threading
import unittest
from datetime import datetime,timezone
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from signal_vault.dashboard import dashboard_snapshot, make_handler,serve_local_dashboard
from signal_vault.paper_store import PersistentPaperOrderStore

T=datetime(2026,9,28,23,0,tzinfo=timezone.utc)

class DashboardTests(unittest.TestCase):
    def test_snapshot_is_read_only_and_labels_nonverified_performance(self):
        with PersistentPaperOrderStore(":memory:") as store:
            store.set_operator_halt(True,reason="owner test",at=T)
            result=dashboard_snapshot(store)
            self.assertEqual(result["mode"],"DEVELOPMENT_PAPER_ONLY")
            self.assertFalse(result["real_money_execution"])
            self.assertTrue(result["no_provider_paper_profit_claim"])
            self.assertTrue(result["operator_halt"])
            self.assertEqual(result["paper_order_states"],{})
            self.assertEqual(result["events"][0]["type"],"HALT_ENABLED")

    def test_no_public_bind_or_nonexistent_file(self):
        with self.assertRaises(ValueError):
            serve_local_dashboard("does-not-exist",host="0.0.0.0",port=8765)
        with self.assertRaises(FileNotFoundError):
            make_handler("does-not-exist",allowed_port=8765)

    def test_local_http_get_and_no_mutation_methods(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"owner.sqlite"
            with PersistentPaperOrderStore(p) as store:
                store.set_operator_halt(True,reason="test",at=T)
            # Port 0 binds to a random local ephemeral port. Handler is generated
            # after binding by a short delegated request class with the actual port.
            server = ThreadingHTTPServer(("127.0.0.1",0),BaseHandlerPlaceholder)
            port=server.server_address[1]
            server.RequestHandlerClass=make_handler(p,allowed_port=port)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                base=f"http://127.0.0.1:{port}"
                with urlopen(base+"/api/status",timeout=3) as response:
                    self.assertEqual(response.status,200)
                    self.assertEqual(response.headers.get("Cache-Control"),"no-store, max-age=0")
                    content=json.loads(response.read())
                    self.assertTrue(content["operator_halt"])
                with self.assertRaises(HTTPError) as wrong_host:
                    urlopen(Request(base+"/api/status",headers={"Host":"evil.example"}),timeout=3)
                self.assertEqual(wrong_host.exception.code,403)
                with self.assertRaises(HTTPError) as post:
                    urlopen(Request(base+"/api/status",data=b"{}",method="POST"),timeout=3)
                self.assertEqual(post.exception.code,405)
                with PersistentPaperOrderStore(p) as store:
                    self.assertTrue(store.is_operator_halted())
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)

from http.server import BaseHTTPRequestHandler
class BaseHandlerPlaceholder(BaseHTTPRequestHandler):
    def do_GET(self):
        raise AssertionError("handler was not installed")
    def log_message(self,*args):pass

if __name__ == "__main__":unittest.main()
