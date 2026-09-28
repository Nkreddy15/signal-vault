"""Predeclared research-only v0.2 comparison on the development segment.

This command DOES NOT load provider credentials, access a network endpoint,
import a paper executor, optimize parameters, or inspect reserved post-gap data.
Its fixed pre-gap dataset SHA was reported by the owner after local capture.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from .backtest import CostAssumptions, simulate
from .market_data import load_csv
from .strategy import StrategyConfig

DEVELOPMENT_CSV = Path("data/research/btcusd_older_pregap.csv")
DEVELOPMENT_SHA256 = "0f31fa3e6226a504db4b60185ae7388ae8979c14e3ccef1fc1b98e2b809071cc"
DEVELOPMENT_END = datetime.fromisoformat("2026-03-12T17:00:00+00:00")
DEVELOPMENT_ROWS = 1843

V01 = StrategyConfig()
V02 = StrategyConfig(
    fast_hours=12,
    slow_hours=26,
    strategy_version="btc-hourly-ema-cross-confirm2-v0.2-RESEARCH-ONLY",
    entry_confirmation_bars=2,
)


def _summary(result) -> dict[str, object]:
    return {
        "strategy_version": result.strategy_version,
        "net_pnl_usd": str(result.net_pnl_usd),
        "passive_same_allocation_net_pnl_usd": str(result.passive_same_allocation_net_pnl_usd),
        "max_drawdown_usd": str(result.max_drawdown_usd),
        "estimated_fees_usd": str(result.total_estimated_fees_usd),
        "fill_count": len(result.fills),
        "rejected_count": len(result.rejected),
        "open_position": result.marked_open_base_qty > 0,
    }


def main() -> int:
    actual = sha256(DEVELOPMENT_CSV.read_bytes()).hexdigest()
    if actual != DEVELOPMENT_SHA256:
        raise ValueError("predeclared development dataset SHA-256 mismatch")
    bars = load_csv(DEVELOPMENT_CSV, as_of=DEVELOPMENT_END, min_count=DEVELOPMENT_ROWS)
    if len(bars) != DEVELOPMENT_ROWS or bars[0].start.isoformat() != "2025-12-25T22:00:00+00:00" or bars[-1].close_time != DEVELOPMENT_END:
        raise ValueError("unexpected development dataset boundaries")
    free = CostAssumptions(taker_fee_rate=Decimal("0"), slippage_rate=Decimal("0"))
    report = {
        "kind": "OFFLINE_PREDECLARED_V02_DEVELOPMENT_DIAGNOSTIC_NOT_PAPER_APPROVAL",
        "dataset_sha256": actual,
        "data_scope": "pre-gap development only; reserved post-gap files are not accessed",
        "hypothesis": "second consecutive positive fully closed hourly EMA state required for BUY",
        "unchanged": "12h/26h EMA; immediate bearish-cross SELL; $15 buys; $100 logical cap; risk policy",
        "cost_model": "0.25% taker fee plus 0.10% slippage per side in costed scenarios",
        "baseline_v01": _summary(simulate(bars, as_of=DEVELOPMENT_END, strategy=V01)),
        "candidate_v02": _summary(simulate(bars, as_of=DEVELOPMENT_END, strategy=V02)),
        "baseline_v01_no_costs": _summary(simulate(bars, as_of=DEVELOPMENT_END, strategy=V01, costs=free)),
        "candidate_v02_no_costs": _summary(simulate(bars, as_of=DEVELOPMENT_END, strategy=V02, costs=free)),
        "paper_order_submission": "DISABLED",
        "warning": "Development diagnostics cannot validate predictive performance. Freeze candidate before any reserved evaluation.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
