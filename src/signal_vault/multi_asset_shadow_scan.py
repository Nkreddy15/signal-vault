"""Offline cross-asset signal snapshots with independent cost-envelope veto.

No strategy execution, no credentials, no clock polling and no broker APIs.
A directional historical EMA/Momentum signal is NOT a calibrated forecast of
the expected next price move. Without prospectively validated expected return
evidence, every BUY remains RESEARCH HOLD, regardless of illustrative fees.
SELL indicates only a possible *risk review for an existing position*, never
permission to sell the separately authorized PAPER BTC diagnostic position.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal, ROUND_UP
from typing import Mapping, Sequence

from .multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES, HypothesisKind, ResearchHypothesis,
    decide_on_prior_closes,
)
from .research_universe import (
    AssetClass, ResearchBar, candidate, validate_asset_dataset,
)
from .strategy import Action

BPS=Decimal("10000")


def illustrative_break_even(
    costs: ExplicitRoundTripCosts,
    *,
    target_margin_bps: Decimal = Decimal("20"),
) -> dict[str,str|bool]:
    if (not isinstance(costs,ExplicitRoundTripCosts) or
            type(target_margin_bps) is not Decimal or
            not target_margin_bps.is_finite() or
            not Decimal("0")<=target_margin_bps<=Decimal("1000")):
        raise ValueError("explicit finite, bounded cost/margin assumptions required")
    fee=costs.taker_fee_bps/BPS
    ratio=(
        (Decimal("1")-fee)**2*
        costs.sell_price_multiplier/costs.buy_price_multiplier)
    if not Decimal("0")<ratio<=Decimal("1"):
        raise ValueError("invalid hypothetical round-trip economics")
    break_even=(Decimal("1")/ratio-Decimal("1"))*BPS
    target=((Decimal("1")+target_margin_bps/BPS)/ratio-Decimal("1"))*BPS
    return {
        "kind":"HYPOTHETICAL_TWO_SIDE_COST_HURDLE_NOT_A_RETURN_FORECAST",
        "break_even_gross_mid_move_bps_up":
            str(break_even.quantize(Decimal("0.01"),rounding=ROUND_UP)),
        "gross_mid_move_for_target_bps_up":
            str(target.quantize(Decimal("0.01"),rounding=ROUND_UP)),
        "required_net_target_bps":str(target_margin_bps),
        "assumptions_are_estimates_not_market_quotes":True,
    }


def offline_universe_shadow_scan(
    datasets: Mapping[str,Sequence[ResearchBar]],
    *,
    as_of: datetime,
    costs: Mapping[str,ExplicitRoundTripCosts],
    equity_calendars: Mapping[str,Sequence[datetime]] | None=None,
    hypotheses:Sequence[ResearchHypothesis]=HYPOTHESES,
    target_margin_bps:Decimal=Decimal("20"),
) -> dict[str,object]:
    """One read-only multi-instrument SHA-linked directional research report.

    The scanner is allowed to inspect only supplied completed asset histories
    and *assumed* costs; it never requests data, sets paper positions, ranks
    assets by expected profit, submits an order or promotes a strategy.
    """
    symbols=tuple(sorted(datasets))
    if (not symbols or len(symbols)>12 or set(symbols)!=set(costs) or
            not hypotheses or len({h.name for h in hypotheses})!=len(hypotheses)):
        raise ValueError("complete bounded universe, per-asset costs and hypotheses required")
    calendars={} if equity_calendars is None else dict(equity_calendars)
    results=[]
    for sym in symbols:
        spec=candidate(sym)
        hist=tuple(datasets[sym])
        review=validate_asset_dataset(
            hist,spec=spec,as_of=as_of,
            expected_session_opens_utc=calendars.get(sym))
        envelope=illustrative_break_even(
            costs[sym],target_margin_bps=target_margin_bps)
        per_version=[]
        for cfg in hypotheses:
            if len(hist)<cfg.warmup_bars:
                raise ValueError("insufficient completed research warmup for "+sym)
            # Independently consider a flat entry scenario and a hypothetical
            # already-held risk-exit scenario, without querying any real account.
            entry=decide_on_prior_closes(
                hist,config=cfg,has_position=False,
                next_open_utc=hist[-1].closed_utc)
            exit_=decide_on_prior_closes(
                hist,config=cfg,has_position=True,
                next_open_utc=hist[-1].closed_utc)
            if cfg.kind in (HypothesisKind.CASH,HypothesisKind.PASSIVE):
                entry_decision="REFERENCE_BASELINE_NO_AUTOMATIC_SIGNALS"
            elif entry.action==Action.BUY:
                entry_decision="HOLD_BUY_VETO_NO_INDEPENDENT_FORWARD_EDGE"
            else:
                entry_decision="HOLD_NO_CURRENT_ENTRY_SIGNAL"
            per_version.append({
                "version":cfg.name,
                "flat_scenario_direction":entry.action.value,
                "held_scenario_direction":exit_.action.value,
                "flat_scenario_signal_evidence_sha256":entry.evidence_sha256,
                "held_scenario_signal_evidence_sha256":exit_.evidence_sha256,
                "cost_aware_research_only_entry":entry_decision,
                "hypothetical_exit_risk_review_only":
                    exit_.action==Action.SELL,
                "independent_prospective_edge_validated":False,
                "broker_order_submission":"DISABLED",
            })
        results.append({
            "symbol":sym,
            "market":spec.asset_class.value,
            "feed":review.feed,
            "dataset_content_sha256":review.content_sha256,
            "historical_and_provisional_prospective_counts":{
                "historical":review.historical_bars,
                "timestamp_plausible_prospective_not_archive_verified":
                    review.prospective_bars,
            },
            "last_fully_closed_bar_utc":hist[-1].closed_utc.isoformat(),
            "last_completed_close":str(hist[-1].close),
            "no_next_execution_timestamp_inferred_for_equity":
                spec.asset_class==AssetClass.US_EQUITY,
            "cost_envelope":envelope,
            "hypotheses":per_version,
        })
    raw=json.dumps(results,sort_keys=True,separators=(",",":"))
    return {
        "kind":"OFFLINE_MULTIMARKET_DIRECTIONAL_SHADOW_SCAN_NO_ORDERS",
        "assets":results,
        "combined_report_sha256":hashlib.sha256(raw.encode()).hexdigest(),
        "complete_history_supplied_externally":True,
        "no_network_or_keychain_requests":True,
        "no_historical_data_upgraded_to_forward_proof":True,
        "no_predictive_asset_ranking":True,
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
