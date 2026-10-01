"""Historical-bootstrap gate for a supervised crypto PAPER pilot.

This lane exists to let a strictly retrospective, chronology-preserving
historical study nominate ONE frozen strategy for supervised PAPER testing.
It does NOT satisfy the independent prospective gate and it does NOT authorize
autonomous PAPER or LIVE trading.

A separate current prospective shadow signal is still required for any PAPER
intent. Historical data chooses the frozen hypothesis; current data decides
whether that hypothesis is presently BUY/HOLD/SELL.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .multi_asset_simulation import HYPOTHESES, HypothesisKind
from .paper_intent_preview import DECISION_KIND, preview_paper_intent


KIND="CRYPTO_HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER_REVIEW_NO_ORDERS"
VALIDATION_KIND="CRYPTO_HISTORICAL_BOOTSTRAP_VALIDATION_RECEIPT"
SHADOW_KIND="OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY"
POLICY_VERSION="crypto-historical-bootstrap-supervised-paper-v1-20261001"
REQUIRED_SYMBOLS=(
    "AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD",
)
MAX_PAPER_NOTIONAL_USD=Decimal("5")


def _money(raw:object)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid supervised PAPER notional") from exc
    if not value.is_finite() or value<=0 or value>MAX_PAPER_NOTIONAL_USD:
        raise ValueError("supervised PAPER notional must be >0 and <=5 USD")
    return value


def _sha(raw:object,name:str)->str:
    if (
        not isinstance(raw,str)
        or len(raw)!=64
        or any(ch not in "0123456789abcdef" for ch in raw)
    ):
        raise ValueError(f"valid lowercase SHA-256 required for {name}")
    return raw


def assess_historical_bootstrap_validation(
    validation:Mapping[str,object],
)->dict[str,object]:
    if not isinstance(validation,Mapping) or validation.get("kind")!=VALIDATION_KIND:
        raise ValueError("historical bootstrap validation receipt required")

    strategy=validation.get("selected_strategy")
    active={
        h.name for h in HYPOTHESES
        if h.kind in (HypothesisKind.EMA,HypothesisKind.MOMENTUM)
    }
    symbols=validation.get("symbols")
    historical_hours=validation.get("historical_hours")
    folds=validation.get("walk_forward_fold_count")
    scenario_passes=validation.get("cost_stress_passes")

    if tuple(sorted(symbols or ()))!=REQUIRED_SYMBOLS:
        raise ValueError("exact frozen six-crypto universe required")
    if type(historical_hours) is not int or not 120<=historical_hours<=168:
        raise ValueError("bootstrap requires 5-7 closed historical days")
    if type(folds) is not int or folds<3:
        raise ValueError("at least three chronological walk-forward folds required")
    if strategy not in active:
        raise ValueError("one predeclared active strategy required")
    if (
        not isinstance(scenario_passes,Mapping)
        or set(scenario_passes)!={
            "illustrative_low_friction",
            "illustrative_base_friction",
            "illustrative_high_friction",
        }
        or any(type(v) is not bool for v in scenario_passes.values())
    ):
        raise ValueError("all three predeclared historical cost stress checks required")

    checks={
        "strictly_chronological":
            validation.get("strictly_chronological") is True,
        "selection_used_validation_only":
            validation.get("selection_used_validation_only") is True,
        "untouched_test_used_only_as_veto":
            validation.get("untouched_test_used_only_as_veto") is True,
        "test_not_used_to_tune":
            validation.get("test_used_for_tuning") is False,
        "historical_not_labeled_prospective":
            validation.get("historical_data_is_not_prospective_validation") is True,
        "all_cost_stress_checks_passed":
            all(scenario_passes.values()),
        "no_live_authority":
            validation.get("live_trading")=="UNAVAILABLE",
        "no_order_submission_during_training":
            validation.get("broker_order_submission")=="DISABLED",
    }
    failed=[name for name,value in checks.items() if not value]
    eligible=not failed
    return {
        "kind":KIND,
        "policy_version":POLICY_VERSION,
        "selected_strategy":strategy,
        "historical_hours":historical_hours,
        "walk_forward_fold_count":folds,
        "validation_receipt_sha256":_sha(
            validation.get("receipt_sha256"),"validation receipt"
        ),
        "checks":checks,
        "failed_checks":failed,
        "eligible_for_supervised_paper_bootstrap":eligible,
        "independent_prospective_gate_passed":False,
        "historical_data_reclassified_as_prospective":False,
        "automatic_paper_activation":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
        "next_action":(
            "USE_CURRENT_PROSPECTIVE_SHADOW_FOR_SUPERVISED_PAPER_DECISION"
            if eligible else
            "RESOLVE_HISTORICAL_BOOTSTRAP_VALIDATION_FAILURES"
        ),
    }


def build_supervised_bootstrap_paper_preview(
    validation:Mapping[str,object],
    latest_shadow:Mapping[str,object],
    *,
    account_state:Mapping[str,object],
    max_loss_usd:object="2",
)->dict[str,object]:
    review=assess_historical_bootstrap_validation(validation)
    common={
        "kind":"CRYPTO_HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER_PREVIEW_NO_ORDERS",
        "historical_review":review,
        "automatic_paper_activation":"DISABLED",
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "provider_post_attempted":False,
        "paper_order_submission":"DISABLED",
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
    }
    if not review["eligible_for_supervised_paper_bootstrap"]:
        return {**common,"status":"BLOCKED_HISTORICAL_VALIDATION","paper_preview":None}

    if (
        not isinstance(latest_shadow,Mapping)
        or latest_shadow.get("kind")!=SHADOW_KIND
        or latest_shadow.get("broker_order_submission")!="DISABLED"
        or latest_shadow.get("automatic_paper_trading")!="DISABLED"
        or latest_shadow.get("live_trading")!="UNAVAILABLE"
        or latest_shadow.get("strategy_promoted") is not False
        or latest_shadow.get("future_edge_established") is not False
    ):
        raise ValueError("current prospective no-order shadow required")

    strategy=review["selected_strategy"]
    signals=latest_shadow.get("predeclared_flat_and_held_hypothetical_decisions")
    if not isinstance(signals,Mapping) or not signals:
        raise ValueError("prospective shadow lacks current decisions")

    buys=[]
    for symbol in sorted(signals):
        per_symbol=signals[symbol]
        if not isinstance(per_symbol,Mapping) or strategy not in per_symbol:
            raise ValueError("frozen historical strategy missing from current shadow")
        item=per_symbol[strategy]
        flat=item.get("flat") if isinstance(item,Mapping) else None
        if not isinstance(flat,Mapping):
            raise ValueError("flat-state current prospective decision required")
        action=flat.get("hypothetical_action")
        evidence=_sha(flat.get("evidence_sha256"),"current signal evidence")
        if action=="buy":
            buys.append((symbol,evidence))
        elif action not in ("hold","sell"):
            raise ValueError("unexpected current shadow action")

    if not buys:
        return {
            **common,
            "status":"HOLD_NO_CURRENT_BUY_FOR_FROZEN_HISTORICAL_STRATEGY",
            "paper_preview":None,
        }
    if len(buys)>1:
        return {
            **common,
            "status":"BLOCKED_MULTIPLE_CURRENT_BUYS_NO_ASSET_RANKING",
            "buy_signal_symbols":[x[0] for x in buys],
            "paper_preview":None,
        }

    symbol,evidence=buys[0]
    # First bootstrap is deliberately BTC-only because provider preflight and
    # one-shot execution are currently hardened specifically for BTC/USD.
    if symbol!="BTC/USD":
        return {
            **common,
            "status":"HOLD_CURRENT_BUY_NOT_YET_SUPPORTED_BY_FIRST_BTC_ONLY_EXECUTOR",
            "current_buy_symbol":symbol,
            "paper_preview":None,
        }

    notional=_money(max_loss_usd)
    latest_close=latest_shadow.get("latest_newly_observed_UTC_close")
    shadow_sha=_sha(latest_shadow.get("shadow_payload_sha256"),"shadow payload")
    if not isinstance(latest_close,str) or not latest_close:
        raise ValueError("current prospective close required")
    seed=(
        f"historical-bootstrap|{strategy}|{symbol}|{latest_close}|"
        f"{evidence}|{shadow_sha}|{review['validation_receipt_sha256']}"
    ).encode()
    decision_id="svhb-"+hashlib.sha256(seed).hexdigest()[:20]
    decision={
        "kind":DECISION_KIND,
        "decision_id":decision_id,
        "market_lane":"crypto",
        "instrument":symbol,
        "max_loss_usd":str(notional),
        "provider_payload":{
            "symbol":symbol,
            "side":"buy",
            "type":"market",
            "time_in_force":"gtc",
            "client_order_id":decision_id,
            "notional":str(notional),
        },
        "strategy_evidence_sha256":evidence,
        "forward_gate_passed":False,
        "separate_owner_activation_required":True,
    }
    preview=preview_paper_intent(decision,account_state=account_state)
    return {
        **common,
        "status":(
            "READY_FOR_SUPERVISED_PAPER_DRAFT_REVIEW"
            if preview["risk_assessment"]["risk_admissible"] is True
            else "BLOCKED_SHARED_RISK_GOVERNOR"
        ),
        "selected_strategy":strategy,
        "current_signal_source":"GENUINE_PROSPECTIVE_SHADOW_NOT_HISTORICAL_BACKFILL",
        "paper_preview":preview,
        "independent_prospective_gate_passed":False,
        "paper_period_is_forward_validation":True,
        "live_promotion_permitted":False,
    }
