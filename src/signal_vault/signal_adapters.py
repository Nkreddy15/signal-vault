"""Market-model adapters into the common Phase 162 ensemble signal contract.

These functions do not forecast anything themselves. They normalize outputs
from independent crypto/equity models and event-probability models so all
markets can compete inside one Signal Vault opportunity engine.

No broker imports, credentials, network calls, order submission, or live mode.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .ensemble_signals import ModelSignal
from .opportunity_engine import Direction, Market


def _finite(value: Decimal, *, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def directional_model_signal(
    *,
    market: Market,
    instrument: str,
    source_model: str,
    strategy_family: str,
    predicted_signed_return: Decimal,
    estimated_round_trip_cost_return: Decimal,
    confidence: Decimal,
    max_loss_return: Decimal,
    generated_utc: datetime,
    valid_until_utc: datetime,
    horizon_seconds: int,
    evidence_id: str,
    correlation_group: str,
    paper_long_supported: bool = False,
    paper_short_supported: bool = False,
) -> ModelSignal | None:
    """Normalize one crypto/equity signed return forecast.

    Positive predicted return maps to LONG; negative maps to SHORT. Zero means
    the model has no directional opinion and returns None.

    A short research signal is never marked PAPER-executable unless the caller
    supplies separate shortability/execution evidence for that lane/instrument.
    """
    if market not in (Market.CRYPTO, Market.US_EQUITY):
        raise ValueError("directional return adapter supports crypto/equity only")
    predicted = _finite(
        predicted_signed_return,
        name="predicted signed return",
    )
    cost = _finite(
        estimated_round_trip_cost_return,
        name="estimated round-trip cost",
    )
    conf = _finite(confidence, name="confidence")
    risk = _finite(max_loss_return, name="max loss return")
    if cost < 0 or cost > Decimal("1"):
        raise ValueError("invalid round-trip cost")
    if not Decimal("0") <= conf <= Decimal("1"):
        raise ValueError("confidence outside [0,1]")
    if not Decimal("0") < risk <= Decimal("1"):
        raise ValueError("max loss return outside (0,1]")
    if type(paper_long_supported) is not bool or type(paper_short_supported) is not bool:
        raise ValueError("paper direction support must be explicit booleans")
    if predicted == 0:
        return None

    direction = Direction.LONG if predicted > 0 else Direction.SHORT
    gross = abs(predicted)
    executable = (
        paper_long_supported
        if direction is Direction.LONG
        else paper_short_supported
    )
    return ModelSignal(
        market=market,
        instrument=instrument,
        source_model=source_model,
        strategy_family=strategy_family,
        direction=direction,
        generated_utc=generated_utc,
        valid_until_utc=valid_until_utc,
        horizon_seconds=horizon_seconds,
        expected_gross_return=gross,
        estimated_round_trip_cost_return=cost,
        confidence=conf,
        max_loss_return=risk,
        evidence_id=evidence_id,
        correlation_group=correlation_group,
        paper_executable=executable,
    )


def event_probability_model_signal(
    *,
    ticker: str,
    source_model: str,
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
    correlation_group: str,
    paper_demo_supported: bool = False,
    minimum_model_net_edge: Decimal = Decimal("0"),
) -> ModelSignal | None:
    """Translate one independent event-probability estimate to YES/NO value.

    Expected directional return is expected profit divided by entry premium:
      YES: (p_yes - yes_ask) / yes_ask
      NO:  ((1-p_yes) - no_ask) / no_ask

    The better side is emitted only when it remains above the caller's minimum
    after estimated friction. Multiple probability models still need to agree
    later in ensemble_signals before a common Opportunity is produced.
    """
    p_yes = _finite(
        estimated_yes_probability,
        name="estimated yes probability",
    )
    conf = _finite(probability_confidence, name="probability confidence")
    yes_ask = _finite(yes_ask_probability, name="yes ask")
    no_ask = _finite(no_ask_probability, name="no ask")
    fee = _finite(
        estimated_round_trip_fee_return,
        name="estimated event friction",
    )
    floor = _finite(minimum_model_net_edge, name="minimum model net edge")
    for value, name in (
        (p_yes, "estimated yes probability"),
        (yes_ask, "yes ask"),
        (no_ask, "no ask"),
    ):
        if not Decimal("0") < value < Decimal("1"):
            raise ValueError(f"{name} must be strictly inside (0,1)")
    if yes_ask + no_ask < Decimal("0.90"):
        raise ValueError("event asks are implausibly crossed/incomplete")
    if not Decimal("0") <= conf <= Decimal("1"):
        raise ValueError("probability confidence outside [0,1]")
    if fee < 0 or fee > Decimal("1") or floor < 0:
        raise ValueError("invalid event friction/edge floor")
    if type(paper_demo_supported) is not bool:
        raise ValueError("paper demo support must be explicit")

    p_no = Decimal("1") - p_yes
    yes_gross = (p_yes - yes_ask) / yes_ask
    no_gross = (p_no - no_ask) / no_ask
    gross, direction = max(
        (
            (yes_gross, Direction.YES),
            (no_gross, Direction.NO),
        ),
        key=lambda item: (item[0], item[1].value),
    )
    if gross - fee < floor:
        return None

    return ModelSignal(
        market=Market.EVENT_CONTRACT,
        instrument=ticker,
        source_model=source_model,
        strategy_family=strategy_family,
        direction=direction,
        generated_utc=generated_utc,
        valid_until_utc=valid_until_utc,
        horizon_seconds=horizon_seconds,
        expected_gross_return=gross,
        estimated_round_trip_cost_return=fee,
        confidence=conf,
        max_loss_return=Decimal("1"),
        evidence_id=evidence_id,
        correlation_group=correlation_group,
        paper_executable=paper_demo_supported,
    )
