"""Pure cross-market pre-trade risk governor.

This is a shared safety kernel for crypto, US equities and Kalshi event
contracts.  It evaluates proposed risk against one bankroll and aggregate
limits.  It does not know any broker URL, API credential or order method and
its result is never trading authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Literal

MarketLane=Literal["crypto","us_equity","kalshi_event_contract"]
LANES=("crypto","us_equity","kalshi_event_contract")

@dataclass(frozen=True)
class CrossMarketRiskLimits:
    bankroll_usd:Decimal=Decimal("100")
    max_total_exposure_usd:Decimal=Decimal("30")
    max_single_new_risk_usd:Decimal=Decimal("10")
    max_open_positions:int=4
    daily_loss_cap_usd:Decimal=Decimal("3")
    peak_drawdown_cap_usd:Decimal=Decimal("10")
    crypto_cap_usd:Decimal=Decimal("20")
    us_equity_cap_usd:Decimal=Decimal("20")
    kalshi_event_contract_cap_usd:Decimal=Decimal("10")

    def __post_init__(self) -> None:
        money=(
            self.bankroll_usd,self.max_total_exposure_usd,
            self.max_single_new_risk_usd,self.daily_loss_cap_usd,
            self.peak_drawdown_cap_usd,self.crypto_cap_usd,
            self.us_equity_cap_usd,self.kalshi_event_contract_cap_usd,
        )
        if any(type(x) is not Decimal or not x.is_finite() or x<=0 for x in money):
            raise ValueError("risk limits require positive finite Decimal values")
        if not 1<=self.max_open_positions<=100:
            raise ValueError("invalid maximum open position count")
        if self.max_total_exposure_usd>self.bankroll_usd:
            raise ValueError("aggregate exposure cannot exceed bankroll")
        if self.max_single_new_risk_usd>self.max_total_exposure_usd:
            raise ValueError("single risk cannot exceed aggregate exposure")
        if any(x>self.max_total_exposure_usd for x in (
            self.crypto_cap_usd,self.us_equity_cap_usd,
            self.kalshi_event_contract_cap_usd)):
            raise ValueError("per-market cap cannot exceed aggregate exposure")

    def cap_for(self,lane:MarketLane) -> Decimal:
        if lane=="crypto":
            return self.crypto_cap_usd
        if lane=="us_equity":
            return self.us_equity_cap_usd
        if lane=="kalshi_event_contract":
            return self.kalshi_event_contract_cap_usd
        raise ValueError("unknown market lane")

def assess_new_risk(
    *,
    lane:MarketLane,
    proposed_max_loss_usd:Decimal,
    exposure_by_lane:Mapping[str,Decimal],
    open_positions:int,
    marked_equity_usd:Decimal,
    daily_anchor_equity_usd:Decimal,
    peak_equity_usd:Decimal,
    operator_halted:bool,
    limits:CrossMarketRiskLimits=CrossMarketRiskLimits(),
) -> dict[str,object]:
    """Assess one proposed position; return evidence, never an executable order."""
    if lane not in LANES:
        raise ValueError("unregistered market lane")
    if (type(proposed_max_loss_usd) is not Decimal or
            not proposed_max_loss_usd.is_finite() or proposed_max_loss_usd<=0):
        raise ValueError("positive finite proposed maximum loss required")
    if type(open_positions) is not int or open_positions<0:
        raise ValueError("invalid open position count")
    for value,name in (
        (marked_equity_usd,"marked equity"),
        (daily_anchor_equity_usd,"daily anchor"),
        (peak_equity_usd,"peak equity"),
    ):
        if type(value) is not Decimal or not value.is_finite() or value<0:
            raise ValueError("invalid "+name)
    exposure={}
    for name in LANES:
        value=exposure_by_lane.get(name,Decimal("0"))
        if type(value) is not Decimal or not value.is_finite() or value<0:
            raise ValueError("invalid market exposure")
        exposure[name]=value
    if set(exposure_by_lane)-set(LANES):
        raise ValueError("unregistered exposure lane")

    current_total=sum(exposure.values(),Decimal("0"))
    reasons=[]
    if operator_halted:
        reasons.append("OPERATOR_HALTED")
    if open_positions>=limits.max_open_positions:
        reasons.append("MAX_OPEN_POSITIONS")
    if proposed_max_loss_usd>limits.max_single_new_risk_usd:
        reasons.append("SINGLE_POSITION_RISK_CAP")
    if current_total+proposed_max_loss_usd>limits.max_total_exposure_usd:
        reasons.append("TOTAL_EXPOSURE_CAP")
    if exposure[lane]+proposed_max_loss_usd>limits.cap_for(lane):
        reasons.append("MARKET_LANE_EXPOSURE_CAP")
    if marked_equity_usd<daily_anchor_equity_usd-limits.daily_loss_cap_usd:
        reasons.append("DAILY_LOSS_HALT")
    if marked_equity_usd<peak_equity_usd-limits.peak_drawdown_cap_usd:
        reasons.append("PERSISTENT_PEAK_DRAWDOWN_HALT")

    admissible=not reasons
    return {
        "kind":"CROSS_MARKET_RISK_ASSESSMENT_NOT_ORDER_AUTHORIZATION",
        "lane":lane,
        "risk_admissible":admissible,
        "rejection_reasons":reasons,
        "current_total_exposure_usd":str(current_total),
        "proposed_max_loss_usd":str(proposed_max_loss_usd),
        "projected_total_exposure_usd":str(current_total+proposed_max_loss_usd),
        "current_lane_exposure_usd":str(exposure[lane]),
        "lane_cap_usd":str(limits.cap_for(lane)),
        "automatic_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "live_order_submission":"UNAVAILABLE",
        "assessment_is_not_trading_authorization":True,
    }
