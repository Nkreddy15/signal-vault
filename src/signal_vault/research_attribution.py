"""Cost-aware descriptive trade attribution on the known pre-gap development set.

This module is diagnostic research only. It never changes trading logic, opens
reserved post-gap CSVs, contacts Alpaca or imports an order executor.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from statistics import median
import json

from .backtest import BacktestResult, SimulatedFill, simulate
from .market_data import load_csv
from .research_v02 import DEVELOPMENT_CSV, DEVELOPMENT_SHA256, DEVELOPMENT_END, DEVELOPMENT_ROWS, V01, V02


def _describe_bucket(pairs: list[tuple[Decimal, Decimal]]) -> dict[str, object]:
    pnl = [p for _, p in pairs]
    return {
        "completed_trades": len(pairs),
        "profitable": sum(p > 0 for p in pnl),
        "losing": sum(p < 0 for p in pnl),
        "flat": sum(p == 0 for p in pnl),
        "combined_net_pnl_usd": str(sum(pnl, Decimal("0"))),
        "median_trade_net_pnl_usd": str(median(pnl)) if pnl else None,
    }


def attribute_trades(result: BacktestResult) -> dict[str, object]:
    """Reconcile each BUY/SELL pair and separately mark any remaining open BUY.

    Buckets are mutually exclusive. A result with an unpaired SELL, overlapping
    BUY or a mismatch with its reported ending equity is rejected.
    """
    pending: SimulatedFill | None = None
    complete: list[tuple[Decimal, Decimal]] = []
    for fill in result.fills:
        if fill.side == "buy":
            if pending is not None or fill.base_qty <= 0:
                raise ValueError("unexpected overlapping or nonpositive research BUY")
            pending = fill
        elif fill.side == "sell":
            if pending is None or fill.base_qty != pending.base_qty:
                raise ValueError("unpaired or quantity-mismatched research SELL")
            hours = Decimal(str(
                (datetime.fromisoformat(fill.time) -
                 datetime.fromisoformat(pending.time)).total_seconds()
            )) / Decimal("3600")
            if hours <= 0:
                raise ValueError("non-chronological research fill pair")
            complete.append((hours, pending.cash_delta + fill.cash_delta))
            pending = None
        else:
            raise ValueError("unknown research fill side")

    closed_pnl = sum((p for _, p in complete), Decimal("0"))
    open_pnl = (pending.cash_delta + pending.base_qty * result.last_mark_price
                if pending is not None else Decimal("0"))
    if abs((closed_pnl + open_pnl) - result.net_pnl_usd) > Decimal("0.00000001"):
        raise ValueError("trade attribution does not reconcile with ending equity")
    durations = [h for h, _ in complete]
    return {
        "strategy_version": result.strategy_version,
        "full_sample_net_pnl_usd": str(result.net_pnl_usd),
        "estimated_fees_usd": str(result.total_estimated_fees_usd),
        "fill_count": len(result.fills),
        "completed": _describe_bucket(complete),
        "median_holding_hours": str(median(durations)) if durations else None,
        "held_at_most_6_hours": _describe_bucket([(h, p) for h, p in complete if h <= 6]),
        "held_over_6_under_24_hours": _describe_bucket([(h, p) for h, p in complete if 6 < h < 24]),
        "held_at_least_24_hours": _describe_bucket([(h, p) for h, p in complete if h >= 24]),
        "open_position": pending is not None,
        "open_position_marked_pnl_usd": str(open_pnl),
        "reconciliation": "PASSED",
    }


def main() -> int:
    path: Path = DEVELOPMENT_CSV
    actual = sha256(path.read_bytes()).hexdigest()
    if actual != DEVELOPMENT_SHA256:
        raise ValueError("pre-gap development fingerprint mismatch")
    bars = load_csv(path, as_of=DEVELOPMENT_END, min_count=DEVELOPMENT_ROWS)
    if (len(bars) != DEVELOPMENT_ROWS or
            bars[0].start.isoformat() != "2025-12-25T22:00:00+00:00" or
            bars[-1].close_time != DEVELOPMENT_END):
        raise ValueError("pre-gap development interval mismatch")
    result = {
        "kind": "OFFLINE_DEVELOPMENT_TRADE_ATTRIBUTION_NOT_PAPER_APPROVAL",
        "dataset_sha256": actual,
        "scope": "PRE-GAP DEVELOPMENT ONLY; NO RESERVED POST-GAP DATA",
        "bucket_definitions": "nonoverlapping: <=6h, >6h and <24h, >=24h",
        "v01": attribute_trades(simulate(bars, as_of=DEVELOPMENT_END, strategy=V01)),
        "v02": attribute_trades(simulate(bars, as_of=DEVELOPMENT_END, strategy=V02)),
        "paper_order_submission": "DISABLED",
        "warning": "Descriptive attribution is not evidence of future profitability.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
