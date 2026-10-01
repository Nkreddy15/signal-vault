"""Conservative six-crypto research-to-PAPER decision intent bridge.

This module never reads provider accounts and never submits orders. It only
turns one unambiguous, prospectively validated flat-state BUY signal into the
Phase 111 PRECOMMITTED_MULTIMARKET_PAPER_DECISION_INTENT schema.

No ranking is allowed:
- multiple eligible strategies -> blocked
- multiple simultaneous BUY symbols -> blocked
- zero BUY symbols -> HOLD
"""
from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .paper_intent_preview import DECISION_KIND


KIND="CRYPTO_PAPER_DECISION_INTENT_BUILDER_NO_ORDERS"
REVIEW_KIND="PREDECLARED_SIX_CRYPTO_FORWARD_REVIEW_GATE_NOT_TRADING_AUTHORIZATION"
SHADOW_KIND="OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY"


def _money(raw:object)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid bounded paper intent notional") from exc
    if not value.is_finite() or value<=0 or value>Decimal("10"):
        raise ValueError("paper intent notional must be >0 and <=10 USD")
    return value


def build_crypto_entry_intent(
    review:Mapping[str,object],
    shadow:Mapping[str,object],
    *,
    max_loss_usd:object="5",
)->dict[str,object]:
    if (
        not isinstance(review,Mapping)
        or review.get("kind")!=REVIEW_KIND
        or review.get("evidence_window_complete_for_gate") is not True
        or review.get("candidate_order_has_no_rank_or_preference") is not True
        or review.get("automatic_candidate_selection")!="DISABLED"
        or review.get("paper_order_submission")!="DISABLED"
        or review.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("complete frozen six-crypto review required")
    eligible=review.get("candidates_meeting_all_review_criteria")
    if (
        not isinstance(eligible,list)
        or any(not isinstance(x,str) or not x for x in eligible)
        or len(set(eligible))!=len(eligible)
    ):
        raise ValueError("invalid eligible strategy list")

    if (
        not isinstance(shadow,Mapping)
        or shadow.get("kind")!=SHADOW_KIND
        or shadow.get("broker_order_submission")!="DISABLED"
        or shadow.get("automatic_paper_trading")!="DISABLED"
        or shadow.get("live_trading")!="UNAVAILABLE"
        or shadow.get("strategy_promoted") is not False
        or shadow.get("future_edge_established") is not False
    ):
        raise ValueError("verified no-order prospective shadow required")

    common={
        "kind":KIND,
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "provider_account_positions_queried":False,
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "automatic_strategy_ranking":"DISABLED",
    }

    if len(eligible)==0:
        return {
            **common,
            "status":"HOLD_NO_ELIGIBLE_FORWARD_STRATEGY",
            "decision_intent":None,
        }
    if len(eligible)>1:
        return {
            **common,
            "status":"BLOCKED_MULTIPLE_ELIGIBLE_STRATEGIES_NO_RANKING",
            "eligible_strategies":sorted(eligible),
            "decision_intent":None,
        }

    strategy=eligible[0]
    signals=shadow.get("predeclared_flat_and_held_hypothetical_decisions")
    if not isinstance(signals,Mapping) or not signals:
        raise ValueError("shadow lacks predeclared decisions")

    buys=[]
    for symbol in sorted(signals):
        per_symbol=signals[symbol]
        if not isinstance(per_symbol,Mapping) or strategy not in per_symbol:
            raise ValueError("eligible strategy missing from shadow")
        per_strategy=per_symbol[strategy]
        if not isinstance(per_strategy,Mapping):
            raise ValueError("invalid strategy shadow mapping")
        flat=per_strategy.get("flat")
        if not isinstance(flat,Mapping):
            raise ValueError("flat-state prospective decision required")
        action=flat.get("hypothetical_action")
        evidence=flat.get("evidence_sha256")
        if not isinstance(evidence,str) or len(evidence)!=64:
            raise ValueError("exact signal evidence SHA-256 required")
        if action=="buy":
            buys.append((str(symbol),evidence))
        elif action not in ("hold","sell"):
            raise ValueError("unexpected shadow action")

    if not buys:
        return {
            **common,
            "status":"HOLD_NO_CURRENT_UNAMBIGUOUS_BUY",
            "eligible_strategy":strategy,
            "decision_intent":None,
        }
    if len(buys)>1:
        return {
            **common,
            "status":"BLOCKED_MULTIPLE_SIMULTANEOUS_BUYS_NO_ASSET_RANKING",
            "eligible_strategy":strategy,
            "buy_signal_symbols":[x[0] for x in buys],
            "decision_intent":None,
        }

    symbol,evidence=buys[0]
    notional=_money(max_loss_usd)
    latest_close=shadow.get("latest_newly_observed_UTC_close")
    shadow_sha=shadow.get("shadow_payload_sha256")
    if not isinstance(latest_close,str) or not latest_close:
        raise ValueError("latest prospective close required")
    if not isinstance(shadow_sha,str) or len(shadow_sha)!=64:
        raise ValueError("shadow payload SHA-256 required")

    seed=f"{strategy}|{symbol}|{latest_close}|{evidence}|{shadow_sha}".encode()
    suffix=hashlib.sha256(seed).hexdigest()[:20]
    client_id="svp-"+suffix
    intent={
        "kind":DECISION_KIND,
        "decision_id":client_id,
        "market_lane":"crypto",
        "instrument":symbol,
        "max_loss_usd":str(notional),
        "provider_payload":{
            "symbol":symbol,
            "side":"buy",
            "type":"market",
            "time_in_force":"gtc",
            "client_order_id":client_id,
            "notional":str(notional),
        },
        "strategy_evidence_sha256":evidence,
        "forward_gate_passed":True,
        "separate_owner_activation_required":True,
    }
    return {
        **common,
        "status":"ONE_UNAMBIGUOUS_PAPER_ENTRY_INTENT_PREVIEWABLE",
        "eligible_strategy":strategy,
        "source_shadow_sha256":shadow_sha,
        "decision_intent":intent,
        "intent_is_not_order_authorization":True,
    }
