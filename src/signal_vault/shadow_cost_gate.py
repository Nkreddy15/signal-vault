"""Offline-only after-cost EMA shadow research gate: NO broker, orders or Keychain.

Market-direction signals are NOT calibrated return forecasts. A BUY crossover
without independent prospective expected-return evidence MUST remain research
HOLD even if an arbitrary guessed price move exceeds a cost hurdle. This
module computes the gross midprice return required to recover two taker fees,
the observed/assumed bid-ask spread and two slippage allowances, plus a
predeclared net-target margin. It never upgrades a signal to a trade order.

A defensive standalone CLI displays a labelled hypothetical cost envelope
and the existing verified automatic forward-journal observation count. The
CLI does not request new data, create a journal, persist a signal, import a
paper executor, read Keychain, access the broker or modify the LaunchAgent.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_UP
from pathlib import Path
from typing import Callable, Mapping

from .strategy import Action, StrategySignal

BPS = Decimal("10000")
CENT = Decimal("0.01")
TWO_DECIMAL_BPS = Decimal("0.01")
MINIMUM_PROSPECTIVE_RESEARCH_BARS = 168


def _d(value: object, name: str, *, upper: Decimal) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("invalid " + name)
    try:
        amount = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("invalid " + name) from exc
    if not amount.is_finite() or amount < 0 or amount > upper:
        raise ValueError("nonfinite, negative or excessive " + name)
    return amount


@dataclass(frozen=True)
class ShadowCostPolicy:
    """Research hypotheses ONLY; no promise of actual Alpaca fill economics."""
    buy_taker_fee_bps: Decimal = Decimal("25")
    sell_taker_fee_bps: Decimal = Decimal("25")
    entry_slippage_allowance_bps: Decimal = Decimal("10")
    exit_slippage_allowance_bps: Decimal = Decimal("10")
    required_net_margin_bps: Decimal = Decimal("20")
    hypothetical_notional_usd: Decimal = Decimal("15")

    def __post_init__(self) -> None:
        for field_name in (
            "buy_taker_fee_bps", "sell_taker_fee_bps",
            "entry_slippage_allowance_bps", "exit_slippage_allowance_bps",
            "required_net_margin_bps",
        ):
            value = getattr(self, field_name)
            if type(value) is not Decimal:
                raise ValueError("cost policy fields must use Decimal: " + field_name)
            _d(value, field_name, upper=Decimal("1000"))
        if (type(self.hypothetical_notional_usd) is not Decimal
                or not self.hypothetical_notional_usd.is_finite()
                or self.hypothetical_notional_usd != Decimal("15")):
            raise ValueError("shadow experiment budget is fixed at 15 USD")


@dataclass(frozen=True)
class RoundTripEnvelope:
    spread_bps: Decimal
    break_even_move_bps: Decimal
    target_move_bps: Decimal
    loss_on_flat_mid_usd: Decimal
    buy_fee_estimate_usd: Decimal
    hypothetical_notional_usd: Decimal
    policy: ShadowCostPolicy

    def to_dict(self) -> dict[str, object]:
        # Round thresholds *upwards* rather than suggesting a lower price move
        # than required by the unrounded model.
        return {
            "kind": "OFFLINE_ILLUSTRATIVE_BTC_USD_ROUND_TRIP_COST_ENVELOPE",
            "observed_or_assumed_spread_bps": str(self.spread_bps),
            "buy_taker_fee_bps": str(self.policy.buy_taker_fee_bps),
            "sell_taker_fee_bps": str(self.policy.sell_taker_fee_bps),
            "entry_slippage_allowance_bps": str(
                self.policy.entry_slippage_allowance_bps),
            "exit_slippage_allowance_bps": str(
                self.policy.exit_slippage_allowance_bps),
            "minimum_net_return_target_bps": str(
                self.policy.required_net_margin_bps),
            "break_even_gross_midprice_rise_bps_rounded_up": str(
                self.break_even_move_bps.quantize(TWO_DECIMAL_BPS, rounding=ROUND_UP)),
            "target_gross_midprice_rise_bps_rounded_up": str(
                self.target_move_bps.quantize(TWO_DECIMAL_BPS, rounding=ROUND_UP)),
            "illustrative_loss_if_midprice_unchanged_usd": str(
                self.loss_on_flat_mid_usd.quantize(Decimal("0.0001"),
                                                   rounding=ROUND_UP)),
            "hypothetical_buy_fee_usd": str(self.buy_fee_estimate_usd),
            "hypothetical_buy_notional_usd": str(self.hypothetical_notional_usd),
            "disclosure": (
                "Spread is explicitly supplied/a hypothetical assumption, NOT a "
                "live quote. Slippage and fees are research inputs, not fill "
                "guarantees. Exit-market conditions may differ. No strategy edge "
                "or broker permission is implied."
            ),
        }


def estimate_round_trip(*, spread_bps: Decimal,
                        policy: ShadowCostPolicy | None = None) -> RoundTripEnvelope:
    """Exact Decimal normalized-mid accounting of virtual buy BTC fee/sell USD fee.

    Buy at ask(mid*(1+half_spread)) plus entry slippage. Alpaca BTC/USD buy fee
    can be charged in the received crypto; selling future BTC at the future bid
    minus exit slippage pays a taker fee on USD received. This does not presume
    the future spread can be measured today; the supplied spread is a stress
    assumption for both sides. Fee/slippage estimates may underestimate reality.

    Required midprice movement is solved algebraically: net proceeds >= original
    $15 (break-even) or >= $15*(1+target net margin) (research hurdle).
    """
    if type(spread_bps) is not Decimal:
        raise ValueError("spread must be explicitly represented with Decimal")
    spread = _d(spread_bps, "spread bps", upper=Decimal("1000"))
    costs = policy or ShadowCostPolicy()
    if not isinstance(costs, ShadowCostPolicy):
        raise ValueError("invalid cost policy")
    half_spread = spread / (BPS * Decimal("2"))
    entry_price_factor = (Decimal("1") + half_spread) * (
        Decimal("1") + costs.entry_slippage_allowance_bps / BPS)
    sell_proceeds_factor = (
        (Decimal("1") - half_spread)
        * (Decimal("1") - costs.exit_slippage_allowance_bps / BPS)
        * (Decimal("1") - costs.buy_taker_fee_bps / BPS)
        * (Decimal("1") - costs.sell_taker_fee_bps / BPS)
    )
    net_flat_factor = sell_proceeds_factor / entry_price_factor
    if not 0 < net_flat_factor <= 1:
        raise ValueError("invalid normalized round-trip economics")
    break_even = (Decimal("1") / net_flat_factor - Decimal("1")) * BPS
    target = (
        (Decimal("1") + costs.required_net_margin_bps / BPS)
        / net_flat_factor - Decimal("1")
    ) * BPS
    notional = costs.hypothetical_notional_usd
    return RoundTripEnvelope(
        spread, break_even, target,
        notional * (Decimal("1") - net_flat_factor),
        notional * costs.buy_taker_fee_bps / BPS, notional, costs,
    )


def review_shadow_signal(
    *, signal: StrategySignal, costs: RoundTripEnvelope,
    forecast_midprice_rise_bps: Decimal | None = None,
    independent_prospective_validation: bool = False,
) -> dict[str, object]:
    """Categorize a proposed signal for RESEARCH, never grant trade permission.

    EMA crossover itself supplies direction, not an independently validated
    expected size of future return. No forecast or no validation => BUY HOLD.
    A SELL can reduce an existing position/risk; a profit hurdle must not veto
    it, but this module cannot confirm inventory, risk or authorize an order.
    """
    if (not isinstance(signal, StrategySignal)
            or type(signal.action) is not Action
            or not isinstance(costs, RoundTripEnvelope)
            or type(independent_prospective_validation) is not bool):
        raise ValueError("invalid shadow review inputs")
    result: dict[str, object] = {
        "kind": "RESEARCH_ONLY_COST_AWARE_EMA_SIGNAL_REVIEW",
        "strategy_version": signal.strategy_version,
        "signal": signal.action.value,
        "signal_evidence_id": signal.evidence_id,
        "broker_order_submission": "DISABLED",
        "strategy_promoted": False,
        "automatic_trading": "DISABLED",
        "required_price_rise_for_net_target_bps_rounded_up": str(
            costs.target_move_bps.quantize(TWO_DECIMAL_BPS, rounding=ROUND_UP)),
        "decision": "HOLD",
        "reason_code": "NO_SIGNAL",
    }
    if signal.action is Action.HOLD:
        return result
    if signal.action is Action.SELL:
        result["decision"] = "SELL_CANDIDATE_REQUIRES_SEPARATE_POSITION_RISK_REVIEW"
        result["reason_code"] = "COST_GATE_MUST_NOT_PREVENT_RISK_REDUCING_EXIT"
        return result
    if forecast_midprice_rise_bps is None or not independent_prospective_validation:
        result["reason_code"] = "BUY_VETO_NO_INDEPENDENT_PROSPECTIVE_EDGE_EVIDENCE"
        return result
    if type(forecast_midprice_rise_bps) is not Decimal:
        result["reason_code"] = "BUY_VETO_INVALID_EXPECTED_MOVE"
        return result
    try:
        forecast = _d(
            forecast_midprice_rise_bps, "estimated future gross midprice rise",
            upper=Decimal("100000"))
    except ValueError:
        result["reason_code"] = "BUY_VETO_INVALID_EXPECTED_MOVE"
        return result
    if forecast < costs.target_move_bps:
        result["reason_code"] = "BUY_VETO_ESTIMATED_MOVE_BELOW_AFTER_COST_TARGET"
    else:
        result["decision"] = "RESEARCH_ONLY_BUY_CANDIDATE_PASSES_COST_ASSUMPTIONS"
        result["reason_code"] = "REQUIRES_INDEPENDENT_PERFORMANCE_AND_RISK_ACCEPTANCE"
    return result


def inspect_offline_shadow_progress(
    *,
    forward_root: str | Path = "data/forward",
    assumed_spread_bps: Decimal = Decimal("3"),
    collector_reader: Callable[..., object] | None = None,
) -> dict[str, object]:
    """Read-only prospective evidence count; no strategy return inference."""
    envelope = estimate_round_trip(spread_bps=assumed_spread_bps)
    output: dict[str, object] = {
        "kind": "OFFLINE_COST_AWARE_SHADOW_RESEARCH_STATUS",
        "schema_version": 1,
        "strategy_promoted": False,
        "strategy_execution": "DISABLED",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "market_data_request": "NONE",
        "keychain_access": "NONE",
        "journal_modifications": "NONE",
        "prospective_observations_verified": 0,
        "minimum_prospective_bars_for_INITIAL_sample_review":
            MINIMUM_PROSPECTIVE_RESEARCH_BARS,
        "research_status": "NOT_INITIALIZED_OR_UNAVAILABLE",
        "costs": envelope.to_dict(),
        "warning": (
            "A count of observations is NOT evidence of a profitable strategy. "
            "Prospective validation and genuinely after-cost results are still required."
        ),
    }
    if collector_reader is None:
        from .unattended_forward_cycle import status_unattended
        collector_reader = status_unattended
    try:
        existing = collector_reader(root=Path(forward_root).expanduser())
    except Exception as exc:
        output["research_status"] = "COLLECTOR_AUDIT_UNAVAILABLE"
        output["failure_class"] = type(exc).__name__
        return output
    if (not isinstance(existing, Mapping)
            or existing.get("kind") != "UNATTENDED_FORWARD_LOCAL_STATUS"
            or existing.get("broker_order_submission") != "DISABLED"):
        output["research_status"] = "COLLECTOR_STATUS_NOT_VERIFIED"
        return output
    tick = existing.get("latest_tick")
    if isinstance(tick, Mapping) and tick.get("decision") == "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE":
        output["research_status"] = "COLLECTOR_HALTED_PRESERVE_ORIGINAL_EVIDENCE"
        return output
    if existing.get("state") != "ARCHIVED_INTERNAL_EVIDENCE_VERIFIED":
        output["research_status"] = "NO_VERIFIED_AUTOMATIC_FORWARD_SEGMENT"
        return output
    count = existing.get("prospective_observations_verified")
    if (type(count) is not int or count < 0
            or existing.get("network_requests") != "NONE"):
        output["research_status"] = "INVALID_COLLECTOR_AUDIT_RESULT"
        return output
    output["prospective_observations_verified"] = count
    if count == 0:
        output["research_status"] = "AUTOMATIC_BOOTSTRAP_ONLY_NO_FORWARD_OBSERVATIONS"
    elif count < MINIMUM_PROSPECTIVE_RESEARCH_BARS:
        output["research_status"] = "ACCUMULATING_PROSPECTIVE_OBSERVATIONS"
    else:
        output["research_status"] = "MINIMUM_SAMPLE_COUNT_REACHED_NOT_EDGE_VALIDATION"
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline after-cost shadow research. No network/Keychain/orders/writes.")
    parser.add_argument("--forward-root", default="data/forward")
    parser.add_argument(
        "--assumed-spread-bps", default="3",
        help="Explicit HYPOTHETICAL spread for both legs, not a live quote (default: 3 bps).")
    args = parser.parse_args(argv)
    try:
        spread = Decimal(args.assumed_spread_bps)
        report = inspect_offline_shadow_progress(
            forward_root=args.forward_root, assumed_spread_bps=spread)
    except Exception as exc:
        report = {
            "kind": "OFFLINE_COST_AWARE_SHADOW_RESEARCH_STATUS",
            "research_status": "INVALID_RESEARCH_INPUT",
            "failure_class": type(exc).__name__,
            "broker_order_submission": "DISABLED",
            "market_data_request": "NONE",
            "strategy_execution": "DISABLED",
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["research_status"] in (
        "ACCUMULATING_PROSPECTIVE_OBSERVATIONS",
        "AUTOMATIC_BOOTSTRAP_ONLY_NO_FORWARD_OBSERVATIONS",
        "MINIMUM_SAMPLE_COUNT_REACHED_NOT_EDGE_VALIDATION") else 2


if __name__ == "__main__":
    raise SystemExit(main())
