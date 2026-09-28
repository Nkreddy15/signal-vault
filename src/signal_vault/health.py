"""Secret-free, atomic health snapshot for the private paper runtime."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Any
import json
import os
import tempfile

from .paper_runtime import PaperCycleResult


def _decimal_text(value: object) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("health account values must be finite Decimal")
    return str(value)


def build_health_snapshot(*, result: PaperCycleResult, logical: Mapping[str, Decimal],
                          operator_halted: bool, at: datetime) -> dict[str, Any]:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware health timestamp required")
    return {
        "schema_version": 1,
        "mode": "ALPACA_PAPER_ONLY",
        "updated_utc": at.astimezone(timezone.utc).isoformat(),
        "state": result.state,
        "client_order_id": result.client_order_id,
        "provider_stage": result.provider_stage,
        "paper_post_attempted": result.paper_post_attempted,
        "operator_halted": bool(operator_halted),
        "logical": {
            "cash_usd": _decimal_text(logical["cash_usd"]),
            "btc_qty": _decimal_text(logical["btc_qty"]),
            "realized_pnl_usd": _decimal_text(logical["realized_pnl_usd"]),
            "fee_usd_equiv": _decimal_text(logical["fees_usd_equiv"]),
        },
    }


def write_health_snapshot(path: str | Path, payload: Mapping[str, object]) -> None:
    """Atomically replace the health file and keep it owner-readable only."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.is_symlink():
        raise ValueError("health path must not be a symlink")
    body = (json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
