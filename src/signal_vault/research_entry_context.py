"""Descriptive, no-lookahead entry-context audit on known development history.

The *outcome* labels use later SELL fills; all reported entry features use
strictly closed bars prior to the hypothetical BUY execution candle. These are
exploratory observations, NOT optimized thresholds or trading instructions.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from statistics import median
from typing import Sequence

from .backtest import BacktestResult, SimulatedFill, simulate
from .market_data import Bar, load_csv
from .research_attribution import attribute_trades
from .research_v02 import (
    DEVELOPMENT_CSV, DEVELOPMENT_SHA256, DEVELOPMENT_END, DEVELOPMENT_ROWS, V01, V02,
)
from .strategy import Action, StrategyConfig, generate_signal

BPS = Decimal("10000")
FIELDS = (
    "ema_spread_bps",
    "prior_6h_close_return_bps",
    "prior_24h_close_return_bps",
    "prior_24h_high_low_range_bps",
    "prior_24h_signed_trend_efficiency",
)


def entry_features(bars: Sequence[Bar], entry_index: int,
                   strategy: StrategyConfig) -> dict[str, Decimal]:
    """Inspect no candle at/after entry_index; the BUY executes at that bar's OPEN.

    Exactly 25 historical closes provide 24 changes for signed efficiency.
    Features should NEVER incorporate the future trade outcome, open candle's
    OHLCV, a future day's data, or post-gap observations.
    """
    if entry_index < max(strategy.slow_hours + 2, 25) or entry_index >= len(bars):
        raise ValueError("insufficient past-only closed history or missing execution candle")
    decision = generate_signal(bars[:entry_index], strategy)
    if decision.action is not Action.BUY:
        raise ValueError("entry-context audit requires a real version-matched BUY signal")
    closed = bars[entry_index - 25:entry_index]
    current = closed[-1].close
    first = closed[0].close
    if current <= 0 or first <= 0:
        raise ValueError("invalid past price")
    range24 = closed[-24:]
    distance = sum(
        (abs(closed[j].close - closed[j - 1].close) for j in range(1, 25)),
        Decimal("0"),
    )
    return {
        "ema_spread_bps": (decision.fast_ema - decision.slow_ema) / current * BPS,
        "prior_6h_close_return_bps": (current / closed[-7].close - 1) * BPS,
        "prior_24h_close_return_bps": (current / first - 1) * BPS,
        "prior_24h_high_low_range_bps": (
            max(bar.high for bar in range24) - min(bar.low for bar in range24)
        ) / current * BPS,
        "prior_24h_signed_trend_efficiency": (
            (current - first) / distance if distance else Decimal("0")
        ),
    }


def _summarize(records: list[tuple[dict[str, Decimal], Decimal, Decimal]]) -> dict:
    return {
        "trade_count": len(records),
        "profitable_count": sum(p > 0 for _, _, p in records),
        "losing_count": sum(p < 0 for _, _, p in records),
        "combined_net_pnl_usd": str(sum((p for _, _, p in records), Decimal("0"))),
        "median_entry_features": {
            key: str(median([features[key] for features, _, _ in records]))
            if records else None for key in FIELDS
        },
    }


def compare_entry_context(bars: Sequence[Bar], result: BacktestResult,
                          strategy: StrategyConfig) -> dict:
    if result.strategy_version != strategy.strategy_version:
        raise ValueError("strategy version mismatch for entry-context audit")
    # Independently validate paired fills, quantities and full P&L reconciliation.
    reference = attribute_trades(result)
    index_by_time = {bar.start.isoformat(): i for i, bar in enumerate(bars)}
    if len(index_by_time) != len(bars):
        raise ValueError("duplicate execution timestamps in research data")
    pending: tuple[SimulatedFill, dict[str, Decimal]] | None = None
    records: list[tuple[dict[str, Decimal], Decimal, Decimal]] = []
    for fill in result.fills:
        if fill.time not in index_by_time:
            raise ValueError("fill timestamp not found in research data")
        if fill.side == "buy":
            if pending is not None:
                raise ValueError("overlapping research buys")
            i = index_by_time[fill.time]
            decision = generate_signal(bars[:i], strategy)
            if fill.evidence_id != decision.evidence_id:
                raise ValueError("BUY evidence does not match past-only strategy signal")
            pending = (fill, entry_features(bars, i, strategy))
        elif fill.side == "sell":
            if pending is None:
                raise ValueError("unpaired research SELL")
            buy, features = pending
            hours = Decimal(str(
                (datetime.fromisoformat(fill.time) -
                 datetime.fromisoformat(buy.time)).total_seconds()
            )) / Decimal("3600")
            pnl = buy.cash_delta + fill.cash_delta
            records.append((features, hours, pnl))
            pending = None
        else:
            raise ValueError("unknown research fill side")
    if len(records) != reference["completed"]["completed_trades"]:
        raise ValueError("entry cohort count does not reconcile")
    if sum((p for _, _, p in records), Decimal("0")) != Decimal(
            reference["completed"]["combined_net_pnl_usd"]):
        raise ValueError("entry cohort P&L does not reconcile")
    return {
        "strategy_version": strategy.strategy_version,
        "closed_bar_entry_features_only": True,
        "total_completed": _summarize(records),
        "observed_winning_trades": _summarize([row for row in records if row[2] > 0]),
        "observed_losing_trades": _summarize([row for row in records if row[2] < 0]),
        "observed_exit_under_24_hours": _summarize([row for row in records if row[1] < 24]),
        "observed_exit_at_least_24_hours": _summarize([row for row in records if row[1] >= 24]),
        "unpaired_open_position_not_labeled_as_winner_or_loser": pending is not None,
        "reconciliation": "PASSED",
        "warning": "Outcome and holding duration are hindsight labels, not entry-time features. Small-sample medians cannot justify a rule.",
    }


def main() -> int:
    actual = sha256(DEVELOPMENT_CSV.read_bytes()).hexdigest()
    if actual != DEVELOPMENT_SHA256:
        raise ValueError("development fingerprint mismatch")
    bars = load_csv(DEVELOPMENT_CSV, as_of=DEVELOPMENT_END, min_count=DEVELOPMENT_ROWS)
    if (len(bars) != DEVELOPMENT_ROWS or
            bars[0].start.isoformat() != "2025-12-25T22:00:00+00:00" or
            bars[-1].close_time != DEVELOPMENT_END):
        raise ValueError("development interval mismatch")
    report = {
        "kind": "OFFLINE_PRE_GAP_ENTRY_CONTEXT_DIAGNOSTIC_NOT_PAPER_APPROVAL",
        "dataset_sha256": actual,
        "data_scope": "SHA-LOCKED PRE-GAP DEVELOPMENT ONLY",
        "features": {
            "ema_spread_bps": "fast-minus-slow EMA divided by last completed close; bps",
            "prior_6h_close_return_bps": "last completed close versus close six hours earlier; bps",
            "prior_24h_close_return_bps": "last completed close versus close 24 hours earlier; bps",
            "prior_24h_high_low_range_bps": "last 24 closed hourly candle high-low range / last close; bps",
            "prior_24h_signed_trend_efficiency": "24-hour net close movement divided by sum absolute hourly close movements; [-1,1]",
        },
        "v01": compare_entry_context(
            bars, simulate(bars, as_of=DEVELOPMENT_END, strategy=V01), V01),
        "v02": compare_entry_context(
            bars, simulate(bars, as_of=DEVELOPMENT_END, strategy=V02), V02),
        "paper_order_submission": "DISABLED",
        "warning": "Descriptive hindsight comparisons cannot establish a predictive edge or support immediate strategy changes.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
