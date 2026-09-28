"""Deterministic, fail-closed pre-order screening.

Phase 1 uses USD notional and spot long positions only. Future market adapters
must translate venue-specific quantity, contract payout and collateral into a
validated normalized exposure BEFORE any submission. No LLM can modify limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Tuple, Mapping

from .domain import PortfolioSnapshot, Side, TradeIntent


def _money_valid(value: Decimal) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value >= 0


@dataclass(frozen=True)
class RiskLimits:
    max_single_buy_usd: Decimal = Decimal("15")
    max_total_long_exposure_usd: Decimal = Decimal("30")
    max_daily_equity_loss_usd: Decimal = Decimal("3")
    max_peak_to_current_drawdown_usd: Decimal = Decimal("10")
    max_quote_age_seconds: int = 90
    allowed_market: str = "crypto"
    allowed_venue: str = "alpaca"
    allowed_symbol: str = "BTC/USD"

    def __post_init__(self) -> None:
        amounts = (self.max_single_buy_usd, self.max_total_long_exposure_usd,
                   self.max_daily_equity_loss_usd, self.max_peak_to_current_drawdown_usd)
        if any(not isinstance(v, Decimal) or not v.is_finite() or v <= 0 for v in amounts):
            raise ValueError("risk limits must be finite and strictly positive Decimal values")
        if self.max_single_buy_usd > self.max_total_long_exposure_usd:
            raise ValueError("single position limit cannot exceed portfolio exposure limit")
        if (not isinstance(self.max_quote_age_seconds, int) or
            isinstance(self.max_quote_age_seconds, bool) or
            not 1 <= self.max_quote_age_seconds <= 300):
            raise ValueError("invalid maximum quote age")
        if (self.allowed_market,self.allowed_venue,self.allowed_symbol) != ("crypto","alpaca","BTC/USD"):
            raise ValueError("only explicitly reviewed BTC/USD risk mandate is enabled")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: Tuple[str, ...]


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def evaluate(
        self,
        intent: TradeIntent,
        portfolio: PortfolioSnapshot,
        *,
        now: datetime | None = None,
    ) -> RiskDecision:
        """Reject unknown assets, bad snapshots, stale data and limit breaches.

        Daily/drawdown halts reject new buys; vetted risk-reducing long sells may
        proceed unless the independent emergency halt is engaged. No shorting.
        """
        reasons: list[str] = []
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            return RiskDecision(False, ("evaluation time must be timezone-aware",))

        if not isinstance(intent.side, Side):
            reasons.append("unrecognized order side")
        if (intent.market, intent.venue, intent.symbol) != (
            self.limits.allowed_market,
            self.limits.allowed_venue,
            self.limits.allowed_symbol,
        ):
            reasons.append("market, venue or symbol not enabled")
        if (not isinstance(intent.client_order_id, str) or not intent.client_order_id.strip() or
            not isinstance(intent.signal_id, str) or not intent.signal_id.strip()):
            reasons.append("missing unique order ID or signal evidence")
        if not _money_valid(intent.notional_usd) or intent.notional_usd == 0:
            reasons.append("invalid non-positive or non-finite order notional")
        if portfolio.halted:
            reasons.append("operator emergency halt is active")

        positions_valid = (isinstance(portfolio.long_positions_usd, Mapping) and
            all(isinstance(k, str) and k == "BTC/USD" for k in portfolio.long_positions_usd))
        amounts = (
            portfolio.equity_usd,
            portfolio.cash_usd,
            portfolio.peak_equity_usd,
            portfolio.session_start_equity_usd,
            portfolio.open_buy_notional_usd,
            *(portfolio.long_positions_usd.values() if positions_valid else ()),
        )
        amounts_valid = positions_valid and all(_money_valid(x) for x in amounts)
        if not amounts_valid:
            reasons.append("invalid portfolio accounting snapshot")
        else:
            if portfolio.peak_equity_usd < portfolio.equity_usd:
                reasons.append("inconsistent portfolio baseline")
            if portfolio.equity_usd < portfolio.cash_usd:
                reasons.append("cash exceeds equity; reconcile before ordering")

        stamp = intent.quote_timestamp
        if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            reasons.append("missing timezone-aware market quote")
        else:
            age = current - stamp
            if age < timedelta(seconds=-2) or age > timedelta(
                seconds=self.limits.max_quote_age_seconds
            ):
                reasons.append("missing or stale quote")

        # Never compare NaN / Infinity / non-Decimal values: reject safely first.
        if not amounts_valid or not _money_valid(intent.notional_usd) or intent.notional_usd == 0:
            return RiskDecision(False, tuple(reasons))

        if intent.side == Side.BUY:
            if intent.notional_usd > self.limits.max_single_buy_usd:
                reasons.append("single-buy allocation exceeded")
            if (portfolio.current_long_exposure_usd + portfolio.open_buy_notional_usd
                    + intent.notional_usd > self.limits.max_total_long_exposure_usd):
                reasons.append("portfolio long-exposure limit exceeded")
            if portfolio.cash_usd - portfolio.open_buy_notional_usd < intent.notional_usd:
                reasons.append("insufficient unreserved cash")
            if (portfolio.session_start_equity_usd - portfolio.equity_usd
                    >= self.limits.max_daily_equity_loss_usd):
                reasons.append("daily equity-loss pause triggered")
            if (portfolio.peak_equity_usd - portfolio.equity_usd
                    >= self.limits.max_peak_to_current_drawdown_usd):
                reasons.append("portfolio drawdown pause triggered")
        elif intent.side == Side.SELL:
            held_notional = portfolio.long_positions_usd.get(intent.symbol, Decimal("0"))
            if intent.notional_usd > held_notional:
                reasons.append("sell exceeds held long value; shorting disabled")
        return RiskDecision(not reasons, tuple(reasons))
