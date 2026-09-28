"""Structured, secret-minimized runtime log records for paper operation."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, TextIO
import json
import sys

from .paper_runtime import PaperCycleResult


def cycle_log_record(*, result: PaperCycleResult, logical: Mapping[str, Decimal],
                     operator_halted: bool, at: datetime) -> dict[str, object]:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware log time required")
    return {
        "event": "paper_cycle",
        "mode": "ALPACA_PAPER_ONLY",
        "at_utc": at.astimezone(timezone.utc).isoformat(),
        "state": result.state,
        "client_order_id": result.client_order_id,
        "provider_stage": result.provider_stage,
        "paper_post_attempted": result.paper_post_attempted,
        "operator_halted": bool(operator_halted),
        "logical_cash_usd": str(logical["cash_usd"]),
        "logical_btc_qty": str(logical["btc_qty"]),
        "logical_realized_pnl_usd": str(logical["realized_pnl_usd"]),
        "logical_fee_usd_equiv": str(logical["fees_usd_equiv"]),
    }


def emit_cycle_log(*, result: PaperCycleResult, logical: Mapping[str, Decimal],
                   operator_halted: bool, at: datetime, stream: TextIO | None = None) -> None:
    target = stream or sys.stdout
    target.write(json.dumps(cycle_log_record(result=result, logical=logical,
                                             operator_halted=operator_halted, at=at),
                            sort_keys=True, separators=(",", ":")) + "\n")
    target.flush()
