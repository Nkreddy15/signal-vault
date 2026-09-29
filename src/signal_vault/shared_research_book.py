"""One shared $100 hypothetical multi-asset research book; ZERO broker connectivity.

Merge validated per-asset NEXT-OPEN events chronologically, process exits
before entries, and enforce ONE shared cash/exposure/loss/drawdown policy.
Never quietly hand each candidate its own independent trading bankroll.
Synthetic OHLCV and estimated friction are not a provider fill or future
performance. No imports of PAPER order, account, Keychain or live routes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from .multi_asset_simulation import (
    ExplicitRoundTripCosts, ResearchHypothesis, decide_on_prior_closes,
)
from .research_universe import (
    AssetClass, CandidateAsset, ResearchBar, candidate, validate_asset_dataset,
)
from .strategy import Action


@dataclass(frozen=True)
class SharedResearchLimits:
    initial_bankroll_usd: Decimal = Decimal("100")
    single_buy_usd: Decimal = Decimal("15")
    maximum_total_long_exposure_usd: Decimal = Decimal("30")
    daily_loss_cap_usd: Decimal = Decimal("3")
    peak_drawdown_cap_usd: Decimal = Decimal("10")
    minimum_synthetic_fill_usd: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        values=(
            self.initial_bankroll_usd,self.single_buy_usd,
            self.maximum_total_long_exposure_usd,self.daily_loss_cap_usd,
            self.peak_drawdown_cap_usd,self.minimum_synthetic_fill_usd)
        if any(type(v) is not Decimal or not v.is_finite() or v<=0 for v in values):
            raise ValueError("all research risk limits must be positive finite Decimals")
        if (self.single_buy_usd>self.maximum_total_long_exposure_usd or
                self.maximum_total_long_exposure_usd>self.initial_bankroll_usd or
                self.minimum_synthetic_fill_usd>self.single_buy_usd):
            raise ValueError("inconsistent shared portfolio dollar caps")


def simulate_shared_research_book(
    datasets: Mapping[str, Sequence[ResearchBar]],
    *,
    specs: Mapping[str, CandidateAsset],
    hypotheses: Mapping[str, ResearchHypothesis],
    assumptions: Mapping[str, ExplicitRoundTripCosts],
    as_of: datetime,
    equity_calendars: Mapping[str, Sequence[datetime]] | None = None,
    limits: SharedResearchLimits = SharedResearchLimits(),
) -> dict[str,object]:
    """Only closed history can generate a signal for an asset's next bar OPEN.

    Mark-to-market at event time uses current opens for instruments with an
    opening event and only the most recently CLOSED bar for other holdings.
    Two simultaneous BUYs compete for a single max $30, not $30 each.
    Selection order is predeclared sort(symbol); this is a deterministic
    simulation convention, not an alpha ranking/asset recommendation.
    """
    if as_of.tzinfo is None:
        raise ValueError("timezone-aware shared research as_of required")
    moment=as_of.astimezone(timezone.utc)
    names=tuple(sorted(datasets))
    if not names or len(names)>12:
        raise ValueError("shared research requires 1-12 proposed assets")
    if (set(names)!=set(specs) or set(names)!=set(hypotheses) or
            set(names)!=set(assumptions)):
        raise ValueError("independent per-symbol spec/strategy/cost required")
    calendars={} if equity_calendars is None else dict(equity_calendars)
    for sym in names:
        if candidate(sym)!=specs[sym]:
            raise ValueError("no unregistered or operationally enabled assets")
        if not isinstance(hypotheses[sym],ResearchHypothesis):
            raise ValueError("missing immutable research strategy hypothesis")
        if not isinstance(assumptions[sym],ExplicitRoundTripCosts):
            raise ValueError("missing per-market hypothetical execution costs")
    if set(calendars)-{
        sym for sym in names if specs[sym].asset_class == AssetClass.US_EQUITY}:
        raise ValueError("equity calendar must not be reused for crypto")
    quality={}
    rows={}
    events: dict[datetime,list[tuple[str,int,ResearchBar]]]={}
    for sym in names:
        data=tuple(datasets[sym])
        quality[sym]=validate_asset_dataset(
            data,spec=specs[sym],as_of=moment,
            expected_session_opens_utc=calendars.get(sym))
        rows[sym]=data
        start=max(hypotheses[sym].warmup_bars,2)
        if len(data)<=start:
            raise ValueError("insufficient per-symbol completed indicator warmup")
        for idx in range(start,len(data)):
            bar=data[idx]
            if bar.closed_utc>moment:
                raise ValueError("unclosed execution candle")
            events.setdefault(bar.start_utc,[]).append((sym,idx,bar))

    cash=limits.initial_bankroll_usd
    owned={sym:Decimal("0") for sym in names}
    fee_total=Decimal("0")
    peak=limits.initial_bankroll_usd
    max_dd=Decimal("0")
    daily_anchor=limits.initial_bankroll_usd
    last_day=None
    buys_blocked=False
    fills: list[dict[str,str]]=[]
    rejected: list[dict[str,str]]=[]
    signals={sym:{Action.HOLD.value:0,Action.BUY.value:0,Action.SELL.value:0}
             for sym in names}

    def previous_closed(sym: str, t: datetime) -> tuple[Decimal,datetime] | None:
        prior=[r for r in rows[sym] if r.closed_utc<=t]
        return (prior[-1].close,prior[-1].closed_utc) if prior else None

    def marked_holdings(marks: Mapping[str,Decimal]) -> Decimal:
        return sum((owned[sym]*marks[sym] for sym in names if owned[sym]>0),
                   Decimal("0"))

    for t in sorted(events):
        group=tuple(sorted(events[t],key=lambda item:item[0]))
        current={sym:bar for sym,_,bar in group}
        prior={sym:previous_closed(sym,t) for sym in names}
        for sym in names:
            if owned[sym]>0 and prior[sym] is None:
                raise ValueError("cannot mark an asset without prior completed price")
        if last_day!=t.date():
            last_day=t.date()
            # DAILY loss anchor is the PRIOR completed price, never the new
            # day's open. Otherwise overnight equity gaps could reset risk.
            daily_anchor=cash+sum(
                (owned[sym]*prior[sym][0] for sym in names if owned[sym]>0),
                Decimal("0"))
        marks={
            sym:(current[sym].open if sym in current else prior[sym][0])
            for sym in names if owned[sym]>0
        }
        # Very stale marks cannot authorize taking additional new risk.
        stale_holdings=any(
            (t-prior[sym][1] >
             (timedelta(hours=2) if specs[sym].asset_class==AssetClass.CRYPTO
              else timedelta(hours=96)))
            for sym in names if owned[sym]>0 and sym not in current
        )
        before=cash+marked_holdings(marks)
        peak=max(peak,before)
        max_dd=max(max_dd,peak-before)
        if (before<daily_anchor-limits.daily_loss_cap_usd or
                before<peak-limits.peak_drawdown_cap_usd):
            buys_blocked=True
        all_actions=[]
        for sym,idx,bar in group:
            known=rows[sym][:idx]
            if not known or known[-1].closed_utc>t:
                raise ValueError("next-open strategy must never see its own execution bar")
            signal=decide_on_prior_closes(
                known,config=hypotheses[sym],has_position=owned[sym]>0,
                next_open_utc=t)
            signals[sym][signal.action.value]+=1
            all_actions.append((signal,sym,bar))
        # SELL before BUY so same-clock risk and funding is unambiguous.
        all_actions.sort(key=lambda item:(0 if item[0].action==Action.SELL else 1,
                                          item[1]))
        for signal,sym,bar in all_actions:
            action=signal.action
            fees=assumptions[sym].taker_fee_bps/Decimal("10000")
            if action==Action.SELL and owned[sym]>0:
                price=bar.open*assumptions[sym].sell_price_multiplier
                gross=owned[sym]*price
                if gross<limits.minimum_synthetic_fill_usd:
                    rejected.append({"symbol":sym,"at":t.isoformat(),
                                     "code":"ESTIMATED_SELL_BELOW_MINIMUM"})
                    continue
                fee=gross*fees
                fills.append({
                    "symbol":sym,"side":"sell","at_open_utc":t.isoformat(),
                    "reference_open":str(bar.open),
                    "hypothetical_exec_price":str(price),
                    "quantity":str(owned[sym]),"estimated_fee_usd":str(fee),
                    "cash_change_usd":str(gross-fee),
                    "signal_sha256":signal.evidence_sha256,
                })
                cash+=gross-fee
                fee_total+=fee
                owned[sym]=Decimal("0")
                marks.pop(sym,None)
            elif action==Action.BUY and owned[sym]==0:
                if buys_blocked or stale_holdings:
                    code=("STALE_HELD_ASSET_MARK_BLOCKS_NEW_BUY" if stale_holdings
                          else "SHARED_DAILY_LOSS_OR_DRAWDOWN_NEW_BUY_BLOCK")
                elif cash<limits.single_buy_usd:
                    code="SHARED_CASH_INSUFFICIENT"
                elif (marked_holdings(marks)+limits.single_buy_usd >
                      limits.maximum_total_long_exposure_usd):
                    code="SHARED_TOTAL_LONG_EXPOSURE_LIMIT"
                else:
                    code=""
                if code:
                    rejected.append({"symbol":sym,"at":t.isoformat(),"code":code})
                    continue
                spend=limits.single_buy_usd
                price=bar.open*assumptions[sym].buy_price_multiplier
                fee=spend*fees
                qty=(spend-fee)/price
                cash-=spend
                fee_total+=fee
                owned[sym]=qty
                marks[sym]=bar.open
                fills.append({
                    "symbol":sym,"side":"buy","at_open_utc":t.isoformat(),
                    "reference_open":str(bar.open),
                    "hypothetical_exec_price":str(price),
                    "quantity":str(qty),"estimated_fee_usd":str(fee),
                    "cash_change_usd":str(-spend),
                    "signal_sha256":signal.evidence_sha256,
                })
        after=cash+marked_holdings(marks)
        peak=max(peak,after)
        max_dd=max(max_dd,peak-after)
        if (after<daily_anchor-limits.daily_loss_cap_usd or
                after<peak-limits.peak_drawdown_cap_usd):
            buys_blocked=True

    # Final asset marks are their last *completed* candle as of the common
    # evaluation endpoint; a stale final equity mark is explicitly reported.
    final_marks={}
    final_mark_times={}
    for sym in names:
        if owned[sym]>0:
            mark=previous_closed(sym,moment)
            if mark is None:
                raise ValueError("missing closing mark for held research asset")
            final_marks[sym]=mark[0]
            final_mark_times[sym]=mark[1].isoformat()
    final_cash_and_mark=cash+marked_holdings(final_marks)
    estimated_exit_cash = cash+sum(
        (owned[sym]*final_marks[sym]*assumptions[sym].sell_price_multiplier*
         (Decimal("1")-assumptions[sym].taker_fee_bps/Decimal("10000")))
        for sym in names if owned[sym]>0
    )
    max_dd=max(max_dd,max(peak,final_cash_and_mark)-final_cash_and_mark)
    return {
        "kind":"OFFLINE_SHARED_100USD_MULTI_ASSET_BOOK_NO_PROVIDER_ORDERS",
        "symbol_order":list(names),
        "allocation_policy":"SELLS_BEFORE_BUYS_THEN_SYMBOL_ASC_NO_ALPHA_RANKING",
        "historical_assets_sha256":{
            sym:quality[sym].content_sha256 for sym in names},
        "market_feed_by_asset":{sym:quality[sym].feed for sym in names},
        "hypotheses":{sym:hypotheses[sym].name for sym in names},
        "initial_bankroll_usd":str(limits.initial_bankroll_usd),
        "max_single_buy_usd":str(limits.single_buy_usd),
        "max_total_long_exposure_usd":str(limits.maximum_total_long_exposure_usd),
        "daily_loss_cap_usd":str(limits.daily_loss_cap_usd),
        "peak_drawdown_cap_usd":str(limits.peak_drawdown_cap_usd),
        "cash_usd":str(cash),
        "final_marked_equity_usd":str(final_cash_and_mark),
        "net_marked_pnl_usd":str(final_cash_and_mark-limits.initial_bankroll_usd),
        "estimated_liquidation_equity_usd":str(estimated_exit_cash),
        "net_pnl_if_hypothetically_liquidated_usd":
            str(estimated_exit_cash-limits.initial_bankroll_usd),
        "estimated_liquidation_not_an_order":True,
        "per_asset_hypothetical_cost_assumptions":{
            sym:{
                "fee_bps_each_side":str(assumptions[sym].taker_fee_bps),
                "full_spread_bps":str(assumptions[sym].full_spread_bps),
                "slippage_bps_each_side":str(assumptions[sym].slippage_per_side_bps),
            } for sym in names},
        "open_positions_quantity":{sym:str(q) for sym,q in owned.items() if q>0},
        "open_positions_last_closed_mark_utc":final_mark_times,
        "estimated_fee_total_usd":str(fee_total),
        "sampled_event_max_drawdown_usd":str(max_dd),
        "new_entries_gated_by_shared_loss_or_drawdown":buys_blocked,
        "synthetic_fills":fills,
        "rejections":rejected,
        "signal_counts":signals,
        "evaluated_distinct_next_open_event_times":len(events),
        "provider_paper_positions_queried":False,
        "past_data_does_not_prove_strategy_edge":True,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
