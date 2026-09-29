"""OFFLINE multi-asset basket sensitivity and return co-movement diagnostics.

A shared risk cap lets only two $15 passive entries into the existing $30
sandbox on the first eligible hourly bar. The legacy deterministic alphabetical
tie-break admits the first two symbols, which is a *simulation convention*,
NOT a comparison of every asset or a signal to buy those symbols.

This module displays ALL two-asset hypothetical combinations against the
same capital/cost/time assumptions, without selecting or ranking a winner.
Hourly return correlations are descriptive, not independent samples, alpha,
risk-model calibration, future predictions or trading permissions.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import statistics
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Mapping, Sequence

from .multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES, HypothesisKind,
)
from .research_universe import AssetClass, ResearchBar, candidate, validate_asset_dataset

BASE_BANKROLL = Decimal("100")
SINGLE_ALLOCATION = Decimal("15")
MAX_TWO_ALLOCATION = Decimal("30")
FIRST_ELIGIBLE_BAR_INDEX = max(HYPOTHESES[1].warmup_bars, 2)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def _cost(value: ExplicitRoundTripCosts) -> dict[str, str]:
    if not isinstance(value, ExplicitRoundTripCosts):
        raise ValueError("an explicit per-asset estimated cost model is required")
    return {
        "taker_fee_bps_each_side": str(value.taker_fee_bps),
        "full_spread_bps": str(value.full_spread_bps),
        "slippage_per_side_bps": str(value.slippage_per_side_bps),
    }


def _corr(a: Sequence[float], b: Sequence[float]) -> float | None:
    if len(a) != len(b) or len(a) < 24:
        raise ValueError("return series must have >=24 exactly aligned observations")
    # A flat series has no measurable Pearson correlation.
    avg_a = statistics.fmean(a)
    avg_b = statistics.fmean(b)
    da = [v - avg_a for v in a]
    db = [v - avg_b for v in b]
    saa = math.fsum(v * v for v in da)
    sbb = math.fsum(v * v for v in db)
    if saa == 0 or sbb == 0:
        return None
    result = math.fsum(x*y for x, y in zip(da, db)) / math.sqrt(saa*sbb)
    return round(max(-1.0, min(1.0, result)), 6)


def all_pair_passive_diagnostics(
    datasets: Mapping[str, Sequence[ResearchBar]],
    *,
    as_of: datetime,
    costs: Mapping[str, ExplicitRoundTripCosts],
) -> dict[str, object]:
    """Inspect fixed-budget, fully closed historical crypto baskets.

    All six symbols must use the same exact hourly UTC timeline and provider
    provenance. Each of the 15 pair scenarios receives a separately reset
    $100 sandbox, spends only $15 on each member at its first eligible next
    OPEN, keeps $70 cash, never rebalances, then computes hypothetical
    liquidation of both remaining positions at the final closed mark.

    Pair scenarios are PARALLEL ALTERNATIVES, not 15 concurrent allocations
    of the same bankroll; correlation shares the SAME 1,487 clock hours.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("timezone-aware historical as_of required")
    names = tuple(sorted(datasets))
    if not 2 <= len(names) <= 12 or set(names) != set(costs):
        raise ValueError("2-12 declared crypto assets and full cost models required")
    if SINGLE_ALLOCATION * 2 != MAX_TWO_ALLOCATION:
        raise ValueError("fixed 15+15 allocation must fit exact $30 exposure cap")
    reviewed = {}
    seq = {}
    common_times = None
    common_feed = None
    for symbol in names:
        spec = candidate(symbol)
        if spec.asset_class != AssetClass.CRYPTO:
            raise ValueError("equities require separately verified session-based diagnostics")
        rows = tuple(datasets[symbol])
        report = validate_asset_dataset(rows, spec=spec, as_of=as_of)
        if len(rows) <= FIRST_ELIGIBLE_BAR_INDEX + 24:
            raise ValueError("insufficient contiguous post-warmup historical observations")
        times = tuple(bar.start_utc for bar in rows)
        if common_times is None:
            common_times = times
        elif times != common_times:
            raise ValueError("do not correlate or pool misaligned hourly market data")
        if common_feed is None:
            common_feed = report.feed
        elif report.feed != common_feed:
            raise ValueError("do not silently combine provider feeds")
        _cost(costs[symbol])
        if report.prospective_bars:
            raise ValueError("this historical-only diagnostic cannot label bars forward")
        seq[symbol] = rows
        reviewed[symbol] = report

    returns: dict[str, list[float]] = {}
    for sym in names:
        r = seq[sym]
        returns[sym] = [
            float((r[i].close / r[i-1].close - Decimal("1")) * Decimal("100"))
            for i in range(1, len(r))
        ]
    correlations = []
    scenarios = []
    for a, b in itertools.combinations(names, 2):
        correlation = _corr(returns[a], returns[b])
        correlations.append({
            "symbols": [a, b],
            "hourly_close_return_pearson": correlation,
            "aligned_close_return_observations": len(returns[a]),
        })
        # This is passive hypothetical allocation, no future-open decision
        # and no actual Alpaca order. $70 remains uninvested in every pair.
        qty = {}
        entry = {}
        exit_estimate = {}
        for sym in (a, b):
            friction = costs[sym]
            price = seq[sym][FIRST_ELIGIBLE_BAR_INDEX].open
            entry_fee = SINGLE_ALLOCATION * friction.taker_fee_bps / Decimal("10000")
            quantity = (SINGLE_ALLOCATION - entry_fee) / (
                price * friction.buy_price_multiplier
            )
            qty[sym] = quantity
            entry[sym] = {
                "reference_open": str(price),
                "modeled_initial_spend_usd": str(SINGLE_ALLOCATION),
                "modeled_fee_usd": str(entry_fee),
                "quantity_hypothetical": str(quantity),
            }
            closing_mark = seq[sym][-1].close
            exit_estimate[sym] = (
                quantity * closing_mark * friction.sell_price_multiplier *
                (Decimal("1") - friction.taker_fee_bps / Decimal("10000"))
            )
        gross_final = (BASE_BANKROLL - MAX_TWO_ALLOCATION) + sum(
            (qty[sym] * seq[sym][-1].close for sym in (a, b)), Decimal("0")
        )
        final_liquidated = (BASE_BANKROLL - MAX_TWO_ALLOCATION) + sum(
            exit_estimate.values(), Decimal("0")
        )
        scenarios.append({
            "symbols": [a, b],
            "hypothetical_uninvested_cash_usd": "70",
            "modeled_entry_usd_per_symbol": "15",
            "modeled_two_entries_usd": "30",
            "first_eligible_reference_open_utc":
                seq[a][FIRST_ELIGIBLE_BAR_INDEX].start_utc.isoformat(),
            "final_closed_mark_utc": seq[a][-1].closed_utc.isoformat(),
            "estimated_final_marked_equity_usd": _money(gross_final),
            "estimated_final_liquidated_equity_usd": _money(final_liquidated),
            "modeled_net_pnl_if_liquidated_usd":
                _money(final_liquidated - BASE_BANKROLL),
            "unrounded_net_pnl_if_liquidated_usd":
                str(final_liquidated - BASE_BANKROLL),
            "estimated_entry": entry,
            "broker_order_submission": "DISABLED",
        })
    all_values = [
        Decimal(pair["unrounded_net_pnl_if_liquidated_usd"])
        for pair in scenarios
    ]
    sorted_values = sorted(all_values)
    mid = len(sorted_values) // 2
    median = (sorted_values[mid] if len(sorted_values) % 2
              else (sorted_values[mid-1] + sorted_values[mid]) / 2)
    sha = {
        symbol: reviewed[symbol].content_sha256 for symbol in names
    }
    evidence = {
        "kind": "OFFLINE_ALL_PAIR_PASSIVE_AND_CORRELATION_RESEARCH_NOT_TRADING",
        "model_version": "passive_pair_15_plus_15_from_same_next_open_v1",
        "assets": list(names),
        "historical_source_sha256": sha,
        "provider_feed": common_feed,
        "aligned_historical_hourly_candles_per_asset": len(common_times),
        "distinct_shared_close_return_hours": len(common_times) - 1,
        "initial_bankroll_usd_per_ALTERNATIVE_scenario": "100",
        "each_pair_invested_usd": "30",
        "each_pair_residual_cash_usd": "70",
        "alphabetical_pair_represented_by_old_passive_baseline":
            [names[0], names[1]],
        "previous_passive_book_was_not_a_six_asset_index": True,
        "all_pair_scenarios": scenarios,
        "all_pair_summary_usd": {
            "scenario_count": len(scenarios),
            "minimum_modeled_exit_inclusive_pnl": _money(sorted_values[0]),
            "median_modeled_exit_inclusive_pnl": _money(median),
            "maximum_modeled_exit_inclusive_pnl": _money(sorted_values[-1]),
        },
        "pairwise_hourly_close_return_correlations": correlations,
        "pair_correlations_are_not_independent_market_samples": True,
        "not_a_tradable_diversified_six_coin_benchmark": True,
        "history_does_not_prove_alpha": True,
        "asset_selection_based_on_test_period": False,
        "historical_not_prospective_evidence": True,
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }
    digest = hashlib.sha256(
        (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n")
        .encode("utf-8")
    ).hexdigest()
    return {**evidence, "research_report_sha256": digest}
