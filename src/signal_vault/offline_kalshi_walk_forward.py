"""Expanding walk-forward historical evaluation for frozen Kalshi references.

Uses the exact 50-market deterministic corpus ordered by settlement time.
Fold 1: first 20 markets are prior context, next 10 are evaluated.
Fold 2: first 30 are prior context, next 10 are evaluated.
Fold 3: first 40 are prior context, final 10 are evaluated.

The hypotheses and friction scenarios are frozen before these folds. No result
from an earlier fold changes later decisions, thresholds, candidates, or market
selection. This remains retrospective history, not prospective/demo evidence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from .kalshi_reference_hypotheses import HYPOTHESES
from .offline_kalshi_chronological_research import (
    REQUIRED_CORPUS_SIZE,
    _stamp,
    _summarize_fold,
    load_captured_kalshi_simulations,
)
from .offline_kalshi_strategy_simulation import FRICTION_SCENARIOS

INITIAL_CONTEXT_MARKETS=20
VALIDATION_BLOCK_MARKETS=10
STEP_MARKETS=10


def expanding_kalshi_walk_forward(
    simulations:Sequence[Mapping[str,object]],
)->dict[str,object]:
    items=tuple(simulations)
    if len(items)!=REQUIRED_CORPUS_SIZE:
        raise ValueError("Kalshi walk-forward requires exact 50-market corpus")

    normalized=[]
    seen=set()
    for item in items:
        if item.get("kind")!="OFFLINE_KALSHI_FROZEN_REFERENCE_STRATEGY_SIMULATION":
            raise ValueError("unexpected Kalshi simulation kind")
        if (
            item.get("decision_made_before_outcome_scoring") is not True
            or item.get("strategy_selection_performed") is not False
            or item.get("demo_order_submission")!="DISABLED"
            or item.get("live_order_submission")!="DISABLED"
        ):
            raise ValueError("Kalshi walk-forward input escaped research contract")
        ticker=item.get("ticker")
        if not isinstance(ticker,str) or not ticker or ticker in seen:
            raise ValueError("Kalshi walk-forward requires unique market tickers")
        seen.add(ticker)
        normalized.append((_stamp(item.get("settlement_ts")),ticker,item))
    normalized.sort(key=lambda x:(x[0],x[1]))
    ordered=[x[2] for x in normalized]

    folds=[]
    context_end=INITIAL_CONTEXT_MARKETS
    fold_index=1
    while context_end+VALIDATION_BLOCK_MARKETS<=len(ordered):
        start=context_end
        end=start+VALIDATION_BLOCK_MARKETS
        validation=ordered[start:end]
        folds.append({
            "fold":fold_index,
            "prior_context_market_count":context_end,
            "validation_market_count":len(validation),
            "validation_first_settlement_ts":
                _stamp(validation[0]["settlement_ts"]).isoformat(),
            "validation_last_settlement_ts":
                _stamp(validation[-1]["settlement_ts"]).isoformat(),
            "items":validation,
        })
        context_end+=STEP_MARKETS
        fold_index+=1

    if len(folds)!=3:
        raise AssertionError("fixed 50-market Kalshi walk-forward must create three folds")

    scenarios={}
    for scenario in FRICTION_SCENARIOS:
        hypotheses={}
        for hypothesis in HYPOTHESES:
            fold_results=[]
            for fold in folds:
                summary=_summarize_fold(
                    fold["items"],
                    scenario=scenario,
                    hypothesis_name=hypothesis.name,
                )
                fold_results.append({
                    "fold":fold["fold"],
                    "prior_context_market_count":
                        fold["prior_context_market_count"],
                    "validation_market_count":
                        fold["validation_market_count"],
                    "validation_first_settlement_ts":
                        fold["validation_first_settlement_ts"],
                    "validation_last_settlement_ts":
                        fold["validation_last_settlement_ts"],
                    **summary,
                })
            hypotheses[hypothesis.name]={
                "fold_count":len(fold_results),
                "folds":fold_results,
                "strategy_selected_from_fold_results":False,
                "thresholds_changed_from_fold_results":False,
            }
        scenarios[scenario]={
            "extra_entry_friction_dollars":
                str(FRICTION_SCENARIOS[scenario]),
            "hypotheses":hypotheses,
        }

    return {
        "kind":"OFFLINE_KALSHI_EXPANDING_WALK_FORWARD_RESEARCH",
        "resolved_market_count":len(ordered),
        "initial_context_market_count":INITIAL_CONTEXT_MARKETS,
        "validation_market_count_per_fold":VALIDATION_BLOCK_MARKETS,
        "step_market_count":STEP_MARKETS,
        "fold_count":len(folds),
        "fixed_hypotheses":[x.name for x in HYPOTHESES],
        "friction_scenarios":scenarios,
        "historical_walk_forward_complete":True,
        "historical_walk_forward_is_not_prospective_validation":True,
        "fold_results_used_to_modify_strategy":False,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "hyperparameter_optimization_performed":False,
        "automatic_strategy_promotion":"DISABLED",
        "credentials_accessed":"NONE",
        "network_requests":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def evaluate_captured_kalshi_walk_forward(
    corpus_root:str,
)->dict[str,object]:
    simulations,source_sha=load_captured_kalshi_simulations(corpus_root)
    result=expanding_kalshi_walk_forward(simulations)
    result["source_corpus_manifest_sha256"]=source_sha
    return result
