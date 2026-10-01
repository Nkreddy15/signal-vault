"""End-to-end autonomous crypto PAPER pilot dry run, with no execution.

This composes the frozen forward/engineering review, conservative strategy
intent builder, shared cross-market risk preview, and explicit PAPER-only owner
handoff. It deliberately does NOT open an execution journal, read credentials,
call a provider, or invoke the Alpaca paper executor.
"""
from __future__ import annotations

from typing import Mapping

from .crypto_paper_activation_handoff import assess_crypto_paper_activation_handoff
from .crypto_paper_decision_intent import build_crypto_entry_intent
from .crypto_paper_pilot_review import assess_crypto_paper_pilot_review
from .paper_intent_preview import preview_paper_intent


KIND="CRYPTO_AUTONOMOUS_PAPER_PILOT_END_TO_END_DRY_RUN_NO_EXECUTION"


def run_crypto_paper_pilot_dry_run(
    *,
    forward_review:Mapping[str,object],
    engineering_evidence:Mapping[str,object],
    latest_shadow:Mapping[str,object],
    account_state:Mapping[str,object],
    owner_authorization:Mapping[str,object],
    max_loss_usd:object="5",
)->dict[str,object]:
    paper_review=assess_crypto_paper_pilot_review(
        forward_review,
        engineering_evidence,
    )
    common={
        "kind":KIND,
        "paper_review":paper_review,
        "execution_journal_opened":False,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "provider_post_attempted":False,
        "paper_executor_invoked":False,
        "automatic_paper_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }

    if not paper_review[
        "eligible_for_separate_owner_paper_pilot_activation_review"
    ]:
        return {
            **common,
            "status":"BLOCKED_FROZEN_PAPER_REVIEW_INCOMPLETE",
            "decision_builder":None,
            "paper_preview":None,
            "activation_handoff":None,
        }

    decision_builder=build_crypto_entry_intent(
        forward_review,
        latest_shadow,
        max_loss_usd=max_loss_usd,
    )
    intent=decision_builder.get("decision_intent")
    if intent is None:
        return {
            **common,
            "status":decision_builder["status"],
            "decision_builder":decision_builder,
            "paper_preview":None,
            "activation_handoff":None,
        }

    preview=preview_paper_intent(
        intent,
        account_state=account_state,
    )
    if preview["risk_assessment"]["risk_admissible"] is not True:
        return {
            **common,
            "status":"BLOCKED_SHARED_RISK_GOVERNOR",
            "decision_builder":decision_builder,
            "paper_preview":preview,
            "activation_handoff":None,
        }

    handoff=assess_crypto_paper_activation_handoff(
        paper_review,
        preview,
        owner_authorization,
    )
    eligible=handoff[
        "eligible_for_separate_paper_executor_invocation_review"
    ]
    return {
        **common,
        "status":(
            "READY_FOR_SEPARATE_PAPER_EXECUTOR_INVOCATION_REVIEW"
            if eligible else
            "BLOCKED_OWNER_ACTIVATION_HANDOFF"
        ),
        "decision_builder":decision_builder,
        "paper_preview":preview,
        "activation_handoff":handoff,
        "eligible_for_separate_paper_executor_invocation_review":eligible,
        "dry_run_is_not_order_authorization":True,
    }
