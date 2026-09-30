"""Strictly prospective six-crypto shadow scorecard from immutable receipts.

NO provider/network, credentials, account, broker order or strategy promotion.
The scorecard reconstructs only the CURRENT contiguous six-crypto segment,
verifies every archived pre-outcome shadow against the then-available source
chain, and evaluates fixed hypotheses on ONE shared hypothetical $100 book.

Important chronology:
- 72h bootstrap is retrospective warmup and counts 0 forward hours.
- prospective source hour #1 creates the first precommitted shadow for the
  NEXT hour, but has no outcome for that shadow yet.
- with N prospective source hours, only N-1 shadow decisions have fully
  observed next-hour outcomes.
- therefore 168 source hours is the collection milestone, while 169 source
  hours are needed to observe 168 complete precommitted decision outcomes.

Historical warmup may seed indicators, but all fill/P&L event times are
restricted to the precommitted prospective-shadow evaluation horizon.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .ci_historical_report import SCENARIOS
from .crypto_universe_forward import (
    CRYPTO_SIX, SHARED_VOLUME_SIDECAR_ROOT,
    _audit_chain, _raw_bar, _safe_root, _sha, _utc,
)
from .multi_asset_simulation import ExplicitRoundTripCosts, HYPOTHESES
from .research_universe import candidate
from .shared_research_book import simulate_shared_research_book
from .six_crypto_shadow import FOLDER, _latest_payload

SOURCE_168_HOURS=168
FULLY_SCORED_DECISIONS=168


def _verify_all_current_segment_shadows(
    root:Path,
    active:list[dict[str,object]],
) -> tuple[dict[str,dict[str,object]],int]:
    """Every prospective receipt must have exact immutable pre-outcome shadow."""
    folder=root/FOLDER
    prospective=active[1:]
    if not prospective:
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("historical-only baseline must not have a shadow")
        return {},0
    if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mode&0o077:
        raise ValueError("prospective shadow folder must be private real directory")
    expected_names=set()
    checked={}
    for offset,receipt in enumerate(prospective,start=1):
        close=_utc(datetime.fromisoformat(receipt["closed_hour_utc"]))
        name="shadow-hour-"+close.strftime("%Y%m%dT%H%MZ")+".json"
        expected_names.add(name)
        path=folder/name
        if (path.is_symlink() or not path.is_file() or
                path.stat().st_mode&0o077 or not 0<path.stat().st_size<=2_000_000):
            raise ValueError("missing/insecure immutable prospective shadow")
        stored=json.loads(path.read_bytes())
        # Recompute using ONLY chain available at this shadow's original
        # decision time. Later outcomes are intentionally excluded here.
        expected=_latest_payload(active[:offset+1])
        if expected is None:
            raise ValueError("prospective receipt did not yield a pre-outcome shadow")
        expected["shadow_payload_sha256"]=_sha(expected)
        if stored!=expected:
            raise ValueError("archived pre-outcome shadow differs from source-time reconstruction")
        if stored["latest_universe_source_receipt_SHA256"]!=receipt["receipt_sha256"]:
            raise ValueError("shadow does not bind to exact source receipt")
        checked[close.isoformat()]=stored
    actual={
        item.name for item in folder.iterdir()
        if item.is_file() and not item.is_symlink()
    }
    if actual!=expected_names:
        raise ValueError("missing or unexpected shadow files in current evidence tree")
    return checked,len(prospective)


def _active_datasets(
    active:list[dict[str,object]],
) -> dict[str,tuple]:
    datasets={}
    for symbol in CRYPTO_SIX:
        bars=[]
        for index,receipt in enumerate(active):
            raw=receipt["source_historical_batch"]["bars"][symbol]
            for row in raw:
                original=_raw_bar(row)
                bars.append(replace(original,prospective=(index>0)))
        datasets[symbol]=tuple(bars)
    return datasets


def _scenario_costs(values:dict[str,str]) -> dict[str,ExplicitRoundTripCosts]:
    model=ExplicitRoundTripCosts(
        Decimal(values["taker_fee_bps"]),
        Decimal(values["full_spread_bps"]),
        Decimal(values["slippage_per_side_bps"]))
    return {sym:model for sym in CRYPTO_SIX}


def prospective_shadow_scorecard(
    *,root:Path=SHARED_VOLUME_SIDECAR_ROOT,
) -> dict[str,object]:
    """Offline audit + score only decisions that existed BEFORE their outcomes."""
    base=_safe_root(Path(root))
    chain=_audit_chain(base)
    if not chain:
        return {
            "kind":"OFFLINE_SIX_CRYPTO_PROSPECTIVE_SHADOW_SCORECARD",
            "status":"NO_SIX_CRYPTO_SOURCE_EVIDENCE",
            "current_segment_prospective_source_hours":0,
            "fully_observed_precommitted_decision_intervals":0,
            "network_requests":"NONE",
            "credentials_accessed":"NONE",
            "broker_order_submission":"DISABLED",
            "strategy_promoted":False,
        }
    segment=chain[-1]["segment_index"]
    active=[r for r in chain if r["segment_index"]==segment]
    if (not active or active[0]["event"]!="HISTORICAL_72H_BOOTSTRAP" or
            len(active[0]["source_historical_batch"]["bars"][CRYPTO_SIX[0]])!=72):
        raise ValueError("current segment lacks exact historical-only 72h warmup")
    if any(r["event"]!="ONE_NEW_CONTIGUOUS_PROSPECTIVE_HOUR"
           for r in active[1:]):
        raise ValueError("current segment contains noncontiguous prospective structure")

    shadows,prospective_hours=_verify_all_current_segment_shadows(base,active)
    scorable=max(0,prospective_hours-1)
    common={
        "kind":"OFFLINE_SIX_CRYPTO_PROSPECTIVE_SHADOW_SCORECARD",
        "segment_index":segment,
        "source_chain_last_receipt_sha256":active[-1]["receipt_sha256"],
        "current_segment_prospective_source_hours":prospective_hours,
        "current_segment_prospective_asset_bars":6*prospective_hours,
        "fully_observed_precommitted_decision_intervals":scorable,
        "source_168_consecutive_hour_collection_ready":
            prospective_hours>=SOURCE_168_HOURS,
        "full_168_precommitted_decision_outcomes_ready":
            scorable>=FULLY_SCORED_DECISIONS,
        "historical_72h_warmup_counted_as_prospective":False,
        "latest_shadow_is_not_scored_until_next_hour_arrives":True,
        "all_archived_current_segment_shadows_verified":
            len(shadows)==prospective_hours,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "provider_account_positions_queried":False,
        "broker_order_submission":"DISABLED",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "strategy_promoted":False,
        "future_edge_established":False,
    }
    if prospective_hours==0:
        return {
            **common,
            "status":"HISTORICAL_72H_BASELINE_ONLY_ZERO_PROSPECTIVE",
            "scenarios":{},
        }
    if scorable==0:
        return {
            **common,
            "status":"ONE_PROSPECTIVE_HOUR_SHADOW_PRECOMMITTED_WAITING_FOR_OUTCOME",
            "first_precommitted_shadow_close_utc":
                active[1]["closed_hour_utc"],
            "scenarios":{},
        }

    datasets=_active_datasets(active)
    # Shadow created at close T predicts/acts on bar [T,T+1). The first
    # prospective source bar itself [T0,T1) had no precommitted sidecar
    # shadow because baseline deliberately generated none.
    start=_utc(datetime.fromisoformat(active[1]["closed_hour_utc"]))
    end=_utc(datetime.fromisoformat(active[-1]["closed_hour_utc"]))
    as_of=max(
        _utc(datetime.fromisoformat(r["captured_utc"])) for r in active)
    if not start<end:
        raise ValueError("no fully observed precommitted next-hour outcome")

    scenarios={}
    for label,values in SCENARIOS.items():
        costs=_scenario_costs(values)
        fixed={}
        for hypothesis in HYPOTHESES:
            book=simulate_shared_research_book(
                datasets,
                specs={sym:candidate(sym) for sym in CRYPTO_SIX},
                hypotheses={sym:hypothesis for sym in CRYPTO_SIX},
                assumptions=costs,
                as_of=as_of,
                evaluation_start_utc=start,
                evaluation_end_utc_exclusive=end)
            if book["evaluated_distinct_next_open_event_times"]!=scorable:
                raise ValueError("shared forward replay evaluated wrong number of precommitted outcome intervals")
            # Every actual synthetic fill must reference a signal hash that
            # was archived BEFORE that execution bar's outcome existed.
            verified_fills=0
            for fill in book["synthetic_fills"]:
                event=fill["at_open_utc"]
                if event not in shadows:
                    raise ValueError("fill event has no pre-outcome immutable shadow")
                symbol=fill["symbol"]
                states=shadows[event][
                    "predeclared_flat_and_held_hypothetical_decisions"][
                        symbol][hypothesis.name]
                action="buy" if fill["side"]=="buy" else "sell"
                matches=[
                    record for record in states.values()
                    if record["hypothetical_action"]==action and
                       record["evidence_sha256"]==fill["signal_sha256"]
                ]
                if len(matches)!=1:
                    raise ValueError("synthetic fill was not authorized by one exact archived pre-outcome shadow")
                verified_fills+=1
            fixed[hypothesis.name]={
                "initial_ONE_shared_bankroll_usd":book["initial_bankroll_usd"],
                "max_total_long_exposure_usd":book[
                    "max_total_long_exposure_usd"],
                "evaluated_precommitted_outcome_intervals":
                    book["evaluated_distinct_next_open_event_times"],
                "net_marked_pnl_usd":book["net_marked_pnl_usd"],
                "net_pnl_if_hypothetically_liquidated_usd":
                    book["net_pnl_if_hypothetically_liquidated_usd"],
                "estimated_fee_total_usd":book["estimated_fee_total_usd"],
                "sampled_event_max_drawdown_usd":
                    book["sampled_event_max_drawdown_usd"],
                "synthetic_fill_count":len(book["synthetic_fills"]),
                "synthetic_fills_with_preoutcome_shadow_SHA_verified":
                    verified_fills,
                "open_positions_quantity":book["open_positions_quantity"],
                "rejected_entry_or_fill_count":len(book["rejections"]),
                "persistent_peak_drawdown_entry_halt":
                    book["persistent_peak_drawdown_entry_halt"],
                "utc_daily_entry_pause_dates":
                    book["utc_daily_entry_pause_dates"],
                "strategy_selected_from_forward_outcomes":False,
                "broker_order_submission":"DISABLED",
            }
        scenarios[label]={
            "illustrative_cost_assumptions_not_observed_execution":dict(values),
            "fixed_predeclared_hypotheses":fixed,
        }

    status=(
        "FULL_168_PRECOMMITTED_DECISION_OUTCOMES_AVAILABLE"
        if scorable>=FULLY_SCORED_DECISIONS else
        "PROSPECTIVE_SHADOW_OUTCOMES_ACCUMULATING")
    return {
        **common,
        "status":status,
        "evaluation_start_first_precommitted_shadow_utc":start.isoformat(),
        "evaluation_end_exclusive_latest_observed_close_utc":end.isoformat(),
        "verified_preoutcome_shadow_count":len(shadows),
        "scenarios":scenarios,
        "warning":"Forward observations reduce hindsight risk but remain one short, correlated market sample; no strategy selection or order authorization.",
    }


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="OFFLINE six-crypto pre-outcome shadow scoring; no provider or orders.")
    parser.add_argument("--root",type=Path,default=SHARED_VOLUME_SIDECAR_ROOT)
    args=parser.parse_args(argv)
    try:
        report=prospective_shadow_scorecard(root=args.root)
        okay=True
    except Exception as exc:
        report={
            "kind":"OFFLINE_SIX_CRYPTO_PROSPECTIVE_SHADOW_SCORECARD",
            "status":"BLOCKED_EVIDENCE_OR_SHADOW_AUDIT_FAILED",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "credentials_accessed":"NONE",
            "broker_order_submission":"DISABLED",
            "strategy_promoted":False,
        }
        okay=False
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if okay else 2


if __name__=="__main__":
    raise SystemExit(main())
