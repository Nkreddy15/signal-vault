"""Read-only all-market PAPER pilot readiness status.

Separates engineering capability from forward-evidence completion. It never
turns either into order authorization, never reads credentials, never performs
provider requests, and never submits PAPER/DEMO/LIVE orders.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .all_market_forward_status import all_market_forward_status
from .cloud_forward_service import CLOUD_ROOT
from .paper_runway_status import paper_runway_from_forward_status


KIND="ALL_MARKET_PAPER_PILOT_STATUS_NOT_ORDER_AUTHORIZATION"
ENGINEERING_VERSION="paper-pilot-engineering-stack-v1-20261001"


def paper_pilot_status_from_forward(
    status:Mapping[str,object],
)->dict[str,object]:
    runway=paper_runway_from_forward_status(status)
    blockers=list(runway["current_forward_evidence_blockers"])
    return {
        "kind":KIND,
        "engineering_version":ENGINEERING_VERSION,
        "forward_evidence":{
            "six_crypto":dict(runway["six_crypto"]),
            "us_equity":dict(runway["us_equity"]),
            "kalshi":dict(runway["kalshi"]),
            "blockers":blockers,
            "all_market_forward_stages_complete":
                runway["all_market_forward_source_and_review_stages_complete"],
        },
        "engineering":{
            "shared_cross_market_risk_governor":"AVAILABLE",
            "durable_multimarket_execution_journal":"AVAILABLE",
            "alpaca_crypto_paper_route":"AVAILABLE_SEPARATELY_GATED",
            "alpaca_equity_paper_route":"AVAILABLE_SEPARATELY_GATED",
            "kalshi_demo_route":"AVAILABLE_SEPARATELY_GATED",
            "crypto_strategy_to_paper_intent":"AVAILABLE_NO_ORDER",
            "crypto_end_to_end_paper_dry_run":"AVAILABLE_NO_EXECUTION",
            "crypto_activation_handoff":"FROZEN_NO_EXECUTION",
            "supervised_alpaca_paper_plumbing":"PREVIOUSLY_RECONCILED",
            "automatic_paper_or_demo_execution":"DISABLED",
            "live_execution":"UNAVAILABLE",
        },
        "crypto_autonomous_paper":{
            "engineering_path_complete_through_dry_run":True,
            "forward_evidence_complete":
                runway["six_crypto"]["frozen_review_window_complete"],
            "candidate_available_after_frozen_review":
                bool(runway["six_crypto"][
                    "candidates_meeting_all_frozen_review_criteria"
                ]),
            "owner_activation_review_required":True,
            "executor_invocation_enabled":False,
        },
        "all_market_autonomous_paper":{
            "engineering_is_not_forward_validation":True,
            "forward_evidence_blocker_count":len(blockers),
            "ready_for_unattended_order_submission":False,
        },
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "readiness_is_not_expected_profit_or_trading_advice":True,
    }


def current_paper_pilot_status(
    *,
    environ:Mapping[str,str]|None=None,
    root:Path=CLOUD_ROOT,
)->dict[str,object]:
    return paper_pilot_status_from_forward(
        all_market_forward_status(environ=environ,root=root)
    )
