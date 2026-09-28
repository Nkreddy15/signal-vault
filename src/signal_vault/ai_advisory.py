"""Optional, bounded AI research veto for NEW PAPER BUY candidates only.

No model SDK, network transport, broker methods, credentials, user messages, or
order tools are present in this module. The injected response may only HOLD or
express NO_OBJECTION; Guardian and venue rules remain the exclusive authority.
The live paper worker does NOT install an AI transport by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Callable, Mapping, Protocol

from .market_data import CryptoQuote
from .strategy import Action, StrategySignal


class AdvisoryTransport(Protocol):
    def __call__(self, frame: Mapping[str, object]) -> object: ...


ALLOWED_REASONS = frozenset({
    "TREND_CONFIRMED", "NO_EDGE", "MOMENTUM_WEAK", "DATA_CONFLICT",
    "SPREAD_WIDE", "VOLATILITY", "UNKNOWN",
})


@dataclass(frozen=True)
class AdvisoryResult:
    verdict: str
    reason_code: str
    evidence_hash: str
    transport_used: bool

    @property
    def continue_to_guardian(self) -> bool:
        # This is NOT order permission; the independent Guardian still evaluates.
        return self.verdict == "NO_OBJECTION"


def _positive_amount(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError("advisory features must be positive finite Decimal")
    return str(value)


def build_public_signal_frame(signal: StrategySignal, quote: CryptoQuote) -> dict[str, object]:
    """Strict allowlist: only public BTC/USD indicators and quote, no account data."""
    if signal.action not in (Action.BUY, Action.SELL) or quote.symbol != "BTC/USD":
        raise ValueError("advisory only accepts a valid BTC/USD candidate")
    if not isinstance(signal.evidence_id, str) or not re.fullmatch(r"[a-f0-9]{64}", signal.evidence_id):
        raise ValueError("advisory evidence fingerprint missing")
    if not isinstance(signal.strategy_version, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,80}", signal.strategy_version):
        raise ValueError("unexpected advisory strategy version")
    if quote.timestamp.tzinfo is None or quote.timestamp.utcoffset() is None:
        raise ValueError("unqualified quote timestamp")
    if not isinstance(signal.bar_closed_at, str) or len(signal.bar_closed_at) > 40:
        raise ValueError("unqualified signal time")
    # Validate before comparing Decimals: NaN comparisons can raise
    # InvalidOperation and advisory input must fail with a controlled ValueError.
    _positive_amount(quote.bid)
    _positive_amount(quote.ask)
    # Validate finite positive values before doing Decimal comparisons: NaN
    # comparisons can raise InvalidOperation instead of a controlled refusal.
    quote_bid = _positive_amount(quote.bid)
    quote_ask = _positive_amount(quote.ask)
    if Decimal(quote_bid) > Decimal(quote_ask):
        raise ValueError("crossed advisory quote")
    # No free-form provider fields or strategy explanation are forwarded to a model.
    return {
        "schema_version": 1,
        "market": "crypto", "symbol": "BTC/USD",
        "candidate_action": signal.action.value,
        "strategy_version": signal.strategy_version,
        "strategy_evidence_sha256": signal.evidence_id,
        "last_bar_closed_utc": signal.bar_closed_at,
        "ema_fast": _positive_amount(signal.fast_ema),
        "ema_slow": _positive_amount(signal.slow_ema),
        "quote_bid_usd": quote_bid,
        "quote_ask_usd": quote_ask,
        "quote_timestamp_utc": quote.timestamp.isoformat(),
        "output_contract": "JSON only: verdict HOLD or NO_OBJECTION, reason_code from predefined enum. No orders or tool calls.",
    }


class BoundedAdvisoryGate:
    """One inert, injected review call. Any failure becomes HOLD without payload echo."""

    def __init__(self, transport: AdvisoryTransport) -> None:
        if not callable(transport):
            raise TypeError("advisory requires an injected callable; no default HTTP access")
        self._transport = transport

    def review(self, *, signal: StrategySignal, quote: CryptoQuote) -> AdvisoryResult:
        frame = build_public_signal_frame(signal, quote)
        evidence = sha256(json.dumps(frame, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        # A model may veto a new-money BUY but is NOT asked to authorize or
        # veto a risk-reducing SELL. Caller must enforce BUY-only usage.
        if signal.action is not Action.BUY:
            return AdvisoryResult("NO_OBJECTION", "RISK_REDUCING_EXIT", evidence, False)
        try:
            response = self._transport(frame)
        except Exception:
            return AdvisoryResult("HOLD", "ADVISOR_UNAVAILABLE", evidence, True)
        if not isinstance(response, Mapping) or set(response.keys()) != {"verdict", "reason_code"}:
            return AdvisoryResult("HOLD", "INVALID_ADVISORY_SCHEMA", evidence, True)
        verdict = response["verdict"]
        reason = response["reason_code"]
        if verdict not in ("HOLD", "NO_OBJECTION") or not isinstance(reason, str) or reason not in ALLOWED_REASONS:
            return AdvisoryResult("HOLD", "INVALID_ADVISORY_SCHEMA", evidence, True)
        if verdict == "NO_OBJECTION" and reason != "TREND_CONFIRMED":
            return AdvisoryResult("HOLD", "INVALID_ADVISORY_SCHEMA", evidence, True)
        if verdict == "HOLD" and reason == "TREND_CONFIRMED":
            return AdvisoryResult("HOLD", "INVALID_ADVISORY_SCHEMA", evidence, True)
        return AdvisoryResult(verdict, reason, evidence, True)
