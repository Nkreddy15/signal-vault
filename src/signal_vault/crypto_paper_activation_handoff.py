"""Frozen handoff contract before any autonomous crypto PAPER pilot execution.

This module never invokes the paper executor. It checks that the Phase 103
technical/forward review, Phase 111 risk/route preview, and an explicit
PAPER-only owner authorization receipt all agree. A pass means only that a
separate executor invocation may be reviewed. LIVE remains unavailable.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .crypto_paper_pilot_review import KIND as REVIEW_KIND
from .paper_intent_preview import KIND as PREVIEW_KIND


KIND="CRYPTO_PAPER_PILOT_ACTIVATION_HANDOFF_NOT_EXECUTION"
AUTH_KIND="OWNER_CRYPTO_PAPER_PILOT_AUTHORIZATION"
AUTH_SCOPE="CRYPTO_AUTONOMOUS_PAPER_PILOT"
AUTH_ENVIRONMENT="alpaca_paper"


def _positive_decimal(raw:object, *, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite() or value<=0:
        raise ValueError(f"invalid {name}")
    return value


def assess_crypto_paper_activation_handoff(
    review:Mapping[str,object],
    preview:Mapping[str,object],
    owner_authorization:Mapping[str,object],
)->dict[str,object]:
    if (
        not isinstance(review,Mapping)
        or review.get("kind")!=REVIEW_KIND
        or review.get("paper_order_submission")!="DISABLED"
        or review.get("live_trading")!="UNAVAILABLE"
        or review.get("eligible_for_separate_owner_paper_pilot_activation_review")
        is not True
        or review.get("paper_pilot_activation_permitted") is not False
    ):
        raise ValueError("eligible frozen crypto paper review required")

    if (
        not isinstance(preview,Mapping)
        or preview.get("kind")!=PREVIEW_KIND
        or preview.get("market_lane")!="crypto"
        or preview.get("route_status")!="VALIDATED_PREVIEW_NO_SUBMISSION"
        or preview.get("network_requests")!="NONE"
        or preview.get("credentials_accessed")!="NONE"
        or preview.get("provider_post_attempted") is not False
        or preview.get("paper_order_submission")!="DISABLED"
        or preview.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("validated no-order crypto paper preview required")

    route=preview.get("route")
    risk=preview.get("risk_assessment")
    if (
        not isinstance(route,Mapping)
        or route.get("provider")!="alpaca"
        or route.get("environment")!="paper"
        or route.get("market_lane")!="crypto"
        or route.get("live_trading_available") is not False
        or not isinstance(risk,Mapping)
        or risk.get("risk_admissible") is not True
        or risk.get("assessment_is_not_trading_authorization") is not True
    ):
        raise ValueError("paper-only Alpaca route and admissible risk receipt required")

    if not isinstance(owner_authorization,Mapping):
        raise ValueError("owner authorization mapping required")
    required={
        "kind","scope","environment","authorized",
        "max_single_order_loss_usd","live_trading_authorized",
    }
    if set(owner_authorization)!=required:
        raise ValueError("exact owner authorization fields required")
    if (
        owner_authorization.get("kind")!=AUTH_KIND
        or owner_authorization.get("scope")!=AUTH_SCOPE
        or owner_authorization.get("environment")!=AUTH_ENVIRONMENT
        or type(owner_authorization.get("authorized")) is not bool
        or type(owner_authorization.get("live_trading_authorized")) is not bool
    ):
        raise ValueError("invalid owner authorization receipt")

    owner_limit=_positive_decimal(
        owner_authorization["max_single_order_loss_usd"],
        name="owner single-order loss limit",
    )
    proposed=_positive_decimal(
        risk.get("proposed_max_loss_usd"),
        name="preview proposed max loss",
    )
    owner_ok=(
        owner_authorization["authorized"] is True
        and owner_authorization["live_trading_authorized"] is False
        and proposed<=owner_limit
    )

    checks={
        "frozen_review_passed":True,
        "paper_route_preview_validated":True,
        "shared_risk_governor_admitted_preview":True,
        "explicit_owner_paper_authorization":owner_authorization["authorized"] is True,
        "owner_limit_covers_previewed_risk":proposed<=owner_limit,
        "owner_did_not_authorize_live":owner_authorization["live_trading_authorized"] is False,
    }
    failed=[name for name,value in checks.items() if not value]
    eligible=not failed and owner_ok

    return {
        "kind":KIND,
        "checks":checks,
        "failed_checks":failed,
        "decision_id":preview.get("decision_id"),
        "instrument":preview.get("instrument"),
        "previewed_max_loss_usd":str(proposed),
        "owner_max_single_order_loss_usd":str(owner_limit),
        "eligible_for_separate_paper_executor_invocation_review":eligible,
        "executor_invocation_performed":False,
        "execution_journal_write_performed":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "provider_post_attempted":False,
        "automatic_paper_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "handoff_is_not_order_authorization":True,
        "next_action":(
            "SEPARATE_PAPER_EXECUTOR_INVOCATION_REVIEW_REQUIRED"
            if eligible else
            "RESOLVE_FAILED_ACTIVATION_HANDOFF_CHECKS"
        ),
    }
