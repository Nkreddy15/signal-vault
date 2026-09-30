"""Chronological three-way evaluation for the frozen 50-market Kalshi corpus.

The deterministic corpus is ordered by settlement time from oldest to newest:
30 development markets, 10 validation markets, 10 untouched-test markets.
All Phase 57 hypotheses are reported under every Phase 58 friction scenario.
No hypothesis is ranked, selected, tuned, or promoted from any fold.

This is retrospective historical research only and does not replace a future
prospective/demo validation period.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence

from .kalshi_reference_hypotheses import HYPOTHESES
from .offline_kalshi_strategy_simulation import (
    FRICTION_SCENARIOS,
    simulate_resolved_market_references,
)

REQUIRED_CORPUS_SIZE=50
DEVELOPMENT_MARKETS=30
VALIDATION_MARKETS=10
UNTOUCHED_TEST_MARKETS=10
MAX_FILE_BYTES=20_000_000


def _stamp(raw:object)->datetime:
    if not isinstance(raw,str) or not raw or len(raw)>64:
        raise ValueError("invalid Kalshi settlement timestamp")
    try:
        value=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("invalid Kalshi settlement timestamp") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Kalshi settlement timestamp lacks timezone")
    return value.astimezone(timezone.utc)


def _decimal(raw:object)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid Kalshi hypothetical PnL") from exc
    if not value.is_finite():
        raise ValueError("non-finite Kalshi hypothetical PnL")
    return value


def _summarize_fold(
    items:Sequence[Mapping[str,object]],
    *,
    scenario:str,
    hypothesis_name:str,
)->dict[str,object]:
    total=Decimal(0)
    trades=0
    blocked=0
    positive=0
    negative=0
    zero=0
    for item in items:
        scenarios=item.get("friction_scenarios")
        if not isinstance(scenarios,Mapping):
            raise ValueError("Kalshi simulation missing friction scenarios")
        scenario_result=scenarios.get(scenario)
        if not isinstance(scenario_result,Mapping):
            raise ValueError("Kalshi simulation missing fixed friction scenario")
        hypotheses=scenario_result.get("hypotheses")
        if not isinstance(hypotheses,Mapping):
            raise ValueError("Kalshi simulation missing frozen hypotheses")
        result=hypotheses.get(hypothesis_name)
        if not isinstance(result,Mapping):
            raise ValueError("Kalshi simulation missing frozen hypothesis result")
        pnl=_decimal(result.get("hypothetical_pnl_dollars"))
        count=result.get("hypothetical_contract_count")
        if type(count) is not int or count not in {0,1}:
            raise ValueError("Kalshi simulation contract count outside one-contract rule")
        is_blocked=result.get("entry_blocked")
        if type(is_blocked) is not bool:
            raise ValueError("Kalshi simulation entry-block state missing")
        total+=pnl
        trades+=count
        blocked+=int(is_blocked)
        if pnl>0:
            positive+=1
        elif pnl<0:
            negative+=1
        else:
            zero+=1
    return {
        "market_count":len(items),
        "hypothetical_contract_count":trades,
        "entry_blocked_market_count":blocked,
        "total_hypothetical_pnl_dollars":str(total),
        "mean_hypothetical_pnl_per_market_dollars":
            str(total/Decimal(len(items))),
        "positive_pnl_market_count":positive,
        "negative_pnl_market_count":negative,
        "zero_pnl_market_count":zero,
    }


def chronological_corpus_summary(
    simulations:Sequence[Mapping[str,object]],
)->dict[str,object]:
    items=tuple(simulations)
    if len(items)!=REQUIRED_CORPUS_SIZE:
        raise ValueError("Kalshi chronological research requires exact 50-market corpus")

    seen=set()
    normalized=[]
    for item in items:
        if item.get("kind")!="OFFLINE_KALSHI_FROZEN_REFERENCE_STRATEGY_SIMULATION":
            raise ValueError("unexpected Kalshi strategy simulation kind")
        if (
            item.get("decision_made_before_outcome_scoring") is not True
            or item.get("historical_quote_close_is_not_guaranteed_fill") is not True
            or item.get("historical_orderbook_depth_reconstructed") is not False
            or item.get("provider_fee_schedule_modeled") is not False
            or item.get("strategy_selection_performed") is not False
            or item.get("demo_order_submission")!="DISABLED"
            or item.get("live_order_submission")!="DISABLED"
        ):
            raise ValueError("Kalshi simulation escaped historical research contract")
        ticker=item.get("ticker")
        if not isinstance(ticker,str) or not ticker or ticker in seen:
            raise ValueError("Kalshi chronological corpus requires unique tickers")
        seen.add(ticker)
        settled=_stamp(item.get("settlement_ts"))
        normalized.append((settled,ticker,item))

    normalized.sort(key=lambda x:(x[0],x[1]))
    ordered=[x[2] for x in normalized]
    development=ordered[:DEVELOPMENT_MARKETS]
    validation=ordered[
        DEVELOPMENT_MARKETS:DEVELOPMENT_MARKETS+VALIDATION_MARKETS
    ]
    untouched=ordered[-UNTOUCHED_TEST_MARKETS:]
    folds={
        "development":development,
        "validation":validation,
        "untouched_test":untouched,
    }

    scenarios={}
    expected_names=[x.name for x in HYPOTHESES]
    for scenario in FRICTION_SCENARIOS:
        by_hypothesis={}
        for name in expected_names:
            by_hypothesis[name]={
                fold:_summarize_fold(
                    fold_items,scenario=scenario,hypothesis_name=name
                )
                for fold,fold_items in folds.items()
            }
        scenarios[scenario]={
            "extra_entry_friction_dollars":str(FRICTION_SCENARIOS[scenario]),
            "hypotheses":by_hypothesis,
        }

    return {
        "kind":"OFFLINE_KALSHI_CHRONOLOGICAL_THREE_WAY_RESEARCH",
        "resolved_market_count":len(ordered),
        "chronological_split":{
            "development_markets":DEVELOPMENT_MARKETS,
            "validation_markets":VALIDATION_MARKETS,
            "untouched_test_markets":UNTOUCHED_TEST_MARKETS,
            "oldest_settlement_ts":normalized[0][0].isoformat(),
            "newest_settlement_ts":normalized[-1][0].isoformat(),
        },
        "fixed_hypotheses":expected_names,
        "friction_scenarios":scenarios,
        "chronological_three_way_complete":True,
        "historical_walk_forward_complete":False,
        "untouched_test_used_for_strategy_selection":False,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "hyperparameter_optimization_performed":False,
        "historical_results_are_not_prospective_validation":True,
        "automatic_strategy_promotion":"DISABLED",
        "credentials_accessed":"NONE",
        "network_requests":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def load_captured_kalshi_simulations(
    corpus_root:str|Path,
)->tuple[list[dict[str,object]],str]:
    root=Path(corpus_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Kalshi corpus root must be a real directory")
    manifest_path=root/"manifest.json"
    if (
        manifest_path.is_symlink() or not manifest_path.is_file()
        or not 0<manifest_path.stat().st_size<=MAX_FILE_BYTES
    ):
        raise ValueError("Kalshi corpus manifest missing or unsafe")
    raw=manifest_path.read_bytes()
    manifest=json.loads(raw)
    if (
        not isinstance(manifest,dict)
        or manifest.get("kind")!="IMMUTABLE_KALSHI_RESOLVED_CORPUS_EVIDENCE"
        or manifest.get("sample_size")!=REQUIRED_CORPUS_SIZE
        or manifest.get("credentials_accessed")!="NONE"
        or manifest.get("demo_order_submission")!="DISABLED"
        or manifest.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi captured corpus manifest")
    children=manifest.get("children")
    if not isinstance(children,list) or len(children)!=REQUIRED_CORPUS_SIZE:
        raise ValueError("Kalshi captured corpus child count mismatch")

    simulations=[]
    for expected,item in enumerate(children,1):
        if (
            not isinstance(item,Mapping)
            or item.get("index")!=expected
            or not isinstance(item.get("folder"),str)
            or "/" in item["folder"] or "\\" in item["folder"]
        ):
            raise ValueError("invalid Kalshi child receipt")
        child=root/item["folder"]
        child_manifest=child/"manifest.json"
        if (
            not child_manifest.is_file() or child_manifest.is_symlink()
            or hashlib.sha256(child_manifest.read_bytes()).hexdigest()
               !=item.get("manifest_sha256")
        ):
            raise ValueError("Kalshi child manifest changed after corpus capture")
        simulations.append(simulate_resolved_market_references(child))

    return simulations,hashlib.sha256(raw).hexdigest()


def evaluate_captured_kalshi_corpus(
    corpus_root:str|Path,
)->dict[str,object]:
    simulations,source_sha=load_captured_kalshi_simulations(corpus_root)
    result=chronological_corpus_summary(simulations)
    result["source_corpus_manifest_sha256"]=source_sha
    return result
