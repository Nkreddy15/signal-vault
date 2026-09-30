"""Predeclared Kalshi reference hypotheses, frozen before strategy scoring.

These rules use only a market's own historical YES trade-price probability at
one fixed pre-settlement horizon. They do not use the final outcome to make a
decision, do not choose markets, do not tune thresholds from history, and have
no provider/network/order capability.

They are intentionally simple comparators for research:
- cash/no-trade
- follow the market favorite at 24 hours
- follow the market favorite at 6 hours
- take the opposite side of the market favorite at 6 hours

A 0.50 tie produces HOLD so no arbitrary side is invented.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

POLICY_VERSION="kalshi-reference-hypotheses-v1-predeclared-20260930"

Mode=Literal["cash","market_favorite","market_contrarian"]
Action=Literal["hold","buy_yes","buy_no"]


@dataclass(frozen=True)
class KalshiReferenceHypothesis:
    name:str
    mode:Mode
    entry_horizon_seconds:int|None

    def __post_init__(self)->None:
        if not self.name or not self.name.endswith("-predeclared"):
            raise ValueError("Kalshi hypothesis requires frozen versioned name")
        if self.mode=="cash":
            if self.entry_horizon_seconds is not None:
                raise ValueError("cash hypothesis cannot have entry horizon")
        elif (
            type(self.entry_horizon_seconds) is not int
            or self.entry_horizon_seconds<=0
        ):
            raise ValueError("trading reference hypothesis needs fixed positive horizon")

    def as_dict(self)->dict[str,object]:
        return asdict(self)


HYPOTHESES=(
    KalshiReferenceHypothesis(
        "cash-v1-predeclared","cash",None
    ),
    KalshiReferenceHypothesis(
        "market-favorite-24h-hold-v1-predeclared",
        "market_favorite",86400,
    ),
    KalshiReferenceHypothesis(
        "market-favorite-6h-hold-v1-predeclared",
        "market_favorite",21600,
    ),
    KalshiReferenceHypothesis(
        "market-contrarian-6h-hold-v1-predeclared",
        "market_contrarian",21600,
    ),
)


def _probability(value:object)->Decimal:
    try:
        p=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError("invalid Kalshi research probability") from exc
    if not p.is_finite() or p<0 or p>1:
        raise ValueError("Kalshi research probability outside 0..1")
    return p


def reference_decision(
    hypothesis:KalshiReferenceHypothesis,
    *,
    yes_trade_probability:object|None,
)->dict[str,object]:
    if hypothesis not in HYPOTHESES:
        raise ValueError("only predeclared Kalshi hypotheses may be evaluated")
    if hypothesis.mode=="cash":
        return {
            "hypothesis":hypothesis.name,
            "action":"hold",
            "decision_reason":"PREDECLARED_CASH_BASELINE",
            "final_outcome_accessed":False,
            "order_submission":"DISABLED",
        }
    if yes_trade_probability is None:
        return {
            "hypothesis":hypothesis.name,
            "action":"hold",
            "decision_reason":"NO_PRESETTLEMENT_TRADE_PRICE_AVAILABLE",
            "final_outcome_accessed":False,
            "order_submission":"DISABLED",
        }

    p=_probability(yes_trade_probability)
    if p==Decimal("0.5"):
        action:Action="hold"
        reason="EXACT_50_50_TIE_HOLD"
    else:
        favorite_yes=p>Decimal("0.5")
        choose_yes=(
            favorite_yes
            if hypothesis.mode=="market_favorite"
            else not favorite_yes
        )
        action="buy_yes" if choose_yes else "buy_no"
        reason=(
            "FOLLOW_MARKET_FAVORITE_AT_FIXED_HORIZON"
            if hypothesis.mode=="market_favorite"
            else "OPPOSE_MARKET_FAVORITE_AT_FIXED_HORIZON"
        )
    return {
        "hypothesis":hypothesis.name,
        "action":action,
        "decision_reason":reason,
        "yes_trade_probability":str(p),
        "entry_horizon_seconds":hypothesis.entry_horizon_seconds,
        "final_outcome_accessed":False,
        "historical_pnl_accessed":False,
        "order_submission":"DISABLED",
    }


def frozen_hypothesis_receipt()->dict[str,object]:
    names=[x.name for x in HYPOTHESES]
    if len(names)!=len(set(names)):
        raise AssertionError("Kalshi predeclared hypothesis names must be unique")
    return {
        "kind":"FROZEN_KALSHI_REFERENCE_HYPOTHESES_NO_ORDER",
        "policy_version":POLICY_VERSION,
        "hypotheses":[x.as_dict() for x in HYPOTHESES],
        "market_selection_rule":"SEPARATE_DETERMINISTIC_CORPUS_PLAN",
        "entry_reference_for_later_simulation":
            "SAME_CANDLE_YES_ASK_FOR_YES_OR_ONE_MINUS_YES_BID_FOR_NO",
        "position_rule":"AT_MOST_ONE_HYPOTHETICAL_CONTRACT_HELD_TO_SETTLEMENT",
        "outcome_used_to_make_entry_decision":False,
        "historical_strategy_results_used_to_define_hypotheses":False,
        "hyperparameter_optimization":"DISABLED",
        "automatic_strategy_selection":"DISABLED",
        "network_requests":"NONE",
        "credentials_accessed":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
