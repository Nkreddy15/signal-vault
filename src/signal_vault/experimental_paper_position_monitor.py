"""GET-only held-position strategy monitor for experimental Alpaca PAPER BTC.

Evaluates the fixed experimental strategy in the HELD state using only fully
closed hourly BTC/USD bars plus read-only Alpaca PAPER position/open-order GETs.
It cannot submit, cancel, replace, or close any order.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .market_data import AlpacaPublicCryptoBars
from .multi_asset_simulation import HYPOTHESES, HypothesisKind, decide_on_prior_closes
from .paper_credentials import PaperCredentials
from .research_universe import ResearchBar

KIND="EXPERIMENTAL_BTC_PAPER_HELD_POSITION_MONITOR"
MAX_BYTES=250_000

STRATEGIES={
    h.name:h
    for h in HYPOTHESES
    if h.kind in (HypothesisKind.EMA,HypothesisKind.MOMENTUM)
}
EXPECTED={
    "generic-ema12x26-v1-predeclared",
    "generic-momentum24bar50bps-v1-predeclared",
}
if set(STRATEGIES)!=EXPECTED:
    raise RuntimeError("experimental strategy set changed unexpectedly")


def _decimal(raw:object,name:str)->Decimal:
    try:
        v=Decimal(str(raw))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError("invalid "+name) from exc
    if not v.is_finite() or v<=0:
        raise ValueError("invalid "+name)
    return v


def _closed_hour(now:datetime)->datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware time required")
    utc=now.astimezone(timezone.utc)
    return utc.replace(minute=0,second=0,microsecond=0)


def _rows(bars,*,captured:datetime):
    return tuple(
        ResearchBar(
            symbol=b.symbol,
            start_utc=b.start,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            feed=b.source,
            captured_utc=captured,
            prospective=False,
        )
        for b in bars
    )


def inspect_held_position(
    *,
    strategy_name:str,
    credentials:PaperCredentials,
    now:datetime,
    reader_factory=PaperAlpacaReadClient,
    bars_factory=AlpacaPublicCryptoBars,
)->dict[str,object]:
    if strategy_name not in STRATEGIES:
        raise ValueError("unsupported experimental strategy")
    end=_closed_hour(now)
    start=end-timedelta(hours=72)
    captured=now.astimezone(timezone.utc)

    reader=reader_factory(credentials.key_id,credentials.secret_key)
    account=reader.get_account()
    if str(account.get("status","")).upper()!="ACTIVE":
        raise PermissionError("PAPER account is not active")
    if account.get("trading_blocked") is not False:
        raise PermissionError("PAPER account trading is blocked")

    positions=reader.get_positions()
    open_orders=reader.get_open_orders()
    if open_orders:
        raise PermissionError("open PAPER orders block held-position evaluation")
    if len(positions)!=1:
        raise PermissionError("exactly one PAPER position required")
    pos=positions[0]
    if str(pos.get("symbol","")).replace("/","")!="BTCUSD":
        raise PermissionError("held PAPER position must be BTC")
    if str(pos.get("side","")).lower()!="long":
        raise PermissionError("held PAPER position must be long")
    qty=_decimal(pos.get("qty"),"BTC quantity")
    market_value=_decimal(pos.get("market_value"),"BTC market value")
    avg_entry=_decimal(pos.get("avg_entry_price"),"average entry price")
    current_price=_decimal(pos.get("current_price"),"current price")

    bars=bars_factory().fetch(start=start,end=end,as_of=captured)
    rows=_rows(bars,captured=captured)
    if len(rows)!=72:
        raise ValueError("exactly 72 closed hourly BTC bars required")

    cfg=STRATEGIES[strategy_name]
    decision=decide_on_prior_closes(
        rows,
        config=cfg,
        has_position=True,
        next_open_utc=end,
    )

    strategy_metrics={}
    if cfg.kind is HypothesisKind.MOMENTUM:
        prior=rows[-1-cfg.lookback_bars].close
        latest=rows[-1].close
        change_bps=(latest/prior-Decimal("1"))*Decimal("10000")
        strategy_metrics={
            "lookback_hours":cfg.lookback_bars,
            "current_24h_return_bps":str(change_bps),
            "sell_threshold_bps":str(cfg.exit_return_bps),
            "sell_condition":"current_24h_return_bps <= sell_threshold_bps",
        }
    elif cfg.kind is HypothesisKind.EMA:
        strategy_metrics={
            "fast_ema_hours":cfg.fast_bars,
            "slow_ema_hours":cfg.slow_bars,
            "sell_condition":"fast EMA crosses below slow EMA on fully closed hourly bars",
        }

    return {
        "kind":KIND,
        "status":"AVAILABLE",
        "checked_at_utc":captured.isoformat(),
        "strategy":strategy_name,
        "held_position":True,
        "btc_qty":format(qty,"f"),
        "market_value_usd":str(market_value),
        "avg_entry_price_usd":str(avg_entry),
        "provider_current_price_usd":str(current_price),
        "evaluated_close_utc":decision.evaluated_close_utc,
        "held_state_action":decision.action.value,
        "signal_evidence_sha256":decision.evidence_sha256,
        "strategy_metrics":strategy_metrics,
        "strategy_validated":False,
        "experimental_only":True,
        "action_is_order_authority":False,
        "automatic_sell":"DISABLED",
        "order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "next_action":(
            "REVIEW_SUPERVISED_PAPER_SELL"
            if decision.action.value=="sell"
            else "CONTINUE_HOURLY_HELD_POSITION_OBSERVATION"
        ),
    }


def _write_once(path:Path,value:Mapping[str,object])->None:
    p=Path(path)
    if p.is_symlink() or p.exists():
        raise ValueError("monitor receipt must be create-only")
    raw=(json.dumps(dict(value),sort_keys=True,indent=2)+"\n").encode()
    if not 0<len(raw)<=MAX_BYTES:
        raise ValueError("monitor receipt outside size bound")
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw);fh.flush();os.fsync(fh.fileno())


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="GET-only held-position strategy monitor; no order path"
    )
    parser.add_argument("--strategy",required=True,choices=sorted(STRATEGIES))
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    creds=PaperCredentials.from_environment(os.environ)
    result=inspect_held_position(
        strategy_name=args.strategy,
        credentials=creds,
        now=datetime.now(timezone.utc),
    )
    _write_once(args.output,result)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
