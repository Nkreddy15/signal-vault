"""Pure offline cross-sectional crypto strength allocator research.

Ranks the six approved crypto assets once per UTC day using only already-closed
72h returns. Holds at most two strongest assets when their 72h return is
positive enough; otherwise stays in cash. Rebalances only at daily boundaries
to reduce turnover. No network, credentials, broker, PAPER, or LIVE path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from .research_universe import ResearchBar

SYMBOLS=("AVAX/USD","BTC/USD","ETH/USD","LINK/USD","LTC/USD","SOL/USD")


@dataclass(frozen=True)
class CrossSectionalConfig:
    lookback_bars:int=72
    top_n:int=2
    min_strength_bps:Decimal=Decimal("150")
    rebalance_hour_utc:int=0
    bankroll_usd:Decimal=Decimal("100")
    per_asset_target_usd:Decimal=Decimal("15")
    fee_bps:Decimal=Decimal("25")
    full_spread_bps:Decimal=Decimal("4")
    slippage_bps:Decimal=Decimal("10")

    def __post_init__(self)->None:
        if not 24<=self.lookback_bars<=300:
            raise ValueError("bounded lookback required")
        if not 1<=self.top_n<=2:
            raise ValueError("top_n must be one or two")
        if not 0<=self.rebalance_hour_utc<=23:
            raise ValueError("valid UTC rebalance hour required")
        for v in (
            self.min_strength_bps,self.bankroll_usd,self.per_asset_target_usd,
            self.fee_bps,self.full_spread_bps,self.slippage_bps,
        ):
            if type(v) is not Decimal or not v.is_finite() or v<0:
                raise ValueError("finite nonnegative Decimal required")
        if self.per_asset_target_usd*self.top_n>Decimal("30"):
            raise ValueError("shared exposure cap exceeded")


def _validate(datasets:Mapping[str,Sequence[ResearchBar]])->dict[str,tuple[ResearchBar,...]]:
    if set(datasets)!=set(SYMBOLS):
        raise ValueError("exact six-crypto universe required")
    rows={k:tuple(v) for k,v in datasets.items()}
    lengths={len(v) for v in rows.values()}
    if len(lengths)!=1 or not lengths or next(iter(lengths))<200:
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


def _costed_buy_price(open_price:Decimal,cfg:CrossSectionalConfig)->Decimal:
    return open_price*(Decimal("1")+(cfg.full_spread_bps/Decimal("2")+cfg.slippage_bps)/Decimal("10000"))


def _costed_sell_price(open_price:Decimal,cfg:CrossSectionalConfig)->Decimal:
    return open_price*(Decimal("1")-(cfg.full_spread_bps/Decimal("2")+cfg.slippage_bps)/Decimal("10000"))


def simulate_cross_sectional_strength(
    datasets:Mapping[str,Sequence[ResearchBar]],
    *,
    config:CrossSectionalConfig=CrossSectionalConfig(),
    evaluation_start_index:int,
    evaluation_end_index:int,
)->dict[str,object]:
    rows=_validate(datasets)
    n=len(next(iter(rows.values())))
    if not (
        config.lookback_bars+1<=evaluation_start_index<evaluation_end_index<=n
    ):
        raise ValueError("evaluation range must follow closed-bar warmup")

    cash=config.bankroll_usd
    qty={s:Decimal("0") for s in SYMBOLS}
    fills=[]
    fee_total=Decimal("0")
    peak=config.bankroll_usd
    max_dd=Decimal("0")

    # Equal-weight passive comparator uses the same max $30 total exposure.
    passive_each=Decimal("30")/Decimal(len(SYMBOLS))
    passive_qty={}
    start_open={s:rows[s][evaluation_start_index].open for s in SYMBOLS}
    for s in SYMBOLS:
        entry=_costed_buy_price(start_open[s],config)
        fee=passive_each*config.fee_bps/Decimal("10000")
        passive_qty[s]=(passive_each-fee)/entry

    for i in range(evaluation_start_index,evaluation_end_index):
        stamp=rows[SYMBOLS[0]][i].start_utc.astimezone(timezone.utc)
        if stamp.hour==config.rebalance_hour_utc:
            scored=[]
            for s in SYMBOLS:
                now=rows[s][i-1].close
                before=rows[s][i-1-config.lookback_bars].close
                strength=(now/before-Decimal("1"))*Decimal("10000")
                scored.append((strength,s))
            target={
                s for strength,s in sorted(scored,reverse=True)[:config.top_n]
                if strength>=config.min_strength_bps
            }
            # exits first
            for s in SYMBOLS:
                if qty[s]>0 and s not in target:
                    px=_costed_sell_price(rows[s][i].open,config)
                    gross=qty[s]*px
                    fee=gross*config.fee_bps/Decimal("10000")
                    cash+=gross-fee
                    fee_total+=fee
                    fills.append((stamp.isoformat(),s,"sell"))
                    qty[s]=Decimal("0")
            # entries second, deterministic strongest-first
            for _,s in sorted(scored,reverse=True):
                if s not in target or qty[s]>0:
                    continue
                if cash<config.per_asset_target_usd:
                    continue
                px=_costed_buy_price(rows[s][i].open,config)
                fee=config.per_asset_target_usd*config.fee_bps/Decimal("10000")
                qty[s]=(config.per_asset_target_usd-fee)/px
                cash-=config.per_asset_target_usd
                fee_total+=fee
                fills.append((stamp.isoformat(),s,"buy"))

        mark=cash+sum(qty[s]*rows[s][i].close for s in SYMBOLS)
        peak=max(peak,mark)
        max_dd=max(max_dd,peak-mark)

    final_index=evaluation_end_index-1
    final_equity=cash+sum(qty[s]*rows[s][final_index].close for s in SYMBOLS)
    passive_final=(config.bankroll_usd-Decimal("30"))+sum(
        passive_qty[s]*rows[s][final_index].close for s in SYMBOLS
    )
    return {
        "kind":"OFFLINE_CROSS_SECTIONAL_STRENGTH_RESEARCH_NO_ORDERS",
        "strategy":"cross-sectional-top2-72h-150bps-daily-v1-predeclared",
        "net_marked_pnl_usd":str(final_equity-config.bankroll_usd),
        "passive_equal_weight_marked_pnl_usd":str(passive_final-config.bankroll_usd),
        "fill_count":len(fills),
        "max_marked_drawdown_usd":str(max_dd),
        "estimated_fees_usd":str(fee_total),
        "open_positions":sorted(s for s in SYMBOLS if qty[s]>0),
        "historical_only":True,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
