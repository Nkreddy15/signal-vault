"""Predeclared prospective shadow gate for the six-stock lane.

Stocks are validated on their own XNYS core-hour clock, not crypto's 24/7
calendar. This gate is frozen before any future stock outcomes are observed.

Only Phase 69 historically confirmed candidates may enter. The prospective
collector must preserve one complete six-stock grid with at least 60 genuine
future core hours per asset (roughly ten normal sessions), zero historical
backfill, and no gaps hidden inside the accepted segment.

Each fixed candidate is assessed independently against the same passive
benchmark under base and high illustrative friction. Two fixed 30-core-hour
blocks must both be positive and beat passive. No order submission occurs.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .equity_historical_candidate_gate import PASSIVE, REQUIRED_SCENARIOS

POLICY_VERSION="equity-prospective-shadow-gate-v1-predeclared-20260930"
MIN_PROSPECTIVE_CORE_HOURS_PER_ASSET=60
MIN_DISTINCT_XNYS_SESSIONS=10
BLOCK_CORE_HOURS=30
REQUIRED_BLOCKS=2
MIN_CANDIDATE_FILLS=2
MAX_SHARED_DRAWDOWN_USD=Decimal("10")
EXPECTED_SYMBOLS=("AAPL","AMD","MSFT","NVDA","QQQ","SPY")


def _count(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid stock prospective {name}")
    return raw


def _money(raw:object, *, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid stock prospective {name}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite stock prospective {name}")
    return value


def _scenario_checks(
    candidate_obj:Mapping[str,object],
    passive_obj:Mapping[str,object],
)->dict[str,object]:
    fills=_count(
        candidate_obj.get("synthetic_fill_count"),
        name="candidate fill count",
    )
    candidate_pnl=_money(
        candidate_obj.get("net_pnl_if_hypothetically_liquidated_usd"),
        name="candidate total P&L",
    )
    passive_pnl=_money(
        passive_obj.get("net_pnl_if_hypothetically_liquidated_usd"),
        name="passive total P&L",
    )
    drawdown=_money(
        candidate_obj.get("sampled_event_max_drawdown_usd"),
        name="candidate drawdown",
    )
    halt=candidate_obj.get("persistent_peak_drawdown_entry_halt")
    if drawdown<0 or type(halt) is not bool:
        raise ValueError("invalid stock prospective risk state")

    cand_blocks=candidate_obj.get("chronological_blocks")
    passive_blocks=passive_obj.get("chronological_blocks")
    if (
        not isinstance(cand_blocks,list)
        or not isinstance(passive_blocks,list)
        or len(cand_blocks)!=REQUIRED_BLOCKS
        or len(passive_blocks)!=REQUIRED_BLOCKS
    ):
        raise ValueError("stock prospective summary requires two fixed blocks")
    block_checks=[]
    for expected,(cand,base) in enumerate(
        zip(cand_blocks,passive_blocks),1
    ):
        if (
            not isinstance(cand,Mapping)
            or not isinstance(base,Mapping)
            or cand.get("block")!=expected
            or base.get("block")!=expected
            or cand.get("core_hours")!=BLOCK_CORE_HOURS
            or base.get("core_hours")!=BLOCK_CORE_HOURS
        ):
            raise ValueError("stock prospective block clocks differ")
        cand_pnl=_money(
            cand.get("net_pnl_if_hypothetically_liquidated_usd"),
            name="candidate block P&L",
        )
        base_pnl=_money(
            base.get("net_pnl_if_hypothetically_liquidated_usd"),
            name="passive block P&L",
        )
        block_checks.append({
            "block":expected,
            "candidate_pnl_usd":str(cand_pnl),
            "passive_pnl_usd":str(base_pnl),
            "positive_candidate_pnl":cand_pnl>0,
            "candidate_beats_passive":cand_pnl>base_pnl,
            "pass":cand_pnl>0 and cand_pnl>base_pnl,
        })

    checks={
        "minimum_activity":{
            "required_fills":MIN_CANDIDATE_FILLS,
            "observed_fills":fills,
            "pass":fills>=MIN_CANDIDATE_FILLS,
        },
        "positive_total_shadow_pnl":{
            "observed_candidate_pnl_usd":str(candidate_pnl),
            "pass":candidate_pnl>0,
        },
        "beats_passive_total_shadow":{
            "candidate_pnl_usd":str(candidate_pnl),
            "passive_pnl_usd":str(passive_pnl),
            "pass":candidate_pnl>passive_pnl,
        },
        "both_fixed_blocks_positive_and_beat_passive":{
            "blocks":block_checks,
            "pass":all(x["pass"] for x in block_checks),
        },
        "drawdown_within_shared_cap":{
            "maximum_usd":str(MAX_SHARED_DRAWDOWN_USD),
            "observed_usd":str(drawdown),
            "pass":drawdown<=MAX_SHARED_DRAWDOWN_USD,
        },
        "persistent_peak_drawdown_halt_not_triggered":{
            "observed":halt,
            "pass":not halt,
        },
    }
    return {
        "checks":checks,
        "pass":all(x["pass"] for x in checks.values()),
    }


def assess_equity_prospective_shadow(
    historical_confirmation:Mapping[str,object],
    summary:Mapping[str,object],
)->dict[str,object]:
    if (
        historical_confirmation.get("kind")
        !="EQUITY_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER"
        or historical_confirmation.get("candidate_added_by_untouched_test") is not False
        or historical_confirmation.get("candidate_ranking_performed") is not False
        or historical_confirmation.get("automatic_candidate_selection")!="DISABLED"
        or historical_confirmation.get("paper_order_submission")!="DISABLED"
        or historical_confirmation.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid stock historical confirmation receipt")

    confirmed=historical_confirmation.get(
        "candidates_confirmed_on_untouched_test"
    )
    if (
        not isinstance(confirmed,list)
        or any(not isinstance(x,str) or not x for x in confirmed)
        or len(set(confirmed))!=len(confirmed)
    ):
        raise ValueError("invalid historically confirmed stock candidate list")

    if summary.get("kind")!="EQUITY_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS":
        raise ValueError("unexpected stock prospective shadow summary")
    if (
        tuple(summary.get("symbols",()))!=EXPECTED_SYMBOLS
        or summary.get("candidate_versions_changed_after_start") is not False
        or summary.get("historical_backfill_count")!=0
        or summary.get("hidden_gap_or_interpolation_count")!=0
        or summary.get("source_integrity_passed") is not True
        or summary.get("network_methods")!=["GET"]
        or summary.get("broker_order_submission")!="DISABLED"
        or summary.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("stock prospective shadow escaped strict GET-only contract")

    hours=_count(
        summary.get("prospective_core_hours_per_asset"),
        name="core hour count",
    )
    sessions=_count(
        summary.get("distinct_xnys_sessions"),
        name="XNYS session count",
    )
    if summary.get("complete_six_stock_grid_verified") is not True:
        raise ValueError("stock prospective evidence lacks complete six-stock grid")

    global_checks={
        "minimum_prospective_core_hours_per_asset":{
            "required":MIN_PROSPECTIVE_CORE_HOURS_PER_ASSET,
            "observed":hours,
            "pass":hours>=MIN_PROSPECTIVE_CORE_HOURS_PER_ASSET,
        },
        "minimum_distinct_xnys_sessions":{
            "required":MIN_DISTINCT_XNYS_SESSIONS,
            "observed":sessions,
            "pass":sessions>=MIN_DISTINCT_XNYS_SESSIONS,
        },
        "complete_six_stock_grid":{
            "observed":True,
            "pass":True,
        },
        "no_historical_backfill_or_hidden_gaps":{
            "historical_backfill_count":0,
            "hidden_gap_or_interpolation_count":0,
            "pass":True,
        },
    }
    global_pass=all(x["pass"] for x in global_checks.values())

    results=summary.get("candidate_results")
    passive=summary.get("passive_benchmark_results")
    if not isinstance(results,Mapping) or not isinstance(passive,Mapping):
        raise ValueError("stock prospective summary lacks candidate/passive results")
    if any(name not in confirmed for name in results):
        raise ValueError("prospective stock summary contains unconfirmed candidate")
    if any(name not in results for name in confirmed):
        raise ValueError("historically confirmed stock candidate missing prospective result")

    assessments={}
    passed=[]
    for candidate in confirmed:
        candidate_obj=results[candidate]
        if not isinstance(candidate_obj,Mapping):
            raise ValueError("malformed stock prospective candidate result")
        scenario_results={}
        for scenario in REQUIRED_SCENARIOS:
            cand_scenario=candidate_obj.get(scenario)
            passive_scenario=passive.get(scenario)
            if not isinstance(cand_scenario,Mapping) or not isinstance(passive_scenario,Mapping):
                raise ValueError("stock prospective result lacks required friction scenario")
            checked=_scenario_checks(cand_scenario,passive_scenario)
            scenario_results[scenario]=checked
        candidate_pass=global_pass and all(
            x["pass"] for x in scenario_results.values()
        )
        assessments[candidate]={
            "scenarios":scenario_results,
            "prospective_shadow_complete":candidate_pass,
        }
        if candidate_pass:
            passed.append(candidate)

    return {
        "kind":"EQUITY_PROSPECTIVE_SHADOW_GATE_NO_ORDER",
        "policy_version":POLICY_VERSION,
        "global_checks":global_checks,
        "historically_confirmed_candidates":list(confirmed),
        "assessments":assessments,
        "candidates_passing_prospective_shadow":passed,
        "candidate_added_by_prospective_results":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "prospective_or_shadow_complete":bool(passed),
        "historical_data_substituted_for_prospective_evidence":False,
        "next_action":(
            "PAPER_EXECUTION_VALIDATION_AND_OWNER_REVIEW_REMAIN_REQUIRED"
            if passed else
            "CONTINUE_PROSPECTIVE_STOCK_SHADOW_COLLECTION"
        ),
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "owner_live_authorization_recorded":False,
        "live_trading":"UNAVAILABLE",
    }
