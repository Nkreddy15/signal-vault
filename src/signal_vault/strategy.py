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

    def __post_init__(self) -> None:
        if not 1 < self.fast_hours < self.slow_hours <= 300:
            raise ValueError("invalid EMA windows")
        if not self.strategy_version.strip():
            raise ValueError("strategy version must be set")


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
        if fast_prev <= slow_prev and fast > slow:
            action, why = Action.BUY, "Confirmed fast EMA upward crossover at previous closed bar"
        elif fast_prev >= slow_prev and fast < slow:
            action, why = Action.SELL, "Confirmed fast EMA downward crossover at previous closed bar"
        else:
            why = "No new confirmed crossover; HOLD"
    last = bars[-1]
    evidence = f"{cfg.strategy_version}|{last.source}|{last.symbol}|{last.close_time.isoformat()}|{last.close}|{action.value}"
    return StrategySignal(action, sha256(evidence.encode()).hexdigest(), last.close_time.isoformat(),
                          fast, slow, why, cfg.strategy_version)
