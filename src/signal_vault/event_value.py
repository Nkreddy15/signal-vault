"""Event-contract value translation into the shared opportunity contract.

The market price is not treated as a recommendation. A separate probability
model supplies an independently estimated YES probability plus a calibration
confidence. This module compares that estimate with executable YES/NO ask
prices, subtracts modeled fees/friction, and emits at most one normalized
research opportunity.

No Kalshi API, credentials, order submission, news model, or live authority is
present here. It is the deterministic bridge between a future probability
model and the common Signal Vault allocator.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .opportunity_engine import Direction, Market, Opportunity


def _probability(value: Decimal, *, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    if value <= 0 or value >= 1:
        raise ValueError(f"{name} must be strictly within (0,1)")
    return value


def event_contract_opportunity(
    *,
    ticker: str,
    candidate_id: str,
    strategy_family: str,
    estimated_yes_probability: Decimal,
    probability_confidence: Decimal,
    yes_ask_probability: Decimal,
    no_ask_probability: Decimal,
    estimated_round_trip_fee_return: Decimal,
    generated_utc: datetime,
    valid_until_utc: datetime,
    horizon_seconds: int,
    evidence_id: str,
    min_expected_net_return: Decimal = Decimal("0.01"),
    paper_executable: bool = False,
) -> Opportunity | None:
    """Return the better YES/NO side only when independent expected value clears.

    Gross directional return is expected profit divided by entry cost:
      YES: (p_yes - yes_ask) / yes_ask
      NO:  ((1-p_yes) - no_ask) / no_ask

    This is expected-value arithmetic, not proof that the probability estimate
    is calibrated or profitable. The caller must supply independent evidence.
    """
    if not ticker.strip() or len(ticker) > 120:
        raise ValueError("invalid event-contract ticker")
    p_yes = _probability(
        estimated_yes_probability,
        name="estimated_yes_probability",
    )
    confidence = _probability(
        probability_confidence,
        name="probability_confidence",
    )
    yes_ask = _probability(yes_ask_probability, name="yes_ask_probability")
    no_ask = _probability(no_ask_probability, name="no_ask_probability")
    if yes_ask + no_ask < Decimal("0.90"):
        raise ValueError("event asks are implausibly crossed/incomplete")
    if type(estimated_round_trip_fee_return) is not Decimal:
        raise ValueError("event fee estimate must be Decimal")
    if (
        not estimated_round_trip_fee_return.is_finite()
        or estimated_round_trip_fee_return < 0
        or estimated_round_trip_fee_return > Decimal("1")
    ):
        raise ValueError("invalid event fee estimate")
    if (
        type(min_expected_net_return) is not Decimal
        or not min_expected_net_return.is_finite()
        or min_expected_net_return < 0
    ):
        raise ValueError("invalid minimum event edge")

    p_no = Decimal("1") - p_yes
    yes_gross = (p_yes - yes_ask) / yes_ask
    no_gross = (p_no - no_ask) / no_ask
    candidates = (
        (yes_gross, Direction.YES, yes_ask),
        (no_gross, Direction.NO, no_ask),
    )
    gross, direction, entry_price = max(
        candidates,
        key=lambda item: (item[0], item[1].value),
    )
    net = gross - estimated_round_trip_fee_return
    if net < min_expected_net_return:
        return None

    return Opportunity(
        market=Market.EVENT_CONTRACT,
        instrument=ticker,
        candidate_id=candidate_id,
        strategy_family=strategy_family,
        direction=direction,
        generated_utc=generated_utc,
        valid_until_utc=valid_until_utc,
        horizon_seconds=horizon_seconds,
        expected_gross_return=gross,
        estimated_round_trip_cost_return=estimated_round_trip_fee_return,
        confidence=confidence,
        max_loss_return=Decimal("1"),
        evidence_id=(
            f"{evidence_id}|entry_probability={entry_price}|"
            f"estimated_yes_probability={p_yes}"
        ),
        correlation_group=f"event:{ticker.split('-')[0]}",
        paper_executable=paper_executable,
    )
