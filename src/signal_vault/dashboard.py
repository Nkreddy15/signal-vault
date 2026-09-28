"""Local-only read-only owner view of *recorded* Signal Vault prototype state.

The HTTP server refuses public bind addresses and implements no order, fund,
credential, restart, or unhalt endpoints. Data is labeled offline/paper, never
shown as verified live P&L. Production cloud use needs separate authentication.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .paper_store import PersistentPaperOrderStore

_LOOPBACKS = frozenset({"127.0.0.1", "localhost"})
_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signal Vault | Local Operator View</title>
<style>
:root{color-scheme:dark;font:15px system-ui,sans-serif;background:#071917;color:#dcece5}
body{max-width:1060px;padding:22px;margin:auto} h1{font-size:2rem;margin-bottom:6px}
small,.muted{color:#a3c3b7} .warn{background:#48351d;color:#ffdeab;border-radius:6px;padding:9px}
.card{background:#112c27;border:1px solid #36564a;border-radius:12px;padding:18px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
.number{font-size:1.35rem;font-weight:650}.halt{color:#ff9a9a}.ready{color:#9fe1b7}
.table{width:100%;border-collapse:collapse;table-layout:fixed;word-wrap:break-word}
.table td,.table th{text-align:left;padding:9px 4px;border-bottom:1px solid #34554a}
.table th{color:#a3c3b7;font-size:.85rem} .table td{font-size:.85rem}
</style></head><body>
<h1>SIGNAL VAULT</h1><p class="warn">DEVELOPMENT ONLY · OFFLINE / PAPER RECORDS · NO VERIFIED LIVE PROFITS</p>
<p class="muted">Local operator overview. This page is deliberately read-only. Use a separate audited operator action to halt submissions.</p>
<section class="grid">
<div class="card"><small>Operator control</small><p id="halt" class="number">Loading…</p></div>
<div class="card"><small>Virtual isolated budget</small><p id="cash" class="number">—</p></div>
<div class="card"><small>Recorded BTC quantity</small><p id="btc" class="number">—</p></div>
<div class="card"><small>Unresolved broker records</small><p id="unresolved" class="number">—</p></div>
</section>
<div class="card"><h2>Persisted paper lifecycle</h2><div id="states" class="muted">Loading…</div></div>
<div class="card"><h2>Audit activity (latest 50)</h2>
<table class="table"><thead><tr><th style="width:17%">UTC</th><th style="width:25%">Event</th><th style="width:23%">Order ID</th><th>Recorded details</th></tr></thead><tbody id="events"></tbody></table></div>
<p class="muted" id="refresh">Refreshing securely from localhost.</p>
<script src="/app.js" defer></script></body></html>
"""
_JS = """'use strict';
const write = (id, value) => { document.getElementById(id).textContent = value; };
async function refresh() {
  try {
    const r = await fetch('/api/status', {cache:'no-store'});
    if(!r.ok) throw new Error('Dashboard read failed: '+r.status);
    const obj = await r.json();
    const b = obj.paper_virtual_budget;
    write('halt', obj.operator_halt ? 'HALTED — New submissions blocked' : 'No manual HALT active');
    document.getElementById('halt').className = obj.operator_halt ? 'number halt' : 'number ready';
    write('cash', b ? '$'+b.virtual_cash : 'Not initialized');
    write('btc', b ? b.virtual_btc + ' BTC' : 'Not initialized');
    write('unresolved', String(obj.unresolved_provider_records));
    write('states', Object.entries(obj.paper_order_states).map(([a,n]) => a+': '+n).join(' · ') || 'No provider paper orders');
    const tb = document.getElementById('events'); tb.replaceChildren();
    for(const event of obj.events) {
      const row = document.createElement('tr');
      for(const value of [event.created_utc, event.type, event.client_order_id,
                           JSON.stringify(event.details)]) {
        const cell = document.createElement('td');
        cell.textContent = String(value); // NEVER render provider/user strings as HTML.
        row.appendChild(cell);
      }
      tb.appendChild(row);
    }
    write('refresh', 'Last local refresh: '+new Date().toLocaleString()+' · No real-money P&L shown.');
  } catch(err) { write('refresh', 'Read error: '+err.message+' (No orders are affected)'); }
}
refresh();setInterval(refresh,20000);
"""


