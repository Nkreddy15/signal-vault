"""Shared-$100 chronological three-way research for the six-stock lane.

This module creates one common XNYS evaluation clock after a fixed warmup and
splits ONLY the later evaluation period into development, validation and
untouched-test folds. Each predeclared hypothesis uses one shared $100 research
book across AAPL/AMD/MSFT/NVDA/QQQ/SPY under each fixed friction scenario.

The untouched fold is reported but never used here to select/rank/tune a
hypothesis. Historical research remains no-order and is not prospective proof.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .ci_historical_equities import EQUITY_ESTIMATED_COST_SCENARIOS, SYMBOLS
from .multi_asset_simulation import ExplicitRoundTripCosts, HYPOTHESES
from .offline_equity_walk_forward import _reload_phase48_verified_source
from .offline_long_equity_validation import validate_long_equity_history
from .research_universe import ResearchBar, candidate
from .shared_research_book import simulate_shared_research_book

WARMUP_CORE_HOURS=60
MIN_EVALUATION_CORE_HOURS=120
DEVELOPMENT_FRACTION=Decimal("0.60")
VALIDATION_FRACTION=Decimal("0.20")


def _fold_bounds(
    timeline:Sequence[datetime],
)->dict[str,tuple[int,int]]:
    total=len(timeline)
    if total<WARMUP_CORE_HOURS+MIN_EVALUATION_CORE_HOURS:
        raise ValueError("long equity history is too short for shared three-way research")
    evaluation=total-WARMUP_CORE_HOURS
    development=max(1,int(Decimal(evaluation)*DEVELOPMENT_FRACTION))
    validation=max(1,int(Decimal(evaluation)*VALIDATION_FRACTION))
    untouched=evaluation-development-validation
    if untouched<1:
        raise ValueError("stock three-way split leaves no untouched test")
    dev_start=WARMUP_CORE_HOURS
    dev_end=dev_start+development
    val_end=dev_end+validation
    return {
        "development":(dev_start,dev_end),
        "validation":(dev_end,val_end),
        "untouched_test":(val_end,total),
    }


def shared_equity_three_way_research(
    datasets:Mapping[str,Sequence[ResearchBar]],
    *,
    timeline:Sequence[datetime],
    as_of:datetime,
)->dict[str,object]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("stock three-way as_of must be timezone-aware")
    checked=as_of.astimezone(timezone.utc)
    grid=tuple(timeline)
    if (
        grid!=tuple(sorted(set(grid)))
        or any(x.tzinfo is None or x.utcoffset() is None for x in grid)
    ):
        raise ValueError("verified XNYS common clock must be sorted and unique")
    if set(datasets)!=set(SYMBOLS):
        raise ValueError("shared stock research requires exact six-stock universe")
    rows={symbol:tuple(datasets[symbol]) for symbol in SYMBOLS}
    if any(
        len(rows[symbol])!=len(grid)
        or tuple(bar.start_utc for bar in rows[symbol])!=grid
        for symbol in SYMBOLS
    ):
        raise ValueError("every stock must match the same verified XNYS core-hour grid")

    bounds=_fold_bounds(grid)
    scenarios={}
    for scenario_name,raw_costs in EQUITY_ESTIMATED_COST_SCENARIOS.items():
        costs=ExplicitRoundTripCosts(
            Decimal(raw_costs["taker_fee_bps"]),
            Decimal(raw_costs["full_spread_bps"]),
            Decimal(raw_costs["slippage_per_side_bps"]),
        )
        hypothesis_reports={}
        for hypothesis in HYPOTHESES:
            fold_reports={}
            for fold,(start_index,end_index) in bounds.items():
                start=grid[start_index]
                end_exclusive=grid[end_index-1]+timedelta(hours=1)
                book=simulate_shared_research_book(
                    rows,
                    specs={symbol:candidate(symbol) for symbol in SYMBOLS},
                    hypotheses={symbol:hypothesis for symbol in SYMBOLS},
                    assumptions={symbol:costs for symbol in SYMBOLS},
                    as_of=checked,
                    equity_calendars={symbol:grid for symbol in SYMBOLS},
                    evaluation_start_utc=start,
                    evaluation_end_utc_exclusive=end_exclusive,
                )
                if (
                    book.get("broker_order_submission")!="DISABLED"
                    or book.get("live_trading")!="UNAVAILABLE"
                    or book.get("past_data_does_not_prove_strategy_edge") is not True
                ):
                    raise ValueError("shared stock fold escaped research-only contract")
                fold_reports[fold]={
                    "evaluation_start_utc":start.isoformat(),
                    "evaluation_end_utc_exclusive":end_exclusive.isoformat(),
                    "evaluation_core_hours":end_index-start_index,
                    "net_pnl_if_hypothetically_liquidated_usd":
                        book["net_pnl_if_hypothetically_liquidated_usd"],
                    "sampled_event_max_drawdown_usd":
                        book["sampled_event_max_drawdown_usd"],
                    "synthetic_fill_count":len(book["synthetic_fills"]),
                    "persistent_peak_drawdown_entry_halt":
                        book["persistent_peak_drawdown_entry_halt"],
                    "historical_assets_sha256":
                        book["historical_assets_sha256"],
                }
            hypothesis_reports[hypothesis.name]=fold_reports
        scenarios[scenario_name]={
            "assumptions":dict(raw_costs),
            "hypotheses":hypothesis_reports,
        }

    return {
        "kind":"OFFLINE_SHARED_SIX_STOCK_CHRONOLOGICAL_THREE_WAY_RESEARCH",
        "symbols":list(SYMBOLS),
        "feed":"alpaca_equity_iex",
        "verified_core_hours_per_asset":len(grid),
        "warmup_core_hours":WARMUP_CORE_HOURS,
        "fold_core_hours":{
            fold:end-start for fold,(start,end) in bounds.items()
        },
        "three_fixed_friction_scenarios":scenarios,
        "predeclared_hypotheses":[x.name for x in HYPOTHESES],
        "shared_bankroll_usd":"100",
        "untouched_test_used_for_strategy_selection":False,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "hyperparameter_optimization_performed":False,
        "historical_results_are_not_prospective_validation":True,
        "automatic_strategy_promotion":"DISABLED",
        "credentials_accessed":"NONE",
        "network_requests":"NONE",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def validate_long_equity_shared_three_way(
    source_root:str|Path,
    *,
    as_of:datetime,
)->dict[str,object]:
    root=Path(source_root)
    baseline=validate_long_equity_history(root,as_of=as_of)
    datasets,timeline=_reload_phase48_verified_source(
        root,baseline=baseline,as_of=as_of
    )
    result=shared_equity_three_way_research(
        datasets,timeline=timeline,as_of=as_of
    )
    result["phase48_source_manifest_sha256"]=baseline[
        "source_manifest_sha256"
    ]
    result["phase48_source_replay_completed_first"]=True
    return result
