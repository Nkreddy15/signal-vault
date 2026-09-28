"""A genuine end-to-end LOCAL planning pipeline — never an executing trading bot.

Read validated closed bars -> immutable signal -> deterministic Guardian and
venue draft validation -> atomic journal. No API credentials, broker POST,
provider paper fill or claims of profitability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from .alpaca_paper import PaperOrderDraft
from .domain import PortfolioSnapshot, Side, TradeIntent
from .journal import OfflineDraftJournal
from .market_data import Bar, validate_bars
from .strategy import Action, StrategyConfig, generate_signal


@dataclass(frozen=True)
class PlanningResult:
    state: str
    explanation: str
    evidence_id: str
    draft: PaperOrderDraft | None = None


def plan_latest_closed_bar(
    candles: Sequence[Bar], *, now: datetime, portfolio: PortfolioSnapshot,
    journal: OfflineDraftJournal, strategy: StrategyConfig | None = None,
    confirmed_sell_quantity: Decimal | None = None,
) -> PlanningResult:
    """Evaluate ONE closed hourly bar; record only a local non-executable draft.

    Real paper trade execution will later require an independently verified
    fresh quote, provider order rules and a durable actual-order ledger.
    """
    cfg = strategy or StrategyConfig()
    history = validate_bars(candles, as_of=now, min_count=cfg.slow_hours + 2)
    signal = generate_signal(history, cfg)
    if signal.action is Action.HOLD:
        return PlanningResult("HOLD", signal.explanation, signal.evidence_id)
    has_long = portfolio.long_positions_usd.get("BTC/USD", Decimal("0")) > 0
    if signal.action is Action.BUY and has_long:
        return PlanningResult("HOLD", "Already holding BTC; no add-on entry in V1", signal.evidence_id)
    if signal.action is Action.SELL and not has_long:
        return PlanningResult("HOLD", "No reconciled BTC holding to sell", signal.evidence_id)
    if signal.action is Action.SELL and confirmed_sell_quantity is None:
        return PlanningResult("HOLD", "No provider-confirmed sell quantity; cannot create exit order", signal.evidence_id)
    order_id = "sv-" + signal.evidence_id[:30]
    notion = Decimal("15") if signal.action is Action.BUY else portfolio.long_positions_usd["BTC/USD"]
    intent = TradeIntent("crypto", "alpaca", "BTC/USD", Side(signal.action.value), notion,
                         order_id, signal.evidence_id, history[-1].close_time)
    try:
        draft = journal.record(intent, portfolio, checked_at=now,
                               reference_price=history[-1].close,
                               full_sell_quantity=confirmed_sell_quantity)
    except (ValueError, PermissionError) as exc:
        return PlanningResult("REJECTED", str(exc), signal.evidence_id)
    return PlanningResult("DRAFT_APPROVED_NOT_SUBMITTED", "Validated offline draft only",
                          signal.evidence_id, draft)
