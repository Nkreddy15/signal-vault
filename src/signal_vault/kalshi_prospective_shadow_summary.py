"""Score frozen Kalshi references on genuine prospective markets.

Consumes only a completed Phase 83 prospective archive audit. Historical
results may determine which already-predeclared hypotheses survived the frozen
historical confirmation gate, but cannot add, rank, or retune candidates here.

Exactly the first 20 valid prospective markets in precommitted chronological
order are evaluated as two fixed 10-market blocks under the same base and high
illustrative friction assumptions used by historical research.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .kalshi_historical_candidate_gate import REQUIRED_SCENARIOS
from .kalshi_prospective_shadow_gate import EXPECTED_HYPOTHESIS_POLICY
from .kalshi_reference_hypotheses import HYPOTHESES, reference_decision
from .offline_kalshi_strategy_simulation import FRICTION_SCENARIOS

EVALUATION_MARKETS=20
BLOCK_MARKETS=10
BLOCKS=2


def _money(raw:object, *, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid Kalshi prospective {name}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite Kalshi prospective {name}")
    return value


def _hypothesis(name:str):
    matches=tuple(x for x in HYPOTHESES if x.name==name)
    if len(matches)!=1:
        raise ValueError("unknown or non-predeclared Kalshi hypothesis")
    return matches[0]


def _chronological_valid_markets(
    audit:Mapping[str,object],
)->tuple[Mapping[str,object],...]:
    rows=audit.get("markets")
    if not isinstance(rows,list):
        raise ValueError("Kalshi prospective audit lacks market rows")
    valid=[]
    for item in rows:
        if not isinstance(item,Mapping):
            raise ValueError("malformed Kalshi prospective audit market")
        if item.get("status")!="VALID_COMPLETE":
            continue
        close=item.get("planned_close_time_utc")
        ticker=item.get("ticker")
        if not isinstance(close,str) or not isinstance(ticker,str):
            raise ValueError("Kalshi prospective market identity/clock missing")
        try:
            datetime.fromisoformat(close)
        except ValueError as exc:
            raise ValueError("invalid Kalshi prospective close timestamp") from exc
        valid.append(item)
    valid.sort(key=lambda x:(str(x["planned_close_time_utc"]),str(x["ticker"])))
    return tuple(valid)


def _simulate_one(
    market:Mapping[str,object],
    *,
    hypothesis_name:str,
    extra_friction:Decimal,
)->dict[str,object]:
    hypothesis=_hypothesis(hypothesis_name)
    horizon=hypothesis.entry_horizon_seconds
    if horizon is None:
        return {
            "hypothetical_contract_count":0,
            "hypothetical_pnl_dollars":"0",
            "entry_blocked":False,
        }
    snapshots=market.get("snapshots")
    settlement=market.get("settlement")
    if not isinstance(snapshots,Mapping) or not isinstance(settlement,Mapping):
        raise ValueError("complete Kalshi prospective market lacks decision/outcome evidence")
    snapshot=snapshots.get(horizon)
    if snapshot is None:
        snapshot=snapshots.get(str(horizon))
    if not isinstance(snapshot,Mapping) or snapshot.get("decision_valid") is not True:
        raise ValueError("valid Kalshi prospective market lacks fixed-horizon decision")
    result=settlement.get("resolved_result")
    if result not in {"yes","no"}:
        raise ValueError("valid Kalshi prospective market lacks binary settlement")

    last=_money(snapshot.get("last_price_dollars"),name="last price")
    if last<0 or last>1:
        raise ValueError("Kalshi last price outside 0..1")
    decision=reference_decision(
        hypothesis,
        yes_trade_probability=last,
    )
    action=decision["action"]
    if action=="hold":
        return {
            "hypothetical_contract_count":0,
            "hypothetical_pnl_dollars":"0",
            "entry_blocked":False,
        }

    bid=_money(snapshot.get("yes_bid_dollars"),name="YES bid")
    ask=_money(snapshot.get("yes_ask_dollars"),name="YES ask")
    if not Decimal("0")<=bid<=ask<=Decimal("1"):
        raise ValueError("Kalshi prospective quote is crossed or outside 0..1")

    if action=="buy_yes":
        reference=ask
        payout=Decimal("1") if result=="yes" else Decimal("0")
    elif action=="buy_no":
        reference=Decimal("1")-bid
        payout=Decimal("1") if result=="no" else Decimal("0")
    else:
        raise ValueError("unexpected Kalshi frozen reference action")
    total_cost=reference+extra_friction
    if total_cost<=0 or total_cost>=1:
        return {
            "hypothetical_contract_count":0,
            "hypothetical_pnl_dollars":"0",
            "entry_blocked":True,
        }
    return {
        "hypothetical_contract_count":1,
        "hypothetical_pnl_dollars":str(payout-total_cost),
        "entry_blocked":False,
    }


def build_kalshi_prospective_shadow_summary(
    historical_confirmation:Mapping[str,object],
    audit:Mapping[str,object],
)->dict[str,object]:
    if (
        historical_confirmation.get("kind")
        !="KALSHI_UNTOUCHED_TEST_CONFIRMATION_NO_ORDER"
        or historical_confirmation.get("candidate_added_by_untouched_test") is not False
        or historical_confirmation.get("candidate_ranking_performed") is not False
        or historical_confirmation.get("automatic_candidate_selection")!="DISABLED"
        or historical_confirmation.get("demo_order_submission")!="DISABLED"
        or historical_confirmation.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid frozen Kalshi historical confirmation")
    confirmed=historical_confirmation.get("candidates_confirmed_on_untouched_test")
    if (
        not isinstance(confirmed,list) or not confirmed
        or len(set(confirmed))!=len(confirmed)
        or any(not isinstance(x,str) or not x for x in confirmed)
    ):
        raise ValueError("no unique historically confirmed Kalshi candidate")
    for name in confirmed:
        _hypothesis(name)

    if (
        audit.get("kind")!="KALSHI_PROSPECTIVE_ARCHIVE_AUDIT_NO_ORDERS"
        or audit.get("hypothesis_policy_version")!=EXPECTED_HYPOTHESIS_POLICY
        or audit.get("source_integrity_passed") is not True
        or audit.get("outcome_direction_used_for_market_selection") is not False
        or audit.get("historical_backfill_count")!=0
        or audit.get("post_settlement_decision_count")!=0
        or audit.get("network_requests")!="NONE"
        or audit.get("demo_order_submission")!="DISABLED"
        or audit.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("invalid Kalshi prospective archive audit")
    if audit.get("pending_market_count")!=0:
        raise ValueError("Kalshi prospective sample still has pending markets")

    planned=audit.get("planned_market_count")
    valid=audit.get("valid_prospective_market_count")
    missed=audit.get("missed_or_invalid_market_count")
    events=audit.get("distinct_valid_event_count")
    coverage=audit.get("capture_coverage_fraction")
    if (
        type(planned) is not int or type(valid) is not int or type(missed) is not int
        or type(events) is not int
    ):
        raise ValueError("Kalshi prospective audit counts malformed")
    if valid<EVALUATION_MARKETS:
        raise ValueError("Kalshi prospective shadow needs at least twenty valid markets")
    if valid+missed!=planned:
        raise ValueError("Kalshi prospective audit completion counts inconsistent")

    valid_markets=_chronological_valid_markets(audit)
    if len(valid_markets)!=valid:
        raise ValueError("Kalshi prospective valid-market rows differ from count")
    evaluation=valid_markets[:EVALUATION_MARKETS]

    candidate_results={}
    for candidate in confirmed:
        scenario_results={}
        for scenario in REQUIRED_SCENARIOS:
            friction=FRICTION_SCENARIOS.get(scenario)
            if friction is None:
                raise ValueError("frozen Kalshi friction scenario missing")
            total_pnl=Decimal("0")
            total_contracts=0
            block_results=[]
            for block_index in range(BLOCKS):
                start=block_index*BLOCK_MARKETS
                stop=start+BLOCK_MARKETS
                block_pnl=Decimal("0")
                block_contracts=0
                for market in evaluation[start:stop]:
                    outcome=_simulate_one(
                        market,
                        hypothesis_name=candidate,
                        extra_friction=friction,
                    )
                    block_pnl+=Decimal(outcome["hypothetical_pnl_dollars"])
                    block_contracts+=int(outcome["hypothetical_contract_count"])
                total_pnl+=block_pnl
                total_contracts+=block_contracts
                block_results.append({
                    "block":block_index+1,
                    "market_count":BLOCK_MARKETS,
                    "hypothetical_contract_count":block_contracts,
                    "total_hypothetical_pnl_dollars":str(block_pnl),
                })
            scenario_results[scenario]={
                "hypothetical_contract_count":total_contracts,
                "total_hypothetical_pnl_dollars":str(total_pnl),
                "chronological_blocks":block_results,
            }
        candidate_results[candidate]=scenario_results

    return {
        "kind":"KALSHI_PROSPECTIVE_SHADOW_SUMMARY_NO_ORDERS",
        "hypothesis_policy_version":EXPECTED_HYPOTHESIS_POLICY,
        "plan_sha256":audit["plan_sha256"],
        "candidate_versions_changed_after_start":False,
        "outcome_direction_used_for_market_selection":False,
        "planned_market_count":planned,
        "valid_prospective_market_count":valid,
        "distinct_event_count":events,
        "missed_or_invalid_market_count":missed,
        "capture_coverage_fraction":coverage,
        "evaluation_market_count":EVALUATION_MARKETS,
        "evaluation_rule":
            "FIRST_20_VALID_PRECOMMITTED_MARKETS_BY_PLANNED_CLOSE_THEN_TICKER",
        "candidate_results":candidate_results,
        "candidate_added_by_prospective_results":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "historical_backfill_count":0,
        "post_settlement_decision_count":0,
        "source_integrity_passed":True,
        "network_methods":["GET"],
        "credentials_accessed":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
