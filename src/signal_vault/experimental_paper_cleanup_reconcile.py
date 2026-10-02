"""Read-only reconciliation for one experimental BTC PAPER cleanup SELL."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .experimental_paper_cleanup import KIND as SOURCE_KIND
from .multimarket_alpaca_reconciliation import reconcile_alpaca_paper_order_lookup
from .multimarket_execution_journal import MultiMarketExecutionJournal
from .paper_credentials import PaperCredentials
from .paper_order_state import Stage

KIND="EXPERIMENTAL_BTC_PAPER_CLEANUP_READ_ONLY_RECONCILIATION"
MAX_BYTES=4_000_000


def _read_json(path:Path)->dict[str,object]:
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_BYTES:
        raise ValueError("bounded regular cleanup receipt required")
    value=json.loads(p.read_text())
    if not isinstance(value,dict):
        raise ValueError("cleanup receipt must be JSON object")
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


def _positive(raw:object,name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError("invalid "+name) from exc
    if not value.is_finite() or value<=0:
        raise ValueError("invalid "+name)
    return value


def reconcile_cleanup(
    *,
    source_receipt:Mapping[str,object],
    journal_path:Path,
    credentials:PaperCredentials,
    at:datetime,
    reader_factory=PaperAlpacaReadClient,
)->dict[str,object]:
    if (
        source_receipt.get("kind")!=SOURCE_KIND
        or source_receipt.get("cleanup_only") is not True
        or source_receipt.get("side")!="sell"
        or source_receipt.get("instrument")!="BTC/USD"
        or source_receipt.get("paper_post_attempted") is not True
        or source_receipt.get("paper_order_submission")!="ATTEMPT_RECORDED"
        or source_receipt.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("executed cleanup receipt required")
    client_id=source_receipt.get("client_order_id")
    if not isinstance(client_id,str) or not client_id.startswith("svclean-"):
        raise ValueError("cleanup client id required")
    expected_qty=_positive(source_receipt.get("fresh_qty"),"cleanup quantity")

    p=Path(journal_path)
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_BYTES:
        raise ValueError("bounded regular cleanup journal required")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware reconciliation time required")

    reader=reader_factory(credentials.key_id,credentials.secret_key)
    with MultiMarketExecutionJournal(p) as journal:
        recovered=journal.recover_pending_after_restart(at=at)
        draft=journal.get_approved_draft(client_id)
        if (
            draft.market_lane!="crypto"
            or draft.instrument!="BTC/USD"
            or draft.payload.get("side")!="sell"
            or draft.payload.get("qty")!=format(expected_qty,"f")
        ):
            raise ValueError("cleanup journal draft mismatch")

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

        btc_rows=[
            row for row in positions
            if str(row.get("symbol","")).replace("/","")=="BTCUSD"
        ]
        if len(btc_rows)!=len(positions):
            raise ValueError("unexpected non-BTC PAPER position during cleanup reconciliation")
        btc_qty=sum(
            (_positive(row.get("qty"),"remaining BTC quantity") for row in btc_rows),
            Decimal("0"),
        ) if btc_rows else Decimal("0")

        state=outcome.state
        terminal=state.stage is Stage.BROKER_TERMINAL_UNRECONCILED
        provider_status=state.provider_status
        expected_remaining=None
        if terminal:
            expected_remaining=expected_qty-state.cumulative_filled_qty
            if expected_remaining<0:
                raise ValueError("provider fill exceeds cleanup quantity")
            if btc_qty!=expected_remaining:
                raise ValueError("provider BTC position does not reconcile to cleanup fill")
            if open_orders:
                raise ValueError("terminal cleanup unexpectedly leaves open PAPER orders")
            try:
                equity=Decimal(str(account.get("equity")))
            except Exception as exc:
                raise ValueError("provider account surface missing valid equity") from exc
            if not equity.is_finite() or equity<0:
                raise ValueError("provider account equity invalid")
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
        "provider_status":provider_status,
        "cleanup_expected_qty":str(expected_qty),
        "provider_cumulative_filled_qty":str(outcome.state.cumulative_filled_qty),
        "remaining_btc_qty":str(btc_qty),
        "cleanup_fully_flattened":btc_qty==0,
        "journal_stage":state.stage.value,
        "journal_reconciled":state.stage is Stage.RECONCILED,
        "open_order_count":len(open_orders),
        "network_action":"ALPACA_PAPER_GET_ONLY",
        "order_submission":"DISABLED",
        "blind_retry":"FORBIDDEN",
        "live_trading":"UNAVAILABLE",
        "next_action":(
            "RERUN_EXPERIMENTAL_PAPER_READINESS"
            if state.stage is Stage.RECONCILED and btc_qty==0
            else "KEEP_NEW_EXECUTION_BLOCKED"
        ),
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-receipt",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    creds=PaperCredentials.from_environment(os.environ)
    result=reconcile_cleanup(
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
