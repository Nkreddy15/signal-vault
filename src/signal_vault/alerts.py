"""Local secret-free alert sink used before any external notification service is authorized."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os

from .paper_runtime import PaperCycleResult


_ALERT_STATES = {
    "BLOCKED_PROVIDER_ORDER",
    "BLOCKED_RECONCILIATION",
    "BLOCKED_FEE_AUDIT",
    "BLOCKED_PROVIDER_DRIFT",
    "BLOCKED_RUNTIME_EXCEPTION",
    "BLOCKED_BACKUP_FAILURE",
    "BLOCKED_REPORTING_FAILURE",
    "HOLD_BAD_MARKET_DATA",
    "OPERATOR_HALTED",
}


def alert_severity(state: str) -> str | None:
    if state not in _ALERT_STATES:
        return None
    if state in {"BLOCKED_PROVIDER_DRIFT", "BLOCKED_RECONCILIATION", "BLOCKED_FEE_AUDIT",
                 "BLOCKED_RUNTIME_EXCEPTION", "BLOCKED_BACKUP_FAILURE", "BLOCKED_REPORTING_FAILURE"}:
        return "critical"
    if state == "OPERATOR_HALTED":
        return "info"
    return "warning"


class JsonlAlertSink:
    """Append state transitions locally; no network and no provider payloads."""
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._last_alert_state: str | None = None

    def record_if_needed(self, result: PaperCycleResult, *, at: datetime) -> bool:
        severity = alert_severity(result.state)
        if severity is None:
            self._last_alert_state = None
            return False
        if result.state == self._last_alert_state:
            return False
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware alert time required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.is_symlink():
            raise ValueError("alert path must not be a symlink")
        payload = {
            "schema_version": 1,
            "mode": "ALPACA_PAPER_ONLY",
            "created_utc": at.astimezone(timezone.utc).isoformat(),
            "severity": severity,
            "state": result.state,
            "client_order_id": result.client_order_id,
            "provider_stage": result.provider_stage,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        self._last_alert_state = result.state
        return True
