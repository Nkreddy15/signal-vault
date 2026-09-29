"""OFFLINE twelve-instrument mixed-calendar ONE-$100 common-history research.

Requires separately SHA-verified historical DATA source bundles for all SIX
supported crypto markets AND all SIX XNYS stock/ETF CORE-hour IEX markets,
with at least 48 *SAME UTC CLOCK* closed candles. The two historical studies
may be compared as a joint $100 hypothesis only AFTER every participating
instrument has completed its own indicator warmup; the common horizon
ends when the shortest complete market dataset ends.

No provider calls, API keys, stock order fractional eligibility, account
query, paper order, live mode, optimum selection or capital allocation
recommendations. Research is historical and preliminary.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from decimal import Decimal
from typing import Mapping,Sequence

from .ci_historical_equities import EQUITY_ESTIMATED_COST_SCENARIOS
from .ci_historical_report import SCENARIOS as CRYPTO_COST_SCENARIOS
from .historical_clock_overlap import historical_clock_compatibility
from .multi_asset_simulation import (
    ExplicitRoundTripCosts,HYPOTHESES,
)
from .research_universe import (
    AssetClass, ResearchBar, RESEARCH_CANDIDATES,
    candidate, validate_asset_dataset,
)
from .shared_research_book import (
    SharedResearchLimits, simulate_shared_research_book,
)

CRYPTO_SIX=tuple(sorted(
    a.symbol for a in RESEARCH_CANDIDATES
    if a.asset_class == AssetClass.CRYPTO))
STOCK_SIX=tuple(sorted(
    a.symbol for a in RESEARCH_CANDIDATES
    if a.asset_class == AssetClass.US_EQUITY))
FRICTION_LABELS=("low","base","high")


def evaluate_predeclared_twelve_market_common_history(
    *,
    crypto: Mapping[str,Sequence[ResearchBar]],
    equities: Mapping[str,Sequence[ResearchBar]],
    independently_verified_stock_core_opens_utc: Sequence[datetime],
    as_of: datetime,
    limits:SharedResearchLimits=SharedResearchLimits(),
) -> dict[str,object]:
    """Strict precondition: do not join retrospective studies with zero overlap."""
    if (set(crypto)!=set(CRYPTO_SIX) or set(equities)!=set(STOCK_SIX)):
        raise ValueError("exactly six approved historical crypto and six stock sources required")
    if (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("common as_of must be timezone-aware")
    observed=as_of.astimezone(timezone.utc)
    crypto_rows={sym:tuple(crypto[sym]) for sym in CRYPTO_SIX}
    stock_rows={sym:tuple(equities[sym]) for sym in STOCK_SIX}
    stock_grid=tuple(independently_verified_stock_core_opens_utc)
    quality={}
    for sym,rows in crypto_rows.items():
        quality[sym]=validate_asset_dataset(
            rows,spec=candidate(sym),as_of=observed)
        if quality[sym].prospective_bars:
            raise ValueError("mixed experiment permits verified historical data ONLY")
    crypto_starts={rows[0].start_utc for rows in crypto_rows.values()}
    crypto_ends={rows[-1].closed_utc for rows in crypto_rows.values()}
    if len(crypto_starts)!=1 or len(crypto_ends)!=1:
        raise ValueError("the six-crypto common history window must be complete and equal")
    for sym,rows in stock_rows.items():
        quality[sym]=validate_asset_dataset(
            rows,spec=candidate(sym),as_of=observed,
            expected_session_opens_utc=stock_grid)
        if quality[sym].prospective_bars:
            raise ValueError("mixed experiment permits verified historical data ONLY")
    diagnostic=historical_clock_compatibility(
        continuous_crypto_start_utc=next(iter(crypto_starts)),
        continuous_crypto_end_utc_exclusive=next(iter(crypto_ends)),
        independently_verified_stock_core_opens_utc=stock_grid)
    if not diagnostic["basic_clock_alignment_ready"]:
        raise ValueError(
            "NO_VALID_TWELVE_ASSET_COMMON_HISTORICAL_HORIZON:"+
            diagnostic["reason_code"])
    datasets={**crypto_rows,**stock_rows}
    earliest=max(rows[max(h.warmup_bars for h in HYPOTHESES)].start_utc
                 for rows in datasets.values())
    latest=min(rows[-1].closed_utc for rows in datasets.values())
    if not earliest<latest:
        raise ValueError("no closed post-indicator common horizon")
    # Every XNYS stock is required to share the independent actual source
    # core-grid; no crypto candle is interpolated at a stock-market gap.
    evaluated_stock_opens=tuple(
        t for t in stock_grid if earliest<=t and t+timedelta(hours=1)<=latest)
    if len(evaluated_stock_opens)<24:
        raise ValueError("insufficient post-warmup synchronized stock CORE hours")
    scenario_results={}
    names=tuple(sorted(datasets))
    per_class={sym:candidate(sym).asset_class for sym in names}
    for label in FRICTION_LABELS:
        crypto_model=CRYPTO_COST_SCENARIOS["illustrative_"+label+"_friction"]
        stock_model=EQUITY_ESTIMATED_COST_SCENARIOS[
            "illustrative_"+label+"_equity_friction"]
        costs={
            sym:ExplicitRoundTripCosts(
                Decimal((stock_model if per_class[sym]==AssetClass.US_EQUITY
                         else crypto_model)["taker_fee_bps"]),
                Decimal((stock_model if per_class[sym]==AssetClass.US_EQUITY
                         else crypto_model)["full_spread_bps"]),
                Decimal((stock_model if per_class[sym]==AssetClass.US_EQUITY
                         else crypto_model)["slippage_per_side_bps"]))
            for sym in names
        }
        strategies={}
        for hypothesis in HYPOTHESES:
            outcome=simulate_shared_research_book(
                datasets,specs={sym:candidate(sym) for sym in names},
                hypotheses={sym:hypothesis for sym in names},
                assumptions=costs,as_of=observed,
                equity_calendars={sym:stock_grid for sym in STOCK_SIX},
                limits=limits,
                evaluation_start_utc=earliest,
                evaluation_end_utc_exclusive=latest)
            if not outcome["global_common_horizon_applied"]:
                raise ValueError("cross-class report must not use old unscoped book")
            strategies[hypothesis.name]={
                "initial_SHARED_bankroll_usd":outcome["initial_bankroll_usd"],
                "combined_12_market_exposure_cap_usd":
                    outcome["max_total_long_exposure_usd"],
                "hypothetical_exit_inclusive_pnl_usd":
                    outcome["net_pnl_if_hypothetically_liquidated_usd"],
                "estimated_fees_usd":outcome["estimated_fee_total_usd"],
                "sampled_max_marked_drawdown_usd":
                    outcome["sampled_event_max_drawdown_usd"],
                "hypothetical_open_position_symbols":
                    sorted(outcome["open_positions_quantity"]),
                "synthetic_fills":outcome["synthetic_fills"],
                "rejected_synthetic_allocation_requests_count":
                    len(outcome["rejections"]),
                "closed_bar_decisions_by_symbol":outcome["signal_counts"],
                "actual_order_submissions":0,
                "broker_order_submission":"DISABLED",
            }
        scenario_results["illustrative_"+label+"_friction"]={
            "crypto_cost_assumptions":dict(crypto_model),
            "stock_IEX_cost_assumptions":dict(stock_model),
            "prices_fees_spreads_and_fractional_shares_NOT_verified_fills":True,
            "predeclared_hypothesis_results":strategies,
        }
    return {
        "kind":"OFFLINE_SYNCHRONIZED_TWELVE_ASSET_MIXED_CALENDAR_RESEARCH",
        "twelve_source_data_sha256":{
            sym:quality[sym].content_sha256 for sym in names},
        "crypto_symbols":list(CRYPTO_SIX),
        "stock_symbols":list(STOCK_SIX),
        "market_feed_by_symbol":{sym:quality[sym].feed for sym in names},
        "continuous_six_crypto_dataset_and_stock_XNYS_calendar_validated":True,
        "stock_and_crypto_time_compatibility":diagnostic,
        "global_common_indicator_warmup_complete_before_first_fill":True,
        "common_research_start_utc":earliest.isoformat(),
        "common_research_end_utc_exclusive":latest.isoformat(),
        "evaluated_stock_regular_CORE_hour_opens_after_global_warmup":
            len(evaluated_stock_opens),
        "twelve_assets_available_for_signal_not_twelve_simultaneous_allocations":True,
        "one_SHARED_100_usd_cash_not_twelve_times_100":True,
        "max_combined_long_exposure_usd":str(limits.maximum_total_long_exposure_usd),
        "three_estimated_friction_scenarios":scenario_results,
        "historical_no_new_prospective_observations":True,
        "first_partial_stock_hour_excluded":True,
        "stock_fractional_share_eligibility_and_real_spreads_unverified":True,
        "IEX_single_exchange_not_consolidated_SIP":True,
        "no_strategy_chosen_from_test_results":True,
        "future_edge_established":False,
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
