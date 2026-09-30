"""Predeclared Kalshi historical evidence-sufficiency gate.

This gate is frozen before any 50-market corpus result is inspected. It checks
only sample depth, binary outcome representation, and fixed-horizon historical
price coverage. It deliberately does NOT use Brier performance, P&L, or any
strategy outcome to decide whether the dataset is large enough for the next
research phase.

Passing means only: enough retrospective evidence exists to define/freeze a
strategy and then test it. It never authorizes demo, paper, or live orders.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

POLICY_VERSION="kalshi-historical-depth-gate-v1-predeclared-20260930"
MIN_RESOLVED_MARKETS=50
MIN_YES_OUTCOMES=10
MIN_NO_OUTCOMES=10
MIN_COVERAGE={
    86400:Decimal("0.60"),
    21600:Decimal("0.80"),
    3600:Decimal("0.80"),
}


def _fraction(value:object)->Decimal:
    try:
        result=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid Kalshi coverage fraction") from exc
    if not result.is_finite() or result<0 or result>1:
        raise ValueError("Kalshi coverage fraction outside 0..1")
    return result


def assess_kalshi_historical_depth(
    corpus:Mapping[str,object],
)->dict[str,object]:
    if corpus.get("kind")!="OFFLINE_KALSHI_RESOLVED_CORPUS_CALIBRATION_REPORT":
        raise ValueError("unexpected Kalshi historical corpus kind")
    if (
        corpus.get("historical_corpus_is_not_prospective_validation") is not True
        or corpus.get("market_price_calibration_is_not_strategy_alpha") is not True
        or corpus.get("strategy_ranking_performed") is not False
        or corpus.get("strategy_selection_performed") is not False
        or corpus.get("demo_order_submission")!="DISABLED"
        or corpus.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("Kalshi historical corpus escaped research-only contract")

    total=corpus.get("resolved_market_count")
    yes=corpus.get("yes_outcome_count")
    no=corpus.get("no_outcome_count")
    if (
        type(total) is not int or total<1
        or type(yes) is not int or yes<0
        or type(no) is not int or no<0
        or yes+no!=total
    ):
        raise ValueError("invalid Kalshi corpus outcome counts")

    summary=corpus.get("fixed_horizon_summary")
    if not isinstance(summary,Mapping):
        raise ValueError("Kalshi corpus fixed-horizon summary missing")

    coverage_checks={}
    for horizon,minimum in MIN_COVERAGE.items():
        row=summary.get(str(horizon))
        if not isinstance(row,Mapping):
            raise ValueError("Kalshi corpus missing predeclared horizon")
        if row.get("horizon_seconds_before_settlement")!=horizon:
            raise ValueError("Kalshi corpus horizon identity mismatch")
        coverage=_fraction(row.get("coverage_fraction"))
        available=row.get("available_market_count")
        missing=row.get("missing_market_count")
        if (
            type(available) is not int or available<0
            or type(missing) is not int or missing<0
            or available+missing!=total
        ):
            raise ValueError("Kalshi horizon coverage counts inconsistent")
        coverage_checks[str(horizon)]={
            "required_fraction":str(minimum),
            "observed_fraction":str(coverage),
            "pass":coverage>=minimum,
        }

    checks={
        "minimum_resolved_markets":{
            "required":MIN_RESOLVED_MARKETS,
            "observed":total,
            "pass":total>=MIN_RESOLVED_MARKETS,
        },
        "minimum_yes_outcomes":{
            "required":MIN_YES_OUTCOMES,
            "observed":yes,
            "pass":yes>=MIN_YES_OUTCOMES,
        },
        "minimum_no_outcomes":{
            "required":MIN_NO_OUTCOMES,
            "observed":no,
            "pass":no>=MIN_NO_OUTCOMES,
        },
        "fixed_horizon_coverage":coverage_checks,
    }
    ready=(
        checks["minimum_resolved_markets"]["pass"]
        and checks["minimum_yes_outcomes"]["pass"]
        and checks["minimum_no_outcomes"]["pass"]
        and all(x["pass"] for x in coverage_checks.values())
    )
    return {
        "kind":"KALSHI_HISTORICAL_DEPTH_GATE_PREDECLARED_NO_ORDER",
        "policy_version":POLICY_VERSION,
        "checks":checks,
        "historical_depth_ready_for_fixed_strategy_research":ready,
        "brier_error_used_to_set_depth_gate":False,
        "historical_pnl_used_to_set_depth_gate":False,
        "strategy_results_used_to_set_depth_gate":False,
        "next_action":(
            "DEFINE_AND_FREEZE_KALSHI_STRATEGY_BEFORE_STRATEGY_SCORING"
            if ready else
            "COLLECT_MORE_DETERMINISTIC_RESOLVED_MARKET_EVIDENCE"
        ),
        "demo_execution_eligible":False,
        "paper_execution_eligible":False,
        "live_execution_eligible":False,
        "automatic_strategy_promotion":"DISABLED",
        "order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
