"""Multi-asset OFFLINE next-open strategy comparison, no provider/broker calls.

Different instruments share the same generic indicator evaluation; historical
series are validated per provider and exchange calendar first. All decisions
use closes with closed_utc <= the *next* bar's opening timestamp. BUY/SELL
denote synthetic fills exclusively, never recommendations or account orders.

A single-asset hypothetical portfolio is *not* twelve independently funded
live accounts. The portfolio-wide simulator will be a separately validated
module with ONE shared bankroll and aggregate exposure limits.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence

from .research_universe import (
    AssetClass, CandidateAsset, ResearchBar, candidate, validate_asset_dataset,
)
from .strategy import Action


def _positive(value: Decimal, *, zero_allowed: bool = False) -> Decimal:
    if (type(value) is not Decimal or not value.is_finite()
            or (value < 0 if zero_allowed else value <= 0)):
        raise ValueError("finite research Decimal required")
    return value


class HypothesisKind(str, Enum):
    CASH = "cash"
    PASSIVE = "one_allocation_buy_and_hold"
    EMA = "closed_bar_ema_cross"
    MOMENTUM = "closed_bar_lookback_momentum"


@dataclass(frozen=True)
class ResearchHypothesis:
    kind: HypothesisKind
    name: str
    fast_bars: int = 12
    slow_bars: int = 26
    lookback_bars: int = 24
    entry_return_bps: Decimal = Decimal("50")
    exit_return_bps: Decimal = Decimal("-50")

    def __post_init__(self) -> None:
        if (not isinstance(self.name,str) or not self.name.strip()
                or len(self.name)>90):
            raise ValueError("explicit immutable hypothesis version required")
        if not 1 < self.fast_bars < self.slow_bars <= 300:
            raise ValueError("invalid EMA windows")
        if type(self.lookback_bars) is not int or not 2 <= self.lookback_bars <= 300:
            raise ValueError("invalid lookback bar count")
        for value in (self.entry_return_bps, self.exit_return_bps):
            if type(value) is not Decimal or not value.is_finite():
                raise ValueError("invalid momentum threshold")
        if self.entry_return_bps < 0 or self.exit_return_bps > 0:
            raise ValueError("momentum entry/exit signs invalid")

    @property
    def warmup_bars(self) -> int:
        return max(self.slow_bars + 2,
                   self.lookback_bars + 1 if self.kind == HypothesisKind.MOMENTUM else 2)


HYPOTHESES: tuple[ResearchHypothesis, ...] = (
    ResearchHypothesis(HypothesisKind.CASH, "cash-v1-predeclared"),
    ResearchHypothesis(HypothesisKind.PASSIVE, "one-allocation-passive-v1-predeclared"),
    ResearchHypothesis(HypothesisKind.EMA, "generic-ema12x26-v1-predeclared"),
    ResearchHypothesis(HypothesisKind.MOMENTUM, "generic-momentum24bar50bps-v1-predeclared"),
)


@dataclass(frozen=True)
class ExplicitRoundTripCosts:
    """Estimated per-side taker friction, NOT measured provider fills.

    Spread = FULL estimated bid-ask spread; each synthetic side crosses half.
    For equities, fee assumptions must be separately supplied, not inherited
    blindly from crypto's historical 25bps taker fee hypothesis.
    """
    taker_fee_bps: Decimal
    full_spread_bps: Decimal
    slippage_per_side_bps: Decimal

    def __post_init__(self) -> None:
        for val in (self.taker_fee_bps,self.full_spread_bps,
                    self.slippage_per_side_bps):
            _positive(val,zero_allowed=True)
            if val > Decimal("1000"):
                raise ValueError("unreasonable unsupported synthetic cost assumption")

    @property
    def buy_price_multiplier(self) -> Decimal:
        return Decimal("1") + (
            self.full_spread_bps / Decimal("2") +
            self.slippage_per_side_bps) / Decimal("10000")

    @property
    def sell_price_multiplier(self) -> Decimal:
        return Decimal("1") - (
            self.full_spread_bps / Decimal("2") +
            self.slippage_per_side_bps) / Decimal("10000")


@dataclass(frozen=True)
class SyntheticDecision:
    symbol: str
    evaluated_close_utc: str
    hypothesis_version: str
    action: Action
    evidence_sha256: str


def _ema_pair(known: Sequence[ResearchBar], period: int) -> tuple[Decimal, Decimal]:
    alpha=Decimal("2") / Decimal(period+1)
    old=known[0].close
    prior=old
    for bar in known[1:]:
        prior,old=old,alpha*bar.close+(Decimal("1")-alpha)*old
    return prior,old


def decide_on_prior_closes(
    known: Sequence[ResearchBar],
    *,
    config: ResearchHypothesis,
    has_position: bool,
    next_open_utc: datetime,
) -> SyntheticDecision:
    """Never accept a candle closing after the hypothetical execution OPEN."""
    if not known:
        raise ValueError("no preceding completed candles")
    rows=tuple(known)
    symbol=rows[0].symbol
    if any(x.symbol!=symbol for x in rows):
        raise ValueError("mixed asset decision history")
    current=next_open_utc.astimezone(timezone.utc)
    if next_open_utc.tzinfo is None or any(b.closed_utc > current for b in rows):
        raise ValueError("future/open bars are forbidden in a decision")
    if any(rows[i].start_utc <= rows[i-1].start_utc
           for i in range(1,len(rows))):
        raise ValueError("decision bars must be chronological")
    action=Action.HOLD
    if config.kind == HypothesisKind.CASH:
        pass
    elif config.kind == HypothesisKind.PASSIVE:
        action=Action.HOLD if has_position else Action.BUY
    elif config.kind == HypothesisKind.EMA:
        if len(rows)>=config.slow_bars+2:
            fast_before,fast_now=_ema_pair(rows,config.fast_bars)
            slow_before,slow_now=_ema_pair(rows,config.slow_bars)
            if has_position and fast_before >= slow_before and fast_now < slow_now:
                action=Action.SELL
            elif (not has_position and fast_before <= slow_before and
                  fast_now > slow_now):
                action=Action.BUY
    elif config.kind == HypothesisKind.MOMENTUM:
        if len(rows) >= config.lookback_bars+1:
            prior=rows[-1-config.lookback_bars].close
            change=(rows[-1].close/prior-Decimal("1"))*Decimal("10000")
            if has_position and change <= config.exit_return_bps:
                action=Action.SELL
            elif not has_position and change >= config.entry_return_bps:
                action=Action.BUY
    else:
        raise ValueError("unknown hypothesis")

    last=rows[-1]
    src=(f"{config.name}|{symbol}|{last.feed}|{last.closed_utc.isoformat()}|"
         f"{last.close}|{action.value}|held={has_position}")
    return SyntheticDecision(symbol,last.closed_utc.isoformat(),config.name,action,
                             hashlib.sha256(src.encode()).hexdigest())


@dataclass(frozen=True)
class SyntheticFill:
    symbol: str
    at_open_utc: str
    side: str
    reference_open: str
    estimated_execution_price: str
    base_quantity: str
    cash_change_usd: str
    fee_usd: str
    decision_evidence_sha256: str


def _gross_equity(cash: Decimal, qty: Decimal, mark: Decimal) -> Decimal:
    return cash + qty*mark


def _cost_dict(costs: ExplicitRoundTripCosts) -> dict[str,str]:
    return {
        "taker_fee_bps_each_side":str(costs.taker_fee_bps),
        "full_spread_bps":str(costs.full_spread_bps),
        "slippage_bps_each_side":str(costs.slippage_per_side_bps),
    }


def simulate_one_asset(
    bars: Sequence[ResearchBar],
    *,
    spec: CandidateAsset,
    as_of: datetime,
    hypothesis: ResearchHypothesis,
    costs: ExplicitRoundTripCosts,
    expected_equity_session_opens_utc: Sequence[datetime] | None = None,
    evaluation_start_index: int | None = None,
    evaluation_end_index: int | None = None,
    bankroll_usd: Decimal = Decimal("100"),
    max_one_buy_usd: Decimal = Decimal("15"),
    min_synthetic_fill_usd: Decimal = Decimal("10"),
    daily_loss_cap_usd: Decimal = Decimal("3"),
    drawdown_cap_usd: Decimal = Decimal("10"),
) -> dict[str,object]:
    """Pure deterministic synthetic next-open book with *one* $100 sandbox.

    'Net' is relative to the assumed sampled open and includes hypothetical
    fees, spread crossing and slippage. Unliquidated holdings are final-marked
    only, NOT assumed sell fills.
    """
    if candidate(spec.symbol) != spec:
        raise ValueError("unregistered or operationally enabled instrument")
    if not isinstance(hypothesis,ResearchHypothesis) or not isinstance(costs,ExplicitRoundTripCosts):
        raise ValueError("explicit strategy and cost assumptions required")
    for val in (bankroll_usd,max_one_buy_usd,min_synthetic_fill_usd,
                daily_loss_cap_usd,drawdown_cap_usd):
        _positive(val)
    if max_one_buy_usd>bankroll_usd or min_synthetic_fill_usd>max_one_buy_usd:
        raise ValueError("synthetic buy exceeds allocated bankroll or venue minimum")
    seq=tuple(bars)
    review=validate_asset_dataset(
        seq,spec=spec,as_of=as_of,
        expected_session_opens_utc=expected_equity_session_opens_utc)
    low=max(hypothesis.warmup_bars,2)
    first=low if evaluation_start_index is None else evaluation_start_index
    last=len(seq) if evaluation_end_index is None else evaluation_end_index
    if (type(first) is not int or type(last) is not int or
            first<low or last>len(seq) or first>=last):
        raise ValueError("evaluation indices must follow predeclared warmup")
    cash=bankroll_usd
    quantity=Decimal("0")
    peak=bankroll_usd
    max_dd=Decimal("0")
    fee_total=Decimal("0")
    rejected: list[dict[str,str]]=[]
    fills: list[SyntheticFill]=[]
    counts={Action.HOLD.value:0,Action.BUY.value:0,Action.SELL.value:0}
    daily_anchor=bankroll_usd
    day=None
    # One asset uses the same v2 risk rule as the shared research book:
    # DAILY new-buy pause resets at the next UTC date; independent peak
    # drawdown entry halt persists for the remainder of this simulation.
    daily_entry_pause=False
    persistent_peak_halt=False
    daily_pause_dates:set[str]=set()
    # Model reference passive comparator: same max_one_buy allocation at the
    # same FIRST EVALUATION bar; it is not a retrospective whole-portfolio BTC
    # buy-and-hold and is deliberately not charged an unexecuted closing sale.
    open0=seq[first].open
    passive_entry=open0*costs.buy_price_multiplier
    passive_fee=max_one_buy_usd*costs.taker_fee_bps/Decimal("10000")
    passive_qty=(max_one_buy_usd-passive_fee)/passive_entry
    passive_final=(bankroll_usd-max_one_buy_usd)+passive_qty*seq[last-1].close

    for idx in range(first,last):
        candle=seq[idx]
        if candle.start_utc.date()!=day:
            day=candle.start_utc.date()
            daily_entry_pause=False
            # Prior completed close (not this bar's post-gap/open mark) anchors
            # the day so an overnight loss cannot be erased by resetting at open.
            prior_close=seq[idx-1].close
            daily_anchor=_gross_equity(cash,quantity,prior_close)
        before=_gross_equity(cash,quantity,candle.open)
        peak=max(peak,before)
        max_dd=max(max_dd,peak-before)
        if before < daily_anchor-daily_loss_cap_usd:
            daily_entry_pause=True
            daily_pause_dates.add(day.isoformat())
        if before < peak-drawdown_cap_usd:
            persistent_peak_halt=True
        signal=decide_on_prior_closes(
            seq[:idx],config=hypothesis,has_position=quantity>0,
            next_open_utc=candle.start_utc)
        counts[signal.action.value]+=1
        if signal.action==Action.BUY and quantity==0:
            if daily_entry_pause or persistent_peak_halt:
                rejected.append({
                    "at":candle.start_utc.isoformat(),
                    "code":"DAILY_LOSS_OR_DRAWDOWN_BLOCKS_NEW_BUY",
                    "risk_source":(
                        "PERSISTENT_PEAK_DRAWDOWN_HALT" if persistent_peak_halt
                        else "UTC_DAILY_ENTRY_PAUSE"),
                })
            elif cash<max_one_buy_usd:
                rejected.append({"at":candle.start_utc.isoformat(),
                                 "code":"INSUFFICIENT_HYPOTHETICAL_CASH"})
            else:
                price=candle.open*costs.buy_price_multiplier
                fee=max_one_buy_usd*costs.taker_fee_bps/Decimal("10000")
                qty=(max_one_buy_usd-fee)/price
                cash-=max_one_buy_usd
                quantity=qty
                fee_total+=fee
                fills.append(SyntheticFill(
                    spec.symbol,candle.start_utc.isoformat(),"buy",
                    str(candle.open),str(price),str(qty),
                    str(-max_one_buy_usd),str(fee),signal.evidence_sha256))
        elif signal.action==Action.SELL and quantity>0:
            proceeds_before_fee=quantity*candle.open*costs.sell_price_multiplier
            if proceeds_before_fee < min_synthetic_fill_usd:
                rejected.append({"at":candle.start_utc.isoformat(),
                                 "code":"SELL_BELOW_ASSUMED_MINIMUM"})
            else:
                fee=proceeds_before_fee*costs.taker_fee_bps/Decimal("10000")
                proceeds=proceeds_before_fee-fee
                cash+=proceeds
                fee_total+=fee
                fills.append(SyntheticFill(
                    spec.symbol,candle.start_utc.isoformat(),"sell",
                    str(candle.open),
                    str(candle.open*costs.sell_price_multiplier),
                    str(quantity),str(proceeds),str(fee),signal.evidence_sha256))
                quantity=Decimal("0")
        # Close is used for accounting AFTER this candle, not for this candle's
        # decision or execution. Post-close observations are not future leaks.
        mark=_gross_equity(cash,quantity,candle.close)
        peak=max(peak,mark)
        max_dd=max(max_dd,peak-mark)
        if mark < daily_anchor-daily_loss_cap_usd:
            daily_entry_pause=True
            daily_pause_dates.add(day.isoformat())
        if mark < peak-drawdown_cap_usd:
            persistent_peak_halt=True
    final=_gross_equity(cash,quantity,seq[last-1].close)
    estimated_exit=(
        cash + quantity * seq[last-1].close * costs.sell_price_multiplier *
        (Decimal("1")-costs.taker_fee_bps/Decimal("10000")))
    passive_estimated_exit=(
        (bankroll_usd-max_one_buy_usd)+passive_qty*seq[last-1].close*
        costs.sell_price_multiplier*
        (Decimal("1")-costs.taker_fee_bps/Decimal("10000")))
    return {
        "kind":"OFFLINE_PER_ASSET_NEXT_OPEN_SIMULATION_NOT_BROKER_TRADING",
        "symbol":spec.symbol,
        "market":spec.asset_class.value,
        "hypothesis":hypothesis.name,
        "feed":review.feed,
        "data_sha256":review.content_sha256,
        "historical_data_not_forward_strategy_proof":True,
        "evaluation_start_utc":seq[first].start_utc.isoformat(),
        "evaluation_end_utc":seq[last-1].closed_utc.isoformat(),
        "evaluation_bar_count":last-first,
        "initial_cash_usd":str(bankroll_usd),
        "final_marked_equity_usd":str(final),
        "net_marked_pnl_usd":str(final-bankroll_usd),
        "estimated_liquidation_equity_usd":str(estimated_exit),
        "net_pnl_if_hypothetically_liquidated_usd":str(estimated_exit-bankroll_usd),
        "estimated_liquidation_not_an_order":True,
        "passive_same_allocation_final_marked_usd":str(passive_final),
        "passive_estimated_liquidation_equity_usd":str(passive_estimated_exit),
        "passive_same_allocation_marked_pnl_usd":str(passive_final-bankroll_usd),
        "cash_only_comparator_final_usd":str(bankroll_usd),
        "max_marked_drawdown_usd":str(max_dd),
        "estimated_fees_usd":str(fee_total),
        "estimated_costs_not_measured_fills":_cost_dict(costs),
        "open_position_quantity":str(quantity),
        "mark_is_not_liquidated":quantity>0,
        "entry_blocked_by_loss_cap":daily_entry_pause or persistent_peak_halt,
        "research_risk_gate_semantics_version":
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt",
        "utc_daily_entry_pause_dates":sorted(daily_pause_dates),
        "utc_daily_entry_pause_current":daily_entry_pause,
        "persistent_peak_drawdown_entry_halt":persistent_peak_halt,
        "signal_counts":counts,
        "fills":[f.__dict__ for f in fills],
        "rejected":rejected,
        "shared_portfolio_risk_evaluated":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def chronological_three_way_review(
    bars: Sequence[ResearchBar],
    *,
    spec: CandidateAsset,
    as_of: datetime,
    hypothesis: ResearchHypothesis,
    costs: ExplicitRoundTripCosts,
    expected_equity_session_opens_utc: Sequence[datetime] | None = None,
) -> dict[str,object]:
    """Predeclared time-based 50/25/25 descriptive review, not model fitting.

    Indicator histories may use earlier folds, but portfolio cash/positions
    restart in each fold. No overlap in evaluated NEXT-OPEN candles.
    """
    n=len(bars)
    warm=max(hypothesis.warmup_bars,2)
    usable=n-warm
    if usable<24:
        raise ValueError("need at least 24 post-warmup bars for three folds")
    train_end=warm+usable//2
    validate_end=train_end+usable//4
    if min(train_end-warm,validate_end-train_end,n-validate_end)<4:
        raise ValueError("chronological folds too small")
    splits=(("development",warm,train_end),
            ("validation",train_end,validate_end),
            ("untouched_test",validate_end,n))
    results={}
    for name,first,last in splits:
        results[name]=simulate_one_asset(
            bars,spec=spec,as_of=as_of,hypothesis=hypothesis,costs=costs,
            expected_equity_session_opens_utc=expected_equity_session_opens_utc,
            evaluation_start_index=first,evaluation_end_index=last)
    return {
        "kind":"OFFLINE_PREDECLARED_CHRONOLOGICAL_THREE_WAY_RESEARCH",
        "hypothesis":hypothesis.name,
        "symbol":spec.symbol,
        "evaluation_folds":results,
        "selected_on_untouched_test":False,
        "hyperparameter_optimization_performed":False,
        "strategy_validated":False,
        "broker_order_submission":"DISABLED",
    }
