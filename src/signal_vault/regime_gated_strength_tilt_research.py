"""Offline regime-gated fully-invested cross-sectional strength tilt.

Starts from the same $30 equal-weight six-crypto allocation as the passive
comparator. At weekly boundaries it tilts only when at least four of six assets
have positive already-closed 168-hour momentum; otherwise it stays/reverts to
equal weight. No network, credentials, broker, PAPER, or LIVE path.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from .research_universe import ResearchBar

SYMBOLS=("AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD")


@dataclass(frozen=True)
class RegimeTiltConfig:
    lookback_bars:int=168
    rebalance_interval_bars:int=168
    breadth_required:int=4
    top_n:int=2
    top_target_usd:Decimal=Decimal("10")
    other_target_usd:Decimal=Decimal("2.5")
    bankroll_usd:Decimal=Decimal("100")
    fee_bps:Decimal=Decimal("25")
    full_spread_bps:Decimal=Decimal("4")
    slippage_bps:Decimal=Decimal("10")

    def __post_init__(self)->None:
        if type(self.lookback_bars) is not int or not 72<=self.lookback_bars<=336:
            raise ValueError("bounded lookback required")
        if type(self.rebalance_interval_bars) is not int or not 24<=self.rebalance_interval_bars<=336:
            raise ValueError("bounded rebalance interval required")
        if type(self.breadth_required) is not int or not 1<=self.breadth_required<=6:
            raise ValueError("breadth threshold outside six-asset universe")
        if self.top_n!=2:
            raise ValueError("top_n fixed at two")
        for v in (
            self.top_target_usd,self.other_target_usd,self.bankroll_usd,
            self.fee_bps,self.full_spread_bps,self.slippage_bps,
        ):
            if type(v) is not Decimal or not v.is_finite() or v<0:
                raise ValueError("finite nonnegative Decimal required")
        if self.top_target_usd*2+self.other_target_usd*4!=Decimal("30"):
            raise ValueError("tilt must preserve exact $30 gross exposure")
        if self.top_target_usd<=self.other_target_usd:
            raise ValueError("leaders must receive larger target")


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


def _buy_price(p:Decimal,cfg:RegimeTiltConfig)->Decimal:
    return p*(Decimal("1")+(cfg.full_spread_bps/Decimal("2")+cfg.slippage_bps)/Decimal("10000"))


def _sell_price(p:Decimal,cfg:RegimeTiltConfig)->Decimal:
    return p*(Decimal("1")-(cfg.full_spread_bps/Decimal("2")+cfg.slippage_bps)/Decimal("10000"))


def _strengths(rows:Mapping[str,Sequence[ResearchBar]],i:int,cfg:RegimeTiltConfig):
    scored=[]
    for s in SYMBOLS:
        now=rows[s][i-1].close
        before=rows[s][i-1-cfg.lookback_bars].close
        scored.append(((now/before-Decimal("1"))*Decimal("10000"),s))
    return scored


def _rebalance(
    *,
    rows:Mapping[str,Sequence[ResearchBar]],
    i:int,
    cfg:RegimeTiltConfig,
    qty:dict[str,Decimal],
    cash:Decimal,
    targets:Mapping[str,Decimal],
)->tuple[Decimal,Decimal,int]:
    fees=Decimal("0")
    fills=0
    for s in SYMBOLS:
        mark=qty[s]*rows[s][i].open
        desired=targets[s]
        if mark>desired and qty[s]>0:
            excess=mark-desired
            px=_sell_price(rows[s][i].open,cfg)
            sell_qty=min(qty[s],excess/rows[s][i].open)
            gross=sell_qty*px
            fee=gross*cfg.fee_bps/Decimal("10000")
            cash+=gross-fee
            fees+=fee
            qty[s]-=sell_qty
            fills+=1
    for s in SYMBOLS:
        mark=qty[s]*rows[s][i].open
        desired=targets[s]
        if mark<desired:
            need=desired-mark
            if need<=0 or cash<need:
                continue
            px=_buy_price(rows[s][i].open,cfg)
            fee=need*cfg.fee_bps/Decimal("10000")
            qty[s]+=(need-fee)/px
            cash-=need
            fees+=fee
            fills+=1
    return cash,fees,fills


def simulate_regime_tilt(
    datasets:Mapping[str,Sequence[ResearchBar]],
    *,
    config:RegimeTiltConfig,
    evaluation_start_index:int,
    evaluation_end_index:int,
)->dict[str,object]:
    rows=_validate(datasets)
    n=len(next(iter(rows.values())))
    if not config.lookback_bars+1<=evaluation_start_index<evaluation_end_index<=n:
        raise ValueError("evaluation range must follow closed-bar warmup")

    cash=config.bankroll_usd
    qty={s:Decimal("0") for s in SYMBOLS}
    passive_qty={}
    fee_total=Decimal("0")
    fills=0
    peak=config.bankroll_usd
    max_dd=Decimal("0")

    # Strategy and comparator begin from the same costed equal-weight $30 book.
    for s in SYMBOLS:
        px=_buy_price(rows[s][evaluation_start_index].open,config)
        fee=Decimal("5")*config.fee_bps/Decimal("10000")
        bought=(Decimal("5")-fee)/px
        qty[s]=bought
        passive_qty[s]=bought
        cash-=Decimal("5")
        fee_total+=fee
        fills+=1

    regime="equal"
    tilt_activations=0
    equal_reversions=0

    for i in range(evaluation_start_index,evaluation_end_index):
        if i>evaluation_start_index and (i-evaluation_start_index)%config.rebalance_interval_bars==0:
            scored=_strengths(rows,i,config)
            positive=sum(1 for strength,_ in scored if strength>0)
            if positive>=config.breadth_required:
                leaders={s for _,s in sorted(scored,reverse=True)[:config.top_n]}
                targets={
                    s:(config.top_target_usd if s in leaders else config.other_target_usd)
                    for s in SYMBOLS
                }
                new_regime="tilt"
            else:
                targets={s:Decimal("5") for s in SYMBOLS}
                new_regime="equal"

            # In a continuing equal regime, preserve passive-like buy-and-hold
            # rather than paying needless equal-weight rebalancing costs.
            if not (regime=="equal" and new_regime=="equal"):
                cash,fees,new_fills=_rebalance(
                    rows=rows,i=i,cfg=config,qty=qty,cash=cash,targets=targets
                )
                fee_total+=fees
                fills+=new_fills
                if new_regime=="tilt" and regime!="tilt":
                    tilt_activations+=1
                if new_regime=="equal" and regime!="equal":
                    equal_reversions+=1
            regime=new_regime

        equity=cash+sum(qty[s]*rows[s][i].close for s in SYMBOLS)
        peak=max(peak,equity)
        max_dd=max(max_dd,peak-equity)

    final=evaluation_end_index-1
    final_equity=cash+sum(qty[s]*rows[s][final].close for s in SYMBOLS)
    passive_final=(config.bankroll_usd-Decimal("30"))+sum(
        passive_qty[s]*rows[s][final].close for s in SYMBOLS
    )
    return {
        "kind":"OFFLINE_REGIME_GATED_STRENGTH_TILT_RESEARCH_NO_ORDERS",
        "strategy":"equal-weight-unless-4of6-positive-168h-top2-10x2.5-weekly-v1",
        "net_marked_pnl_usd":str(final_equity-config.bankroll_usd),
        "passive_equal_weight_marked_pnl_usd":str(passive_final-config.bankroll_usd),
        "fill_count":fills,
        "max_marked_drawdown_usd":str(max_dd),
        "estimated_fees_usd":str(fee_total),
        "tilt_activations":tilt_activations,
        "equal_weight_reversions":equal_reversions,
        "final_regime":regime,
        "gross_target_exposure_usd":"30",
        "historical_only":True,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
