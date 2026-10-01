"""Loopback-only, read-only Basic-auth monitoring for Signal Vault's PAPER ledger.

No network broker imports; no POST/PUT/DELETE endpoints. Use SSH port forwarding
or a separately reviewed TLS/authenticated gateway for remote access; NEVER
expose the HTTP listener directly to a public interface.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .operator_view import OperatorSnapshotError, read_local_paper_snapshot
from .market_capabilities import current_market_capabilities
from .current_readiness import current_readiness_baseline
from .all_market_dashboard import build_dashboard_snapshot, render_dashboard_html, snapshot_json


def _authorize(header: str | None, token: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        data = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    username, sep, provided = data.partition(":")
    return bool(sep) and hmac.compare_digest(username, "operator") and hmac.compare_digest(provided, token)


def _dashboard(payload: dict[str, object]) -> bytes:
    ledger = payload["logical"]
    orders = payload["paper_orders"]
    safe = lambda value: html.escape(str(value), quote=True)
    fields = [("Unreserved cash", "$" + safe(ledger["unreserved_cash_usd"])),
              ("Reserved", "$" + safe(ledger["reserved_usd"])),
              ("BTC inventory (units)", safe(ledger["btc_qty"])),
              ("Realized P&L (ledger)", "$" + safe(ledger["realized_pnl_usd"])),
              ("Accumulated fee equivalent", "$" + safe(ledger["fees_usd_equiv"])),
              ("Unresolved orders", safe(orders["unresolved"]))]
    cards = "".join(f'<article><small>{label}</small><strong>{value}</strong></article>'
                    for label, value in fields)
    events = "".join(f'<tr><td>{safe(item["type"])}</td><td>{safe(item["at_utc"])}</td></tr>'
                     for item in payload["recent_events"])
    capabilities=payload["market_capabilities"]["markets"]
    readiness=payload["market_readiness"]["lanes"]
    multimarket_execution=payload["multimarket_execution"]
    execution_cards="".join(
        f'<article><small>{safe(lane)}</small>'
        f'<strong>{safe(values["unresolved"])} unresolved</strong>'
        f'<span>Total journaled: {safe(values["count"])}</span></article>'
        for lane,values in multimarket_execution["by_lane"].items())
    execution_rows="".join(
        f'<tr><td>{safe(item["market_lane"])}</td>'
        f'<td>{safe(item["instrument"])}</td>'
        f'<td>{safe(item["stage"])}</td>'
        f'<td>{safe(item["provider_status"])}</td>'
        f'<td>{safe(item["filled_qty"])}</td>'
        f'<td>{safe(item["updated_utc"])}</td></tr>'
        for item in multimarket_execution["recent"])
    market_cards="".join(
        f'<article><small>{safe(lane["market"])}</small>'
        f'<strong>{safe(lane["order_submission"])}</strong>'
        f'<span>Historical: {safe(lane["historical_research"])}</span>'
        f'<span>Prospective: {safe(lane["prospective_collection"])}</span>'
        f'<span>Paper: {safe(lane["paper_execution"])}</span>'
        f'<span>Live: {safe(lane["live_execution"])}</span>'
        f'<span>Technical live-review ready: '
        f'{safe(readiness[lane["market"]]["technically_ready_for_live_activation_review"])}</span>'
        f'<span>Blockers: {safe(", ".join(readiness[lane["market"]]["technical_blockers_before_live_activation_review"]))}</span>'
        f'</article>'
        for lane in capabilities)
    badge = "HALTED" if payload["operator_halted"] else "NOT HALTED"
    markup = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Signal Vault | Private paper monitor</title><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60"><style>
:root{{font-family:system-ui,sans-serif;color:#d9f2e8;background:#111e1b}}
body{{max-width:980px;margin:4rem auto;padding:0 1.2rem}}h1{{font-size:2rem}}
.sub{{color:#a5c8b6}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:12px}}
article{{padding:1.2rem;border:1px solid #3f6554;border-radius:10px;background:#1b3028;display:flex;flex-direction:column;gap:12px}}
small{{color:#abc8b9}}strong{{font-size:1.6rem}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;border-bottom:1px solid #3f6554;text-align:left;overflow-wrap:anywhere}}
.warning{{border-left:4px solid #e4bb6c;padding:14px;background:#2b3023}}
</style></head><body><h1>Signal Vault</h1>
<p class="sub">Private monitoring · ALPACA PAPER ONLY · Operator status: <b>{badge}</b></p>
<p class="warning">LOCAL LEDGER ONLY. Inventory is not a live valuation. No authenticated exchange results or profit claims are inferred by this dashboard.</p>
<div class="cards">{cards}</div><h2>Market lanes</h2><div class="cards">{market_cards}</div>
<h2>Cross-market paper/demo execution</h2><div class="cards">{execution_cards}</div>
<table><tr><th>Lane</th><th>Instrument</th><th>Stage</th><th>Provider status</th><th>Filled qty</th><th>Updated UTC</th></tr>{execution_rows}</table>
<h2>Recent journal events</h2><table><tr><th>Event type</th><th>UTC timestamp</th></tr>{events}</table>
<p class="sub">Last ledger update: {safe(payload["ledger_updated_utc"])} · Read-only · Reloads each minute.</p>
</body></html>'''
    return markup.encode("utf-8")


def build_handler(db_path: str | Path, *, token: str, forward_root: str | Path | None = None) -> type[BaseHTTPRequestHandler]:
    if len(token) < 32 or token.strip() != token or "\x00" in token:
        raise ValueError("operator token must contain at least 32 non-space characters")
    path = Path(db_path).expanduser()
    forward_path = Path(forward_root).expanduser() if forward_root is not None else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "SignalVaultLocalMonitor/1"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            # Avoid leaking authorization, query data and database identifiers to logs.
            del format, args

        def _send(self, code: int, body: bytes, content_type: str, *, challenge: bool = False) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if challenge:
                self.send_header("WWW-Authenticate", 'Basic realm="Signal Vault private paper monitor", charset="UTF-8"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not _authorize(self.headers.get("Authorization"), token):
                return self._send(401, b"Authentication required\n", "text/plain; charset=utf-8", challenge=True)
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment or parsed.path not in ("/", "/api/status", "/all-markets", "/api/all-markets"):
                return self._send(404, b"Not found\n", "text/plain; charset=utf-8")
            if parsed.path in ("/all-markets", "/api/all-markets"):
                if forward_path is None:
                    return self._send(
                        503,
                        b"All-market forward root not configured\n",
                        "text/plain; charset=utf-8",
                    )
                try:
                    snapshot=build_dashboard_snapshot(root=forward_path)
                except Exception:
                    return self._send(
                        503,
                        b"All-market forward evidence unavailable or inconsistent\n",
                        "text/plain; charset=utf-8",
                    )
                if parsed.path == "/api/all-markets":
                    return self._send(
                        200,
                        snapshot_json(snapshot),
                        "application/json; charset=utf-8",
                    )
                return self._send(
                    200,
                    render_dashboard_html(snapshot),
                    "text/html; charset=utf-8",
                )
            try:
                payload = read_local_paper_snapshot(path)
                payload["market_capabilities"] = current_market_capabilities()
                payload["market_readiness"] = current_readiness_baseline()
            except OperatorSnapshotError:
                return self._send(503, b"Local paper ledger unavailable or inconsistent\n",
                                  "text/plain; charset=utf-8")
            if parsed.path == "/api/status":
                data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                self._send(200, data, "application/json; charset=utf-8")
            else:
                self._send(200, _dashboard(payload), "text/html; charset=utf-8")

        def do_POST(self) -> None:
            self._send(405, b"Read-only monitor\n", "text/plain; charset=utf-8")
        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST
        do_OPTIONS = do_POST

    return Handler


def create_server(db_path: str | Path, *, token: str, host: str = "127.0.0.1",
                  port: int = 8766, forward_root: str | Path | None = None) -> ThreadingHTTPServer:
    try:
        allowed = ip_address(host).is_loopback and host == "127.0.0.1"
    except ValueError:
        allowed = False
    if not allowed:
        raise ValueError("operator monitor MUST bind to literal IPv4 loopback 127.0.0.1")
    if not 0 <= port <= 65535:
        raise ValueError("invalid monitor port")
    handler = build_handler(db_path, token=token, forward_root=forward_root)
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private loopback-only paper ledger monitor")
    parser.add_argument("--db", default=os.environ.get("SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--forward-root",
        default=os.environ.get("SIGNAL_VAULT_FORWARD_ROOT"),
    )
    args = parser.parse_args(argv)
    token = os.environ.get("SIGNAL_VAULT_OPERATOR_TOKEN", "")
    with create_server(
        args.db,
        token=token,
        host=args.host,
        port=args.port,
        forward_root=args.forward_root,
    ) as server:
        print(f"Private PAPER monitoring available at http://127.0.0.1:{server.server_address[1]}", flush=True)
        server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
