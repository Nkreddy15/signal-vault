"""Read-only sanitized Alpaca PAPER position/open-order inventory.

This command exists only to explain why the experimental PAPER preflight is
blocked. It cannot place, cancel, replace, close, or fund anything and does not
persist credentials, account identifiers, or raw provider payloads.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient, PaperReadStageError
from .paper_credentials import PaperCredentials

KIND="EXPERIMENTAL_PAPER_ACCOUNT_READ_ONLY_INVENTORY"
_SYMBOL=re.compile(r"^[A-Z0-9/._-]{1,32}$")
MAX_ROWS=20
MAX_BYTES=250_000


def _decimal_or_none(raw:object)->str|None:
    if raw in (None,""):
        return None
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,TypeError,ValueError):
        return None
    if not value.is_finite():
        return None
    return format(value,"f")


def _sanitize_position(row:Mapping[str,object])->dict[str,object]:
    symbol=str(row.get("symbol",""))
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("unsafe or missing provider position symbol")
    side=str(row.get("side","")).lower()
    if side not in ("long","short"):
        # Alpaca crypto positions are normally long; preserve UNKNOWN rather
        # than printing arbitrary provider text.
        side="unknown"
    return {
        "symbol":symbol,
        "side":side,
        "qty":_decimal_or_none(row.get("qty")),
        "market_value_usd":_decimal_or_none(row.get("market_value")),
        "avg_entry_price":_decimal_or_none(row.get("avg_entry_price")),
        "current_price":_decimal_or_none(row.get("current_price")),
        "unrealized_pl_usd":_decimal_or_none(row.get("unrealized_pl")),
    }


def inspect_paper_account(
    *,
    credentials:PaperCredentials,
    client_factory=PaperAlpacaReadClient,
)->dict[str,object]:
    client=client_factory(credentials.key_id,credentials.secret_key)
    try:
        positions=client.get_positions()
    except Exception as exc:
        if isinstance(exc,PaperReadStageError):
            raise
        raise PaperReadStageError("paper_positions",type(exc).__name__,getattr(exc,"code",None)) from None
    try:
        orders=client.get_open_orders()
    except Exception as exc:
        if isinstance(exc,PaperReadStageError):
            raise
        raise PaperReadStageError("paper_open_orders",type(exc).__name__,getattr(exc,"code",None)) from None

    if len(positions)>MAX_ROWS:
        raise ValueError("too many provider positions for bounded diagnostic")
    summary=tuple(_sanitize_position(row) for row in positions)
    symbols=[row["symbol"] for row in summary]
    return {
        "kind":KIND,
        "status":"AVAILABLE",
        "position_count":len(summary),
        "positions":list(summary),
        "open_order_count":len(orders),
        "position_symbols":symbols,
        "all_positions_are_btc_only":(
            bool(summary)
            and all(str(s).replace("/","")=="BTCUSD" for s in symbols)
        ),
        "network_action":"ALPACA_PAPER_GET_ONLY",
        "account_identifier_persisted":False,
        "credentials_persisted":False,
        "provider_payloads_persisted":False,
        "order_submission":"DISABLED",
        "order_cancel_replace":"DISABLED",
        "automatic_close_position":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "next_action":"REVIEW_EXISTING_PAPER_POSITION_BEFORE_ANY_NEW_EXECUTION",
    }


def _write_once(path:Path,value:Mapping[str,object])->None:
    p=Path(path)
    if p.is_symlink() or p.exists():
        raise ValueError("inventory output must be create-only")
    raw=(json.dumps(dict(value),sort_keys=True,indent=2)+"\n").encode()
    if not 0<len(raw)<=MAX_BYTES:
        raise ValueError("inventory receipt outside size bound")
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw);fh.flush();os.fsync(fh.fileno())


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Read-only sanitized Alpaca PAPER position inventory; no order path"
    )
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        creds=PaperCredentials.from_environment(os.environ)
        result=inspect_paper_account(credentials=creds)
        code=0
    except Exception as exc:
        result={
            "kind":KIND,
            "status":"FAIL_CLOSED",
            "failure_stage":getattr(exc,"stage","unknown"),
            "failure_class":getattr(exc,"failure_class",type(exc).__name__),
            "order_submission":"DISABLED",
            "order_cancel_replace":"DISABLED",
            "automatic_close_position":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        http=getattr(exc,"http_status",getattr(exc,"code",None))
        if isinstance(http,int):
            result["http_status"]=http
        code=2
    _write_once(args.output,result)
    print(json.dumps(result,sort_keys=True,indent=2))
    return code


if __name__=="__main__":
    raise SystemExit(main())
