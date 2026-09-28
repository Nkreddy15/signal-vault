"""Loopback-only private owner control/read API for the paper runtime.

This service never receives broker credentials and imports no broker client. It
reads Signal Vault's local logical ledger and may only toggle the persistent
operator halt. Bind is intentionally restricted to loopback; TLS/reverse proxy
is a deployment concern for any future remote access.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
import hmac
import json
import os

from .paper_store import PersistentPaperOrderStore
from .operator_view import read_local_paper_snapshot

_MAX_BODY = 4096
_MAX_HEALTH = 64 * 1024


def _safe_decimal_map(logical: Mapping[str, Decimal]) -> dict[str, str]:
    allowed = ("cash_usd", "btc_qty", "btc_cost_basis_usd", "realized_pnl_usd",
               "fees_usd_equiv", "peak_equity_usd", "session_start_equity_usd")
    return {key: str(logical[key]) for key in allowed}


@dataclass(frozen=True)
class OwnerApiConfig:
    db_path: Path
    health_path: Path
    token: str
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "OwnerApiConfig":
        values = os.environ if env is None else env
        db = Path(values.get("SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3").strip()).expanduser()
        health = Path(values.get("SIGNAL_VAULT_HEALTH_FILE", str(db.with_name(db.name + ".health.json"))).strip()).expanduser()
        token = values.get("SIGNAL_VAULT_OWNER_TOKEN", "")
        host = values.get("SIGNAL_VAULT_OWNER_HOST", "127.0.0.1").strip()
        raw_port = values.get("SIGNAL_VAULT_OWNER_PORT", "8765").strip()
        if host != "127.0.0.1":
            raise ValueError("owner API must bind to literal IPv4 loopback 127.0.0.1")
        if len(token) < 32 or len(token) > 512 or any(ch in token for ch in "\r\n\x00"):
            raise ValueError("owner API token must be a secret of at least 32 characters")
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError("invalid owner API port") from exc
        if not 1024 <= port <= 65535:
            raise ValueError("owner API port outside unprivileged range")
        if "\x00" in str(db) or "\x00" in str(health):
            raise ValueError("invalid owner API path")
        return cls(db, health, token, host, port)


class OwnerService:
    def __init__(self, config: OwnerApiConfig) -> None:
        self.config = config

    def authorized(self, auth_header: str | None) -> bool:
        if not isinstance(auth_header, str) or not auth_header.startswith("Bearer "):
            return False
        supplied = auth_header[7:]
        return hmac.compare_digest(supplied, self.config.token)

    def status(self) -> dict[str, object]:
        """Read-only and fail-closed: a missing journal MUST NEVER be auto-created by GET."""
        snapshot = read_local_paper_snapshot(self.config.db_path)
        ledger = snapshot["logical"]
        return {
            "mode": "ALPACA_PAPER_ONLY",
            "source": snapshot["source"],
            "operator_halted": snapshot["operator_halted"],
            "halt_reason": snapshot["halt_reason"],
            "logical": {key: ledger[key] for key in (
                "cash_usd", "btc_qty", "btc_cost_basis_usd", "realized_pnl_usd",
                "fees_usd_equiv", "peak_equity_usd", "session_start_equity_usd")},
            "order_state_count": snapshot["paper_orders"]["count"],
            "unresolved_provider_orders": snapshot["paper_orders"]["unresolved"],
            "pending_fee_audits": snapshot["paper_orders"]["pending_fee_audits"],
            "last_mark": snapshot["last_mark"],
        }

    def health(self) -> dict[str, object]:
        path = self.config.health_path
        if not path.exists():
            return {"mode": "ALPACA_PAPER_ONLY", "state": "HEALTH_NOT_WRITTEN_YET"}
        if not path.is_file() or path.is_symlink():
            raise ValueError("health file must be a regular non-symlink file")
        raw = path.read_bytes()
        if len(raw) > _MAX_HEALTH:
            raise ValueError("health file unexpectedly large")
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("mode") != "ALPACA_PAPER_ONLY":
            raise ValueError("malformed health file")
        # Health writer itself is allowlisted; return only known safe fields.
        allowed = {"schema_version", "mode", "updated_utc", "state", "client_order_id",
                   "provider_stage", "paper_post_attempted", "operator_halted", "logical", "last_mark"}
        return {k: v for k, v in value.items() if k in allowed}

    def halt(self, reason: str) -> dict[str, object]:
        # Prevent accidental creation of a new clean $100 journal on a typo.
        read_local_paper_snapshot(self.config.db_path)
        with PersistentPaperOrderStore(self.config.db_path) as store:
            store.set_operator_halt(True, reason=reason, at=datetime.now(timezone.utc))
        return self.status()

    def resume(self) -> dict[str, object]:
        read_local_paper_snapshot(self.config.db_path)
        with PersistentPaperOrderStore(self.config.db_path) as store:
            store.set_operator_halt(False, reason="", at=datetime.now(timezone.utc))
        return self.status()


def _handler(service: OwnerService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SignalVaultOwner/0.1"
        sys_version = ""

        def _reply(self, status: int, payload: Mapping[str, object]) -> None:
            body = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _auth(self) -> bool:
            if not service.authorized(self.headers.get("Authorization")):
                self._reply(401, {"error": "unauthorized"})
                return False
            return True

        def do_GET(self) -> None:
            if not self._auth():
                return
            try:
                if self.path == "/v1/status":
                    self._reply(200, service.status())
                elif self.path == "/v1/health":
                    self._reply(200, service.health())
                else:
                    self._reply(404, {"error": "not_found"})
            except Exception as exc:
                self._reply(500, {"error": "internal", "type": type(exc).__name__})

        def do_POST(self) -> None:
            if not self._auth():
                return
            try:
                raw_len = self.headers.get("Content-Length", "0")
                length = int(raw_len)
                if length < 0 or length > _MAX_BODY:
                    raise ValueError("request body too large")
                body = self.rfile.read(length)
                value = json.loads(body or b"{}")
                if not isinstance(value, dict):
                    raise ValueError("JSON object required")
                if self.path == "/v1/halt":
                    if set(value) != {"reason"} or not isinstance(value["reason"], str):
                        raise ValueError("halt requires only reason")
                    self._reply(200, service.halt(value["reason"]))
                elif self.path == "/v1/resume":
                    if value:
                        raise ValueError("resume body must be empty object")
                    self._reply(200, service.resume())
                else:
                    self._reply(404, {"error": "not_found"})
            except (ValueError, json.JSONDecodeError):
                self._reply(400, {"error": "bad_request"})
            except Exception as exc:
                self._reply(500, {"error": "internal", "type": type(exc).__name__})

        def log_message(self, format: str, *args: object) -> None:
            # Do not log Authorization headers or request bodies. Base log only
            # contains remote address, path/status formatting supplied internally.
            return
    return Handler


def main() -> int:
    config = OwnerApiConfig.from_environment()
    service = OwnerService(config)
    # Opening status on startup validates the local database before listening.
    service.status()
    server = ThreadingHTTPServer((config.host, config.port), _handler(service))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
