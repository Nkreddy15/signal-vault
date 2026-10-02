"""Read-only recovery/reconciliation for one experimental BTC PAPER sandbox run.

Consumes the archived Phase 154 receipt+journal, never submits/cancels/replaces
orders, and performs only authoritative Alpaca PAPER GETs.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .experimental_paper_sandbox import KIND as SOURCE_KIND
from .multimarket_alpaca_reconciliation import reconcile_alpaca_paper_order_lookup
from .multimarket_execution_journal import MultiMarketExecutionJournal
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

    btc_positions=[
        p for p in positions
        if str(p.get("symbol","")).replace("/","")=="BTCUSD"
    ]
    return {
        "kind":KIND,
        "source_kind":SOURCE_KIND,
        "client_order_id":client_id,
        "restart_pending_states_recovered":list(recovered),
        "order_lookup":outcome.as_dict(),
        "paper_account_status":str(account.get("status","")),
        "paper_account_trading_blocked":account.get("trading_blocked"),
        "btc_position_rows":len(btc_positions),
        "open_order_count":len(open_orders),
        "network_action":"ALPACA_PAPER_GET_ONLY",
        "order_submission":"DISABLED",
        "blind_retry":"FORBIDDEN",
        "live_trading":"UNAVAILABLE",
        "next_action":(
            "FULL_ACCOUNT_RECONCILIATION_REQUIRED_BEFORE_ANOTHER_EXECUTION"
            if outcome.full_account_reconciliation_still_required
            else
            "KEEP_BLOCKED_IF_PROVIDER_RESULT_REMAINS_UNRESOLVED"
            if outcome.new_execution_blocked
            else
            "NO_ADDITIONAL_EXECUTION_AUTHORITY_GRANTED"
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
