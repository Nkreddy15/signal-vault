"""Versioned, deterministic baseline research strategy; not financial advice."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Sequence

from .market_data import Bar


class Action(str, Enum):
    HOLD = "hold"
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class StrategyConfig:
    fast_hours: int = 12
    slow_hours: int = 26
    strategy_version: str = "btc-hourly-ema-cross-v0.1"
    # 1 retains the shipped v0.1 behavior. 2 is a research-only, separately
    # versioned entry hypothesis: require one additional positive closed bar.
    entry_confirmation_bars: int = 1
    # None preserves all earlier strategy versions. A separately versioned
    # v0.3 research candidate can veto a BUY using only prior closed prices.
    entry_minimum_prior_24h_return_bps: Decimal | None = None

    def __post_init__(self) -> None:
        if not 1 < self.fast_hours < self.slow_hours <= 300:
            raise ValueError("invalid EMA windows")
        if not self.strategy_version.strip():
            raise ValueError("strategy version must be set")
        if type(self.entry_confirmation_bars) is not int or self.entry_confirmation_bars not in (1, 2):
            raise ValueError("entry confirmation must be 1 (baseline) or 2 (research candidate)")
        if self.entry_confirmation_bars == 2 and self.strategy_version == "btc-hourly-ema-cross-v0.1":
            raise ValueError("two-bar candidate must have its own strategy version")
        threshold = self.entry_minimum_prior_24h_return_bps
        if threshold is not None:
            if (not isinstance(threshold, Decimal) or not threshold.is_finite()
                    or threshold < 0 or threshold > 10000):
                raise ValueError("invalid prior-24h BUY momentum threshold")
            if self.entry_confirmation_bars != 1:
                raise ValueError("momentum research gate cannot combine with two-bar entry confirmation")
            if self.strategy_version in (
                "btc-hourly-ema-cross-v0.1",
                "btc-hourly-ema-cross-confirm2-v0.2-RESEARCH-ONLY",
            ):
                raise ValueError("momentum research gate requires its own candidate version")


@dataclass(frozen=True)
class StrategySignal:
    action: Action
    evidence_id: str
    bar_closed_at: str
    fast_ema: Decimal
    slow_ema: Decimal
    explanation: str
    strategy_version: str


def _last_two_emas(bars: Sequence[Bar], period: int) -> tuple[Decimal, Decimal]:
    alpha = Decimal(2) / Decimal(period + 1)
    previous = bars[0].close
    penultimate = previous
    for bar in bars[1:]:
        penultimate, previous = previous, alpha * bar.close + (Decimal(1) - alpha) * previous
    return penultimate, previous


def generate_signal(bars: Sequence[Bar], config: StrategyConfig | None = None) -> StrategySignal:
    """Use completed bars only, and return HOLD without manufacturing a trade.

    The caller must validate ordering/freshness/completeness using validate_bars.
    This strategy deliberately has no broker capabilities or access to secrets.
    """
    cfg = config or StrategyConfig()
    if not bars:
        raise ValueError("missing data")
    if len(bars) >= 2 and any(bars[i].start != bars[i - 1].close_time for i in range(1, len(bars))):
        raise ValueError("strategy cannot process gapped or unordered bars")
    if any(b.symbol != "BTC/USD" or b.timeframe_seconds != 3600 for b in bars):
        raise ValueError("unexpected instrument or interval")
    fast_prev, fast = _last_two_emas(bars, cfg.fast_hours)
    slow_prev, slow = _last_two_emas(bars, cfg.slow_hours)
    action = Action.HOLD
    why = "Warmup / no confirmed crossover; HOLD"
    if len(bars) >= cfg.slow_hours + 2:
        if fast_prev >= slow_prev and fast < slow:
            # Preserve immediate risk-reducing sell in both research versions.
            action, why = Action.SELL, "Confirmed fast EMA downward crossover at previous closed bar"
        elif cfg.entry_confirmation_bars == 1 and fast_prev <= slow_prev and fast > slow:
            threshold = cfg.entry_minimum_prior_24h_return_bps
            if threshold is None:
                # Preserve v0.1 exactly when the research-only filter is absent.
                action, why = Action.BUY, "Confirmed fast EMA upward crossover at previous closed bar"
            elif len(bars) < 25:
                why = "Prior-24h entry evidence unavailable; HOLD"
            else:
                # bars[-1] is the last completed hour. bars[-25] closed exactly
                # 24 hours earlier. bars that executes the order is NOT accessed.
                prior_24h_return_bps = (
                    bars[-1].close / bars[-25].close - Decimal("1")
                ) * Decimal("10000")
                if prior_24h_return_bps >= threshold:
                    action, why = Action.BUY, "Confirmed upward EMA cross and completed 24h momentum entry gate"
                else:
                    why = "Upward EMA crossover vetoed by prior-24h momentum; HOLD"
        elif cfg.entry_confirmation_bars == 2:
            # The previous bar must have been the first strictly positive
            # closed-bar EMA state after crossing, and the current *closed*
            # bar must still be positive. This emits exactly once, after two
            # positive closed bars, with no future-bar observations.
            if len(bars) >= cfg.slow_hours + 3 and fast_prev > slow_prev and fast > slow:
                fast_older, _ = _last_two_emas(bars[:-1], cfg.fast_hours)
                slow_older, _ = _last_two_emas(bars[:-1], cfg.slow_hours)
                if fast_older <= slow_older:
                    action, why = Action.BUY, "Two closed bars confirmed upward EMA crossover"
                else:
                    why = "No new two-bar-confirmed upward crossover; HOLD"
            elif fast_prev <= slow_prev and fast > slow:
                why = "First positive closed bar; awaiting entry confirmation; HOLD"
            else:
                why = "No new two-bar-confirmed upward crossover; HOLD"
        else:
            why = "No new confirmed crossover; HOLD"
    last = bars[-1]
    evidence = f"{cfg.strategy_version}|{last.source}|{last.symbol}|{last.close_time.isoformat()}|{last.close}|{action.value}"
    return StrategySignal(action, sha256(evidence.encode()).hexdigest(), last.close_time.isoformat(),
                          fast, slow, why, cfg.strategy_version)
