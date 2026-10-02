"""One-shot supervised cleanup of one small existing BTC Alpaca PAPER position.

This module exists only to flatten a reviewed experimental/smoke-test PAPER
position so the empty-account preflight can be restored. It accepts a sanitized
Phase 163 inventory receipt, re-reads Alpaca PAPER state, requires the exact
reviewed BTC quantity to still match, refuses open orders/multiple positions,
caps eligible market value at $25, uses the shared position-reduction risk
governor, persists a durable journal, and performs at most one PAPER POST.

LIVE trading is unavailable by construction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .cross_market_risk import assess_position_reduction
from .experimental_paper_inventory import KIND as INVENTORY_KIND
from .multimarket_alpaca_paper_executor import MultiMarketAlpacaPaperOnceExecutor
from .multimarket_execution_journal import MultiMarketExecutionJournal, MultiMarketOrderDraft
from .multimarket_paper_router import CRYPTO_PAPER_ACK
from .paper_credentials import PaperCredentials
from .venue_rules import CryptoVenueRules

KIND="EXPERIMENTAL_BTC_PAPER_POSITION_CLEANUP"
MAX_SOURCE_BYTES=250_000
MAX_CLEANUP_MARKET_VALUE_USD=Decimal("25")


def _decimal(raw:object, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError("invalid "+name) from exc
    if not value.is_finite() or value<=0:
        raise ValueError("invalid "+name)
    return value


def _read_inventory(path:Path)->dict[str,object]:
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_SOURCE_BYTES:
        raise ValueError("bounded regular inventory receipt required")
    value=json.loads(p.read_text())
    if not isinstance(value,dict):
        raise ValueError("inventory receipt must be object")
    return value


def _reviewed_position(receipt:Mapping[str,object])->tuple[Decimal,Decimal]:
    if (
        receipt.get("kind")!=INVENTORY_KIND
        or receipt.get("status")!="AVAILABLE"
        or receipt.get("position_count")!=1
        or receipt.get("open_order_count")!=0
        or receipt.get("all_positions_are_btc_only") is not True
        or receipt.get("order_submission")!="DISABLED"
        or receipt.get("automatic_close_position")!="DISABLED"
        or receipt.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("safe single-BTC inventory receipt required")
    rows=receipt.get("positions")
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],Mapping):
        raise ValueError("exactly one reviewed position required")
    row=rows[0]
    if str(row.get("symbol","")).replace("/","")!="BTCUSD":
        raise ValueError("reviewed position must be BTC only")
    if row.get("side")!="long":
        raise ValueError("reviewed position must be long")
    qty=_decimal(row.get("qty"),"reviewed BTC quantity")
    value=_decimal(row.get("market_value_usd"),"reviewed market value")
    if qty.as_tuple().exponent < -9:
        raise ValueError("reviewed BTC quantity exceeds 9 decimals")
    if value>MAX_CLEANUP_MARKET_VALUE_USD:
        raise ValueError("reviewed PAPER position exceeds cleanup value cap")
    return qty,value


def _fresh_position(client:PaperAlpacaReadClient, expected_qty:Decimal):
    positions=client.get_positions()
    orders=client.get_open_orders()
    if orders:
        raise PermissionError("existing open PAPER orders block cleanup")
    if len(positions)!=1:
        raise PermissionError("cleanup requires exactly one current PAPER position")
    row=positions[0]
    if str(row.get("symbol","")).replace("/","")!="BTCUSD":
        raise PermissionError("cleanup position is not BTC")
    if str(row.get("side","")).lower()!="long":
        raise PermissionError("cleanup requires one long BTC position")
    qty=_decimal(row.get("qty"),"fresh BTC quantity")
    if qty!=expected_qty:
        raise PermissionError("fresh BTC quantity differs from reviewed inventory")
    market_value=_decimal(row.get("market_value"),"fresh BTC market value")
    current_price=_decimal(row.get("current_price"),"fresh BTC current price")
    if market_value>MAX_CLEANUP_MARKET_VALUE_USD:
        raise PermissionError("fresh PAPER position exceeds cleanup value cap")
    return row,qty,market_value,current_price


def cleanup_once(
    *,
    source_inventory:Mapping[str,object],
    credentials:PaperCredentials,
    now:datetime,
    acknowledgement:str="",
    execute:bool=False,
    journal_path:Path|None=None,
    reader_factory=PaperAlpacaReadClient,
    executor_factory=MultiMarketAlpacaPaperOnceExecutor,
)->dict[str,object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware cleanup time required")
    if execute and acknowledgement!=CRYPTO_PAPER_ACK:
        raise PermissionError("exact crypto PAPER acknowledgement required")
    expected_qty,reviewed_value=_reviewed_position(source_inventory)
    client=reader_factory(credentials.key_id,credentials.secret_key)
    account=client.get_account()
    if str(account.get("status","")).upper()!="ACTIVE":
        raise PermissionError("Alpaca PAPER account is not active")
    if account.get("trading_blocked") is not False:
        raise PermissionError("Alpaca PAPER account trading is not confirmed unblocked")
    _,qty,market_value,current_price=_fresh_position(client,expected_qty)
    asset=client.get_btc_asset()
    rules=CryptoVenueRules.from_asset(asset)
    rules.validate_sell_qty(qty,current_price)

    seed=f"cleanup|BTC/USD|{qty}".encode()
    client_id="svclean-"+hashlib.sha256(seed).hexdigest()[:18]
    if client.lookup_order(client_id) is not None:
        return {
            "kind":KIND,
            "status":"BLOCKED_DUPLICATE_CLEANUP_ORDER_EXISTS",
            "client_order_id":client_id,
            "paper_post_attempted":False,
            "paper_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }

    risk=assess_position_reduction(
        lane="crypto",
        current_lane_exposure_usd=market_value,
        proposed_reduction_usd=market_value,
        open_positions=1,
        operator_halted=False,
    )
    if risk["risk_admissible"] is not True:
        raise PermissionError("shared position-reduction risk governor blocked cleanup")

    draft=MultiMarketOrderDraft(
        client_order_id=client_id,
        market_lane="crypto",
        instrument="BTC/USD",
        max_loss_usd=market_value,
        payload={
            "symbol":"BTC/USD",
            "side":"sell",
            "type":"market",
            "time_in_force":"gtc",
            "client_order_id":client_id,
            "qty":format(qty,"f"),
        },
    )
    common={
        "kind":KIND,
        "instrument":"BTC/USD",
        "side":"sell",
        "reviewed_qty":format(expected_qty,"f"),
        "fresh_qty":format(qty,"f"),
        "reviewed_market_value_usd":str(reviewed_value),
        "fresh_market_value_usd":str(market_value),
        "fresh_current_price_usd":str(current_price),
        "cleanup_value_cap_usd":str(MAX_CLEANUP_MARKET_VALUE_USD),
        "client_order_id":client_id,
        "paper_account_active":True,
        "paper_account_trading_blocked":False,
        "risk_assessment":risk,
        "cleanup_only":True,
        "new_position_entry":"FORBIDDEN",
        "automatic_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    if not execute:
        return {
            **common,
            "status":"READY_FOR_EXPLICIT_PAPER_POSITION_CLEANUP",
            "required_acknowledgement":CRYPTO_PAPER_ACK,
            "paper_post_attempted":False,
            "paper_order_submission":"DISABLED",
        }

    if journal_path is None:
        raise ValueError("durable cleanup journal path required")
    path=Path(journal_path)
    if path.is_symlink() or path.exists() or not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("cleanup journal must be a new file under a real directory")
    with MultiMarketExecutionJournal(path) as journal:
        journal.record_approved_draft(draft,at=now)
        executor=executor_factory(
            paper_key=credentials.key_id,
            paper_secret=credentials.secret_key,
            journal=journal,
        )
        outcome=executor.submit_once(
            draft,
            risk_assessment=risk,
            acknowledgement=acknowledgement,
            at=now,
        )
    return {
        **common,
        "status":"PAPER_POSITION_CLEANUP_POST_ATTEMPT_RECORDED",
        "paper_post_attempted":outcome.paper_post_attempted,
        "paper_order_submission":"ATTEMPT_RECORDED",
        "execution_stage":outcome.stage.value,
        "provider_status":outcome.state.provider_status,
        "blind_retry_forbidden":True,
        "next_action":"RECONCILE_CLEANUP_BEFORE_ANY_NEW_EXECUTION",
    }


def _write_once(path:Path,value:Mapping[str,object])->None:
    p=Path(path)
    if p.is_symlink() or p.exists():
        raise ValueError("cleanup receipt must be create-only")
    raw=(json.dumps(dict(value),sort_keys=True,indent=2)+"\n").encode()
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw);fh.flush();os.fsync(fh.fileno())


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description="One-shot supervised BTC PAPER cleanup")
    parser.add_argument("--source-inventory",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--journal",type=Path)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--acknowledgement",default="")
    args=parser.parse_args(argv)
    creds=PaperCredentials.from_environment(os.environ)
    result=cleanup_once(
        source_inventory=_read_inventory(args.source_inventory),
        credentials=creds,
        now=datetime.now(timezone.utc),
        acknowledgement=args.acknowledgement,
        execute=args.execute,
        journal_path=args.journal,
    )
    _write_once(args.receipt,result)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
