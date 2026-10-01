"""Offline fully-invested cross-sectional strength-tilt research.

Keeps the same $30 gross crypto exposure as the passive six-asset comparator,
but reweights that exposure weekly using only already-closed 168-hour relative
strength. No network, credentials, broker, PAPER, or LIVE path.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from .research_universe import ResearchBar

SYMBOLS=("AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD")


@dataclass(frozen=True)
class StrengthTiltConfig:
    lookback_bars:int=168
    rebalance_interval_bars:int=168
    top_n:int=2
    top_target_usd:Decimal=Decimal("7.5")
    other_target_usd:Decimal=Decimal("3.75")
    bankroll_usd:Decimal=Decimal("100")
    fee_bps:Decimal=Decimal("25")
    full_spread_bps:Decimal=Decimal("4")
    slippage_bps:Decimal=Decimal("10")

    def __post_init__(self)->None:
        if type(self.lookback_bars) is not int or not 72<=self.lookback_bars<=336:
            raise ValueError("bounded lookback required")
        if type(self.rebalance_interval_bars) is not int or not 24<=self.rebalance_interval_bars<=336:
            raise ValueError("bounded rebalance interval required")
        if self.top_n!=2:
            raise ValueError("top_n fixed at two for predeclared tilt family")
        for v in (
            self.top_target_usd,self.other_target_usd,self.bankroll_usd,
            self.fee_bps,self.full_spread_bps,self.slippage_bps,
        ):
            if type(v) is not Decimal or not v.is_finite() or v<0:
                raise ValueError("finite nonnegative Decimal required")
        gross=self.top_target_usd*Decimal(self.top_n)+self.other_target_usd*Decimal(len(SYMBOLS)-self.top_n)
        if gross!=Decimal("30"):
            raise ValueError("tilt must preserve exact $30 gross exposure")
        if self.top_target_usd<=self.other_target_usd:
            raise ValueError("top assets must receive a larger target")


def _validate(datasets:Mapping[str,Sequence[ResearchBar]])->dict[str,tuple[ResearchBar,...]]:
    if set(datasets)!=set(SYMBOLS):
        raise ValueError("exact six-crypto universe required")
    rows={k:tuple(v) for k,v in datasets.items()}
    lengths={len(v) for v in rows.values()}
    if len(lengths)!=1 or not lengths or next(iter(lengths))<300:
        raise ValueError("aligned sufficiently deep hourly history required")
    first=rows[SYMBOLS[0]]
    for sym in SYMBOLS:
        seq=rows[sym]
        if any(b.symbol!=sym for b in seq):
            raise ValueError("symbol mismatch")
        if any(seq[i].start_utc!=first[i].start_utc for i in range(len(seq))):
            raise ValueError("cross-sectional history must be hour aligned")
        if any(seq[i].start_utc<=seq[i-1].start_utc for i in range(1,len(seq))):
            raise ValueError("history must be chronological")
    return rows


def _buy_price(open_price:Decimal,cfg:StrengthTiltConfig)->Decimal:
    return open_price*(Decimal("1")+(cfg.full_spread_bps/Decimal("2")+cfg.slippage_bps)/Decimal("10000"))


def _sell_price(open_price:Decimal,cfg:StrengthTiltConfig)->Decimal:
    return open_price*(Decimal("1")-(cfg.full_spread_bps/Decimal("2")+cfg.slippage_bps)/Decimal("10000"))


def _targets(
    rows:Mapping[str,Sequence[ResearchBar]],i:int,cfg:StrengthTiltConfig,
)->dict[str,Decimal]:
    scored=[]
    for s in SYMBOLS:
        now=rows[s][i-1].close
        before=rows[s][i-1-cfg.lookback_bars].close
        scored.append(((now/before-Decimal("1"))*Decimal("10000"),s))
    leaders={s for _,s in sorted(scored,reverse=True)[:cfg.top_n]}
    return {
        s:(cfg.top_target_usd if s in leaders else cfg.other_target_usd)
        for s in SYMBOLS
    }


def simulate_strength_tilt(
    datasets:Mapping[str,Sequence[ResearchBar]],
    *,
    config:StrengthTiltConfig,
    evaluation_start_index:int,
    evaluation_end_index:int,
)->dict[str,object]:
    rows=_validate(datasets)
    n=len(next(iter(rows.values())))
    if not config.lookback_bars+1<=evaluation_start_index<evaluation_end_index<=n:
        raise ValueError("evaluation range must follow closed-bar warmup")

    cash=config.bankroll_usd
    qty={s:Decimal("0") for s in SYMBOLS}
    fee_total=Decimal("0")
    fills=0
    peak=config.bankroll_usd
    max_dd=Decimal("0")

    passive_each=Decimal("5")
    passive_qty={}
    for s in SYMBOLS:
        px=_buy_price(rows[s][evaluation_start_index].open,config)
        fee=passive_each*config.fee_bps/Decimal("10000")
        passive_qty[s]=(passive_each-fee)/px

    for i in range(evaluation_start_index,evaluation_end_index):
        if (i-evaluation_start_index)%config.rebalance_interval_bars==0:
            target=_targets(rows,i,config)

            # Reduce exposures first so rebalance cannot require leverage.
            for s in SYMBOLS:
                mark=qty[s]*rows[s][i].open
                desired=target[s]
                if mark>desired and qty[s]>0:
                    excess=mark-desired
                    px=_sell_price(rows[s][i].open,config)
                    sell_qty=min(qty[s],excess/rows[s][i].open)
                    gross=sell_qty*px
                    fee=gross*config.fee_bps/Decimal("10000")
                    cash+=gross-fee
                    fee_total+=fee
                    qty[s]-=sell_qty
                    fills+=1

            # Then top up underweights. Cash reserve is intentionally large.
            for s in SYMBOLS:
                mark=qty[s]*rows[s][i].open
                desired=target[s]
                if mark<desired:
                    need=desired-mark
                    if need<=0 or cash<need:
                        continue
                    px=_buy_price(rows[s][i].open,config)
                    fee=need*config.fee_bps/Decimal("10000")
                    qty[s]+=(need-fee)/px
                    cash-=need
                    fee_total+=fee
                    fills+=1

        equity=cash+sum(qty[s]*rows[s][i].close for s in SYMBOLS)
        peak=max(peak,equity)
        max_dd=max(max_dd,peak-equity)

    final=evaluation_end_index-1
    final_equity=cash+sum(qty[s]*rows[s][final].close for s in SYMBOLS)
    passive_final=(config.bankroll_usd-Decimal("30"))+sum(
        passive_qty[s]*rows[s][final].close for s in SYMBOLS
    )
    return {
        "kind":"OFFLINE_FULLY_INVESTED_STRENGTH_TILT_RESEARCH_NO_ORDERS",
        "strategy":(
            f"full-invested-top2-{config.lookback_bars}h-"
            f"{config.top_target_usd}x{config.other_target_usd}-"
            f"every{config.rebalance_interval_bars}h"
        ),
        "net_marked_pnl_usd":str(final_equity-config.bankroll_usd),
        "passive_equal_weight_marked_pnl_usd":str(passive_final-config.bankroll_usd),
        "fill_count":fills,
        "max_marked_drawdown_usd":str(max_dd),
        "estimated_fees_usd":str(fee_total),
        "gross_target_exposure_usd":"30",
        "historical_only":True,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
