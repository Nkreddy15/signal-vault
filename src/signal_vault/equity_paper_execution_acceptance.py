"""Predeclared Alpaca PAPER execution acceptance for US equities.

This policy is frozen before paper-order validation begins. It measures only
execution correctness, recovery, provider reconciliation and shared-risk
enforcement. Strategy profitability is explicitly excluded.

Passing this policy is one technical-readiness input. It does not configure
live credentials, record owner live authorization, or enable live orders.
"""
from __future__ import annotations

from typing import Mapping

POLICY_VERSION="equity-paper-execution-acceptance-v1-predeclared-20260930"
MIN_PAPER_ORDERS=20
MIN_DISTINCT_SYMBOLS=4
MIN_PROVIDER_RECONCILIATIONS=20
MIN_RESTART_RECOVERY_CASES=1
MIN_UNKNOWN_RESULT_RECOVERY_CASES=1


def _count(raw:object, *, name:str)->int:
    if type(raw) is not int or raw<0:
        raise ValueError(f"invalid stock paper {name}")
    return raw


def assess_equity_paper_execution(
    summary:Mapping[str,object],
)->dict[str,object]:
    if summary.get("kind")!="EQUITY_PAPER_EXECUTION_VALIDATION_SUMMARY":
        raise ValueError("unexpected stock paper execution summary")
    if (
        summary.get("environment")!="alpaca_paper"
        or summary.get("paper_host_only_verified") is not True
        or summary.get("live_host_requests")!=0
        or summary.get("live_order_submission")!="DISABLED"
    ):
        raise ValueError("stock paper validation escaped Alpaca PAPER boundary")

    orders=_count(summary.get("paper_order_count"),name="order count")
    symbols=_count(
        summary.get("distinct_symbol_count"),name="distinct symbol count"
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
    preflight_passes=_count(
        summary.get("provider_rule_preflight_pass_count"),
        name="provider rule preflight pass count",
    )
    restart_cases=_count(
        summary.get("restart_recovery_case_count"),
        name="restart recovery case count",
    )
    unknown_cases=_count(
        summary.get("unknown_result_recovery_case_count"),
        name="unknown-result recovery case count",
    )

    if any(x>orders for x in (reconciled,unresolved,preflight_passes)):
        raise ValueError("stock paper execution counts exceed submitted orders")

    checks={
        "minimum_paper_orders":{
            "required":MIN_PAPER_ORDERS,
            "observed":orders,
            "pass":orders>=MIN_PAPER_ORDERS,
        },
        "minimum_distinct_symbols":{
            "required":MIN_DISTINCT_SYMBOLS,
            "observed":symbols,
            "pass":symbols>=MIN_DISTINCT_SYMBOLS,
        },
        "provider_rule_preflight_before_every_order":{
            "required_passes":orders,
            "observed_passes":preflight_passes,
            "pass":orders>0 and preflight_passes==orders,
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
    passed=all(x["pass"] for x in checks.values())
    return {
        "kind":"EQUITY_PAPER_EXECUTION_ACCEPTANCE_NO_LIVE_AUTHORITY",
        "policy_version":POLICY_VERSION,
        "checks":checks,
        "paper_execution_validated":passed,
        "restart_and_unknown_result_recovery_validated":(
            checks["restart_recovery_exercised"]["pass"]
            and checks["unknown_result_recovery_exercised"]["pass"]
        ),
        "provider_reconciliation_validated":(
            checks["complete_provider_reconciliation"]["pass"]
            and checks["zero_unresolved_orders"]["pass"]
        ),
        "strategy_profitability_used_for_execution_acceptance":False,
        "historical_pnl_used_for_execution_acceptance":False,
        "paper_host_only_required":True,
        "automatic_live_activation":"DISABLED",
        "live_credentials_configured":False,
        "owner_live_authorization_recorded":False,
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "next_action":(
            "CONTINUE_SEPARATE_PROSPECTIVE_STRATEGY_VALIDATION"
            if passed else
            "PAPER_EXECUTION_VALIDATION_INCOMPLETE"
        ),
    }
