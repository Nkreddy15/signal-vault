"""Read-only recovery/reconciliation for one experimental BTC PAPER sandbox run.

Consumes the archived Phase 154 receipt+journal, never submits/cancels/replaces
orders, and performs only authoritative Alpaca PAPER GETs.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .experimental_paper_sandbox import KIND as SOURCE_KIND
from .multimarket_alpaca_reconciliation import reconcile_alpaca_paper_order_lookup
from .multimarket_execution_journal import MultiMarketExecutionJournal
from .paper_order_state import Stage
from .paper_credentials import PaperCredentials

KIND="EXPERIMENTAL_BTC_PAPER_READ_ONLY_RECONCILIATION"
MAX_BYTES=4_000_000


def _read_json(path:Path)->dict[str,object]:
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_BYTES:
        raise ValueError("bounded regular sandbox receipt required")
    value=json.loads(p.read_text())
    if not isinstance(value,dict):
        raise ValueError("sandbox receipt must be JSON object")
    return value


def _write_once(path:Path,value:Mapping[str,object])->None:
    p=Path(path)
    if p.is_symlink() or p.exists():
        raise ValueError("reconciliation receipt must be create-only")
    raw=(json.dumps(dict(value),sort_keys=True,indent=2)+"\n").encode()
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(raw);fh.flush();os.fsync(fh.fileno())


def _nonnegative_decimal(raw:object, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError("invalid "+name) from exc
    if not value.is_finite() or value<0:
        raise ValueError("invalid "+name)
    return value


def reconcile_experimental_paper(
    *,
    source_receipt:Mapping[str,object],
    journal_path:Path,
    credentials:PaperCredentials,
    at:datetime,
    reader_factory=PaperAlpacaReadClient,
)->dict[str,object]:
    if (
        not isinstance(source_receipt,Mapping)
        or source_receipt.get("kind")!=SOURCE_KIND
        or source_receipt.get("experimental_only") is not True
        or source_receipt.get("strategy_validated") is not False
        or source_receipt.get("live_trading")!="UNAVAILABLE"
        or source_receipt.get("paper_post_attempted") is not True
        or source_receipt.get("paper_order_submission")!="ATTEMPT_RECORDED"
    ):
        raise ValueError("executed experimental PAPER receipt required")
    client_id=source_receipt.get("client_order_id")
    if not isinstance(client_id,str) or not client_id.startswith("svexp-"):
        raise ValueError("experimental client order id required")
    p=Path(journal_path)
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_BYTES:
        raise ValueError("bounded regular execution journal required")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware reconciliation time required")

    reader=reader_factory(credentials.key_id,credentials.secret_key)
    with MultiMarketExecutionJournal(p) as journal:
        recovered=journal.recover_pending_after_restart(at=at)
        draft=journal.get_approved_draft(client_id)
        if (
            draft.market_lane!="crypto"
            or draft.instrument!="BTC/USD"
            or draft.client_order_id!=client_id
        ):
            raise ValueError("sandbox journal draft mismatch")
        outcome=reconcile_alpaca_paper_order_lookup(
            journal=journal,
            reader=reader,
            client_order_id=client_id,
            expected_instrument="BTC/USD",
            at=at,
        )
        account=reader.get_account()
        positions=reader.get_positions()
        open_orders=reader.get_open_orders()

        if str(account.get("status","")).upper()!="ACTIVE":
            raise ValueError("PAPER account not active during reconciliation")
        if account.get("trading_blocked") is not False:
            raise ValueError("PAPER account trading unexpectedly blocked during reconciliation")
        try:
            equity=Decimal(str(account.get("equity")))
        except Exception as exc:
            raise ValueError("invalid PAPER account equity") from exc
        if not equity.is_finite() or equity<0:
            raise ValueError("invalid PAPER account equity")

        btc_positions=[
            row for row in positions
            if str(row.get("symbol","")).replace("/","")=="BTCUSD"
        ]
        if len(btc_positions)!=len(positions):
            raise ValueError("unexpected non-BTC PAPER position during reconciliation")

        btc_qty=sum(
            (_nonnegative_decimal(row.get("qty"),"BTC position quantity")
             for row in btc_positions),
            Decimal("0"),
        )

        state=outcome.state
        if state.stage is Stage.BROKER_TERMINAL_UNRECONCILED:
            expected_qty=state.cumulative_filled_qty
            if btc_qty!=expected_qty:
                raise ValueError("PAPER BTC position does not reconcile to provider cumulative fill")
            if open_orders:
                raise ValueError("terminal PAPER order unexpectedly leaves open orders")
            state=journal.confirm_reconciled(
                client_id,
                at=at,
                provider_cash_verified=True,
                provider_position_verified=True,
                provider_order_verified=True,
            )

    return {
        "kind":KIND,
        "source_kind":SOURCE_KIND,
        "client_order_id":client_id,
        "restart_pending_states_recovered":list(recovered),
        "order_lookup":outcome.as_dict(),
        "paper_account_status":str(account.get("status","")),
        "paper_account_trading_blocked":account.get("trading_blocked"),
        "btc_position_rows":len(btc_positions),
        "btc_position_qty":str(btc_qty),
        "open_order_count":len(open_orders),
        "journal_stage":state.stage.value,
        "journal_reconciled":state.stage is Stage.RECONCILED,
        "network_action":"ALPACA_PAPER_GET_ONLY",
        "order_submission":"DISABLED",
        "blind_retry":"FORBIDDEN",
        "live_trading":"UNAVAILABLE",
        "next_action":(
            "PAPER_POSITION_RECONCILED_CONTINUE_OBSERVATION"
            if state.stage is Stage.RECONCILED
            else "KEEP_BLOCKED_IF_PROVIDER_RESULT_REMAINS_UNRESOLVED"
        ),
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-receipt",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    creds=PaperCredentials.from_environment(os.environ)
    result=reconcile_experimental_paper(
        source_receipt=_read_json(args.source_receipt),
        journal_path=args.journal,
        credentials=creds,
        at=datetime.now(timezone.utc),
    )
    _write_once(args.output,result)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
