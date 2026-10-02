"""GET-only experimental PAPER readiness report.

This module cannot submit, cancel, replace, or reconcile orders. It always checks
the Alpaca PAPER account readiness and evaluates both fixed BTC research
hypotheses from one fresh closed 72-hour BTC/USD data window.

The result is an operator readiness receipt only. It does not validate a strategy
and it grants no PAPER or LIVE execution authority.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .market_data import AlpacaAuthenticatedCryptoBars
from .multi_asset_simulation import HYPOTHESES, HypothesisKind, decide_on_prior_closes
from .paper_credentials import PaperCredentials
from .research_universe import ResearchBar

KIND="EXPERIMENTAL_BTC_PAPER_GET_ONLY_READINESS_REPORT"
MAX_BYTES=1_000_000

STRATEGIES={
    h.name:h
    for h in HYPOTHESES
    if h.kind in (HypothesisKind.EMA,HypothesisKind.MOMENTUM)
}
EXPECTED_STRATEGIES={
    "generic-ema12x26-v1-predeclared",
    "generic-momentum24bar50bps-v1-predeclared",
}
if set(STRATEGIES)!=EXPECTED_STRATEGIES:
    raise RuntimeError("experimental readiness strategy set changed unexpectedly")


def _closed_hour(now:datetime)->datetime:
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware time required")
    utc=now.astimezone(timezone.utc)
    return utc.replace(minute=0,second=0,microsecond=0)


def _to_research_rows(bars,*,captured:datetime)->tuple[ResearchBar,...]:
    rows=[]
    for b in bars:
        rows.append(ResearchBar(
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
        ))
    return tuple(rows)


def build_readiness_report(
    *,
    credentials:PaperCredentials,
    now:datetime,
    bars_factory:Callable[...,object]=AlpacaAuthenticatedCryptoBars,
    reader_factory:Callable[...,object]=PaperAlpacaReadClient,
)->dict[str,object]:
    if not isinstance(credentials,PaperCredentials):
        raise ValueError("separate Alpaca PAPER credentials required")
    end=_closed_hour(now)
    start=end-timedelta(hours=72)
    captured=now.astimezone(timezone.utc)

    reader=reader_factory(credentials.key_id,credentials.secret_key)
    account=reader.readiness()

    bars_client=bars_factory(credentials.key_id,credentials.secret_key)
    bars=bars_client.fetch(start=start,end=end,as_of=captured)
    rows=_to_research_rows(bars,captured=captured)
    if len(rows)!=72:
        raise ValueError("exact 72 closed BTC hourly bars required")

    actions={}
    buys=[]
    for name in sorted(STRATEGIES):
        decision=decide_on_prior_closes(
            rows,
            config=STRATEGIES[name],
            has_position=False,
            next_open_utc=end,
        )
        actions[name]={
            "hypothetical_action":decision.action.value,
            "evaluated_close_utc":decision.evaluated_close_utc,
            "evidence_sha256":decision.evidence_sha256,
        }
        if decision.action.value=="buy":
            buys.append(name)

    if account.ready is not True:
        status="BLOCKED_PAPER_ACCOUNT_PREFLIGHT"
        selected=None
    elif len(buys)==0:
        status="NO_CURRENT_EXPERIMENTAL_BUY"
        selected=None
    elif len(buys)==1:
        status="READY_FOR_EXPLICIT_EXPERIMENTAL_PAPER_REVIEW"
        selected=buys[0]
    else:
        status="BLOCKED_MULTIPLE_EXPERIMENTAL_BUYS_NO_RANKING"
        selected=None

    return {
        "kind":KIND,
        "status":status,
        "checked_at_utc":captured.isoformat(),
        "data_window_start_utc":start.isoformat(),
        "data_window_end_utc":end.isoformat(),
        "closed_btc_hour_count":len(rows),
        "paper_account_ready":account.ready is True,
        "paper_account_readiness_reasons":list(account.reasons),
        "paper_logical_cap_usd":str(account.logical_cap_usd),
        "strategy_actions":actions,
        "buy_signal_strategies":buys,
        "selected_strategy_for_operator_review":selected,
        "experimental_only":True,
        "strategy_validated":False,
        "independent_prospective_gate_passed":False,
        "actions_are_order_authority":False,
        "automatic_paper_activation":"DISABLED",
        "paper_order_submission":"DISABLED",
        "network_action":"ALPACA_DATA_GET_AND_PAPER_ACCOUNT_GET_ONLY",
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
    }


def _write_once(path:Path,value:Mapping[str,object])->None:
    p=Path(path)
    if p.is_symlink() or p.exists():
        raise ValueError("readiness output must be create-only")
    raw=(json.dumps(dict(value),sort_keys=True,indent=2)+"\n").encode()
    if not 0<len(raw)<=MAX_BYTES:
        raise ValueError("readiness receipt size outside bound")
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw);fh.flush();os.fsync(fh.fileno())


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="GET-only experimental BTC PAPER readiness report; no order path"
    )
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        creds=PaperCredentials.from_environment(os.environ)
        result=build_readiness_report(
            credentials=creds,
            now=datetime.now(timezone.utc),
        )
        code=0
    except Exception as exc:
        result={
            "kind":KIND,
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "actions_are_order_authority":False,
            "automatic_paper_activation":"DISABLED",
            "paper_order_submission":"DISABLED",
            "live_order_submission":"UNAVAILABLE",
            "live_trading":"UNAVAILABLE",
        }
        code=2
    _write_once(args.output,result)
    print(json.dumps(result,sort_keys=True,indent=2))
    return code


if __name__=="__main__":
    raise SystemExit(main())
