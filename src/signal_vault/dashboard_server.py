"""Standalone private read-only server for the persisted all-market dashboard.

Unlike operator_server, this viewer does not require the PAPER SQLite ledger.
It reads only the bounded dashboard snapshot written by the Railway all-market
cron. It binds to literal IPv4 loopback, requires Basic authentication, and
has no provider or execution imports.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import os
from pathlib import Path
from urllib.parse import urlsplit

from .all_market_dashboard import render_dashboard_html, snapshot_json, KIND
from .dashboard_snapshot_archive import read_dashboard_snapshot


def _authorized(header:str|None, token:str)->bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded=base64.b64decode(header[6:],validate=True).decode("utf-8")
    except (ValueError,UnicodeDecodeError,binascii.Error):
        return False
    username,sep,password=decoded.partition(":")
    return bool(sep) and hmac.compare_digest(username,"operator") and hmac.compare_digest(password,token)


def build_handler(*,forward_root:Path, token:str)->type[BaseHTTPRequestHandler]:
    if len(token)<32 or token.strip()!=token or "\x00" in token:
        raise ValueError("dashboard token must contain at least 32 non-space characters")
    root=Path(forward_root).expanduser()

    class Handler(BaseHTTPRequestHandler):
        server_version="SignalVaultAllMarketDashboard/1"
        sys_version=""

        def log_message(self, format:str, *args:object)->None:
            del format,args

        def _send(self,code:int,body:bytes,content_type:str,*,challenge:bool=False)->None:
            self.send_response(code)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
            )
            if challenge:
                self.send_header(
                    "WWW-Authenticate",
                    'Basic realm="Signal Vault all-market dashboard", charset="UTF-8"',
                )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self)->None:
            if not _authorized(self.headers.get("Authorization"),token):
                return self._send(
                    401,b"Authentication required\n","text/plain; charset=utf-8",
                    challenge=True,
                )
            parsed=urlsplit(self.path)
            if parsed.query or parsed.fragment or parsed.path not in ("/","/api/status"):
                return self._send(404,b"Not found\n","text/plain; charset=utf-8")
            try:
                snapshot=read_dashboard_snapshot(base=root)
                if snapshot.get("kind")!=KIND:
                    raise ValueError("unexpected dashboard snapshot kind")
            except Exception:
                return self._send(
                    503,
                    b"Dashboard snapshot unavailable or inconsistent\n",
                    "text/plain; charset=utf-8",
                )
            if parsed.path=="/api/status":
                return self._send(
                    200,snapshot_json(snapshot),"application/json; charset=utf-8"
                )
            return self._send(
                200,render_dashboard_html(snapshot),"text/html; charset=utf-8"
            )

        def do_POST(self)->None:
            self._send(405,b"Read-only dashboard\n","text/plain; charset=utf-8")
        do_PUT=do_POST
        do_DELETE=do_POST
        do_PATCH=do_POST
        do_OPTIONS=do_POST

    return Handler


def create_server(
    *,
    forward_root:Path,
    token:str,
    host:str="127.0.0.1",
    port:int=8770,
)->ThreadingHTTPServer:
    try:
        allowed=ip_address(host).is_loopback and host=="127.0.0.1"
    except ValueError:
        allowed=False
    if not allowed:
        raise ValueError("dashboard server MUST bind to literal IPv4 loopback 127.0.0.1")
    if not 1024<=port<=65535:
        raise ValueError("dashboard port outside unprivileged range")
    return ThreadingHTTPServer(
        (host,port),
        build_handler(forward_root=forward_root,token=token),
    )


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Private standalone Signal Vault all-market dashboard"
    )
    parser.add_argument(
        "--forward-root",
        default=os.environ.get(
            "SIGNAL_VAULT_FORWARD_ROOT",
            "/var/lib/signal-vault/forward",
        ),
    )
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8770)
    args=parser.parse_args(argv)
    token=os.environ.get("SIGNAL_VAULT_DASHBOARD_TOKEN","")
    with create_server(
        forward_root=Path(args.forward_root),
        token=token,
        host=args.host,
        port=args.port,
    ) as server:
        print(
            f"Signal Vault dashboard available at http://127.0.0.1:{server.server_address[1]}",
            flush=True,
        )
        server.serve_forever(poll_interval=0.5)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