def dashboard_snapshot(store: PersistentPaperOrderStore) -> dict[str, Any]:
    """View only already persisted facts, not generated financial performance."""
    counts = {str(stage): count for stage,count in store.connection.execute(
        "SELECT json_extract(state_json,'$.stage'),COUNT(*) FROM paper_order_states GROUP BY 1")}
    recent = store.connection.execute("""SELECT seq,client_order_id,event_type,event_json,created_utc
        FROM events ORDER BY seq DESC LIMIT 50""").fetchall()
    events = []
    for seq,client,typ,data,at in recent:
        try:
            details = json.loads(data)
        except (ValueError, TypeError):
            details = {"warning":"invalid persisted event JSON"}
        events.append({"seq": seq,"client_order_id":client,"type":typ,
                       "details": details,"created_utc":at})
    return {"mode":"DEVELOPMENT_PAPER_ONLY", "real_money_execution":False,
            "no_provider_paper_profit_claim":True,"operator_halt":store.is_operator_halted(),
            "unresolved_provider_records": sum(n for stage,n in counts.items() if stage != "reconciled"),
            "paper_order_states":counts,"paper_virtual_budget":store.budget_snapshot(),
            "events":events}


def make_handler(db_file: str | Path, *, allowed_port: int):
    database = Path(db_file)
    if not database.is_file():
        raise FileNotFoundError("select an existing local Signal Vault SQLite database")
    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status: int, typ: str, payload: bytes):
            self.send_response(status)
            self.send_header("Content-Type",typ)
            self.send_header("Content-Length",str(len(payload)))
            self.send_header("Cache-Control","no-store, max-age=0")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy",
                 "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)
        def do_GET(self):
            if self.headers.get("Host") not in {f"127.0.0.1:{allowed_port}",
                                                 f"localhost:{allowed_port}"}:
                self._respond(403,"text/plain; charset=utf-8",b"Invalid local Host")
                return
            path=urlsplit(self.path)
            if path.query:
                self._respond(404,"text/plain; charset=utf-8",b"Not found")
                return
            if path.path in ("/", "/index.html"):
                self._respond(200,"text/html; charset=utf-8",_HTML.encode("utf-8"))
            elif path.path == "/app.js":
                self._respond(200,"application/javascript; charset=utf-8",_JS.encode("utf-8"))
            elif path.path == "/api/status":
                try:
                    with PersistentPaperOrderStore(database) as store:
                        raw=json.dumps(dashboard_snapshot(store),sort_keys=True).encode("utf-8")
                    self._respond(200,"application/json; charset=utf-8",raw)
                except (sqlite3.Error, ValueError):
                    self._respond(503,"application/json; charset=utf-8",
                                  b'{"error":"local state unavailable"}')
            else:
                self._respond(404,"text/plain; charset=utf-8",b"Not found")
        def do_POST(self):
            self._respond(405,"text/plain; charset=utf-8",b"Dashboard is read-only")
        def do_PUT(self):
            self._respond(405,"text/plain; charset=utf-8",b"Dashboard is read-only")
        def do_DELETE(self):
            self._respond(405,"text/plain; charset=utf-8",b"Dashboard is read-only")
        def log_message(self, format: str, *args: object) -> None:
            pass  # no URLs, credentials or sensitive audit fields echoed to logs
    return Handler


def serve_local_dashboard(db_file: str | Path, *, host: str="127.0.0.1",port: int=8765) -> None:
    if host != "127.0.0.1" or not (1024 <= port <= 65535):
        raise ValueError("development dashboard MUST be bound only to 127.0.0.1")
    server = ThreadingHTTPServer((host,port),make_handler(db_file,allowed_port=port))
    print(f"Signal Vault LOCAL PAPER dashboard: http://127.0.0.1:{port}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser=argparse.ArgumentParser(description="Local read-only paper trading dashboard")
    parser.add_argument("--db",required=True,help="Existing private local SQLite path")
    parser.add_argument("--port",type=int,default=8765)
    args=parser.parse_args()
    serve_local_dashboard(args.db,port=args.port)

if __name__ == "__main__":
    main()
