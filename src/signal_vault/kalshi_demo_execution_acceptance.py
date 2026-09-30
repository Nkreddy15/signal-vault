"""Predeclared Kalshi DEMO execution acceptance policy.

This policy is frozen before any DEMO orders are authorized or submitted. It
evaluates execution correctness only, never profitability or strategy quality.

A passing summary must demonstrate bounded DEMO-only use, durable
commit-before-POST behavior, unique client ids, zero blind retries, complete
provider reconciliation, no unresolved orders, and explicit restart/unknown
result recovery. Passing this policy is one readiness input; it never enables
live trading or records owner live authorization.
"""
from __future__ import annotations

from typing import Mapping

POLICY_VERSION="kalshi-demo-execution-acceptance-v1-predeclared-20260930"
MIN_DEMO_ORDERS=20
MIN_DISTINCT_MARKETS=10
MIN_PROVIDER_RECONCILIATIONS=20
MIN_RESTART_RECOVERY_CASES=1
MIN_UNKNOWN_RESULT_RECOVERY_CASES=1


def _count(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid Kalshi demo {name}")
    return raw


def assess_kalshi_demo_execution(
    summary:Mapping[str,object],
)->dict[str,object]:
    if summary.get("kind")!="KALSHI_DEMO_EXECUTION_VALIDATION_SUMMARY":
        raise ValueError("unexpected Kalshi demo execution summary")
    if (
        summary.get("environment")!="demo"
        or summary.get("demo_host_only_verified") is not True
        or summary.get("live_host_requests")!=0
        or summary.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("Kalshi demo validation escaped demo-only boundary")

    orders=_count(summary.get("demo_order_count"),name="order count")
    markets=_count(
        summary.get("distinct_market_count"),name="distinct market count"
    )
    reconciled=_count(
        summary.get("provider_reconciled_order_count"),
        name="provider reconciliation count",
    )
    unresolved=_count(
        summary.get("unresolved_order_count"),name="unresolved order count"
    )
    duplicates=_count(
        summary.get("duplicate_client_order_id_count"),
        name="duplicate client id count",
    )
    blind_retries=_count(
        summary.get("blind_retry_count"),name="blind retry count"
    )
    posts_without_commit=_count(
        summary.get("post_without_durable_submission_pending_count"),
        name="post without durable commit count",
    )
    risk_bypasses=_count(
        summary.get("shared_risk_governor_bypass_count"),
        name="shared risk bypass count",
    )
    restart_cases=_count(
        summary.get("restart_recovery_case_count"),
        name="restart recovery case count",
    )
    unknown_cases=_count(
        summary.get("unknown_result_recovery_case_count"),
        name="unknown-result recovery case count",
    )

    if reconciled>orders or unresolved>orders:
        raise ValueError("Kalshi demo reconciliation counts exceed orders")

    checks={
        "minimum_demo_orders":{
            "required":MIN_DEMO_ORDERS,
            "observed":orders,
            "pass":orders>=MIN_DEMO_ORDERS,
        },
        "minimum_distinct_markets":{
            "required":MIN_DISTINCT_MARKETS,
            "observed":markets,
            "pass":markets>=MIN_DISTINCT_MARKETS,
        },
        "complete_provider_reconciliation":{
            "required_reconciliations":orders,
            "observed_reconciliations":reconciled,
            "pass":orders>0 and reconciled==orders,
        },
        "zero_unresolved_orders":{
            "observed":unresolved,
            "pass":unresolved==0,
        },
        "zero_duplicate_client_ids":{
            "observed":duplicates,
            "pass":duplicates==0,
        },
        "zero_blind_retries":{
            "observed":blind_retries,
            "pass":blind_retries==0,
        },
        "commit_before_every_post":{
            "posts_without_durable_commit":posts_without_commit,
            "pass":posts_without_commit==0,
        },
        "shared_risk_governor_never_bypassed":{
            "observed_bypasses":risk_bypasses,
            "pass":risk_bypasses==0,
        },
        "restart_recovery_exercised":{
            "required_cases":MIN_RESTART_RECOVERY_CASES,
            "observed_cases":restart_cases,
            "pass":restart_cases>=MIN_RESTART_RECOVERY_CASES,
        },
        "unknown_result_recovery_exercised":{
            "required_cases":MIN_UNKNOWN_RESULT_RECOVERY_CASES,
            "observed_cases":unknown_cases,
            "pass":unknown_cases>=MIN_UNKNOWN_RESULT_RECOVERY_CASES,
        },
    }
    passed=all(item["pass"] for item in checks.values())
    return {
        "kind":"KALSHI_DEMO_EXECUTION_ACCEPTANCE_NO_LIVE_AUTHORITY",
        "policy_version":POLICY_VERSION,
        "checks":checks,
        "demo_execution_validated":passed,
        "restart_and_unknown_result_recovery_validated":(
            checks["restart_recovery_exercised"]["pass"]
            and checks["unknown_result_recovery_exercised"]["pass"]
        ),
        "provider_reconciliation_validated":
            checks["complete_provider_reconciliation"]["pass"]
            and checks["zero_unresolved_orders"]["pass"],
        "strategy_profitability_used_for_execution_acceptance":False,
        "historical_pnl_used_for_execution_acceptance":False,
        "demo_host_only_required":True,
        "automatic_live_activation":"DISABLED",
        "live_credentials_configured":False,
        "owner_live_authorization_recorded":False,
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "next_action":(
            "CONTINUE_SEPARATE_PROSPECTIVE_STRATEGY_VALIDATION"
            if passed else
            "DEMO_EXECUTION_VALIDATION_INCOMPLETE"
        ),
    }
