"""Explicit local crypto PAPER pilot command.

Default mode performs a fresh Alpaca PAPER GET-only preflight and persists it.
It cannot submit unless --execute is supplied together with the exact
market-specific PAPER acknowledgement. No LIVE host exists in this module.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .crypto_paper_executor_draft import KIND as PREPARED_KIND
from .crypto_paper_executor_once import execute_prepared_crypto_paper_once
from .crypto_paper_pilot_dry_run import KIND as DRY_RUN_KIND
from .crypto_paper_provider_preflight import capture_crypto_paper_provider_preflight
from .multimarket_execution_journal import MultiMarketExecutionJournal
from .multimarket_paper_router import CRYPTO_PAPER_ACK
from .paper_credentials import PaperCredentials


KIND="CRYPTO_PAPER_PILOT_LOCAL_COMMAND"
MAX_RECEIPT_BYTES=2_000_000


def _load_receipt(path:Path)->dict[str,object]:
    item=Path(path).expanduser()
    if (
        item.is_symlink()
        or not item.is_file()
        or not 0<item.stat().st_size<=MAX_RECEIPT_BYTES
    ):
        raise ValueError("pilot receipt must be bounded regular non-symlink file")
    value=json.loads(item.read_text())
    if not isinstance(value,dict):
        raise ValueError("pilot receipt must be JSON object")
    return value


def _existing_journal_path(path:Path)->Path:
    item=Path(path).expanduser()
    if item.is_symlink() or not item.is_file():
        raise ValueError("existing execution journal regular file required")
    return item


def _validate_handoff_receipts(
    prepared:Mapping[str,object],
    dry_run:Mapping[str,object],
)->None:
    if (
        prepared.get("kind")!=PREPARED_KIND
        or prepared.get("status")!="DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED"
        or prepared.get("market_lane")!="crypto"
        or prepared.get("instrument")!="BTC/USD"
        or prepared.get("provider_post_attempted") is not False
        or prepared.get("paper_executor_invoked") is not False
        or prepared.get("paper_order_submission")!="DISABLED"
        or prepared.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible prepared crypto PAPER receipt required")
    if (
        dry_run.get("kind")!=DRY_RUN_KIND
        or dry_run.get("status")!="READY_FOR_SEPARATE_PAPER_EXECUTOR_INVOCATION_REVIEW"
        or dry_run.get("eligible_for_separate_paper_executor_invocation_review") is not True
        or dry_run.get("provider_post_attempted") is not False
        or dry_run.get("paper_executor_invoked") is not False
        or dry_run.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible crypto PAPER dry-run receipt required")
    preview=dry_run.get("paper_preview")
    if not isinstance(preview,Mapping):
        raise ValueError("crypto PAPER preview required")
    if preview.get("decision_id")!=prepared.get("decision_id"):
        raise ValueError("prepared and dry-run decision mismatch")


def run_crypto_paper_pilot(
    *,
    prepared:Mapping[str,object],
    dry_run:Mapping[str,object],
    journal:MultiMarketExecutionJournal,
    credentials:PaperCredentials,
    execute:bool=False,
    acknowledgement:str="",
    at:datetime,
    reader_factory=PaperAlpacaReadClient,
    execution_transport=None,
)->dict[str,object]:
    if not isinstance(at,datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware pilot timestamp required")
    _validate_handoff_receipts(prepared,dry_run)
    decision_id=prepared.get("decision_id")
    if not isinstance(decision_id,str) or not decision_id:
        raise ValueError("prepared decision id required")
    if execute and acknowledgement!=CRYPTO_PAPER_ACK:
        raise PermissionError(
            "exact crypto PAPER acknowledgement required with execute mode"
        )

    reader=reader_factory(credentials.key_id,credentials.secret_key)
    try:
        journal.get_provider_preflight_record(decision_id)
        refresh=True
    except KeyError:
        refresh=False

    preflight=capture_crypto_paper_provider_preflight(
        prepared,
        journal=journal,
        reader=reader,
        at=at,
        refresh_existing=refresh,
    )
    common={
        "kind":KIND,
        "market_lane":"crypto",
        "instrument":"BTC/USD",
        "provider_preflight_status":preflight["status"],
        "provider_preflight_refreshed":refresh,
        "credential_values_persisted":False,
        "live_host_available":False,
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
    }
    if not execute:
        return {
            **common,
            "status":"PREFLIGHT_ONLY_COMPLETE_NO_ORDER_SUBMISSION",
            "paper_post_attempted":False,
            "paper_executor_invoked":False,
            "paper_order_submission":"DISABLED",
            "next_action":
                "EXPLICIT_EXECUTE_FLAG_AND_EXACT_CRYPTO_PAPER_ACK_REQUIRED_FOR_ONE_SHOT_POST",
        }

    kwargs={}
    if execution_transport is not None:
        kwargs["transport"]=execution_transport
    result=execute_prepared_crypto_paper_once(
        prepared,
        dry_run,
        journal=journal,
        paper_key=credentials.key_id,
        paper_secret=credentials.secret_key,
        acknowledgement=acknowledgement,
        at=at,
        **kwargs,
    )
    return {
        **common,
        "status":"ONE_SHOT_PAPER_EXECUTOR_INVOKED",
        "paper_post_attempted":result["paper_post_attempted"],
        "paper_executor_invoked":True,
        "execution_stage":result["stage"],
        "provider_status":result["provider_status"],
        "blind_retry_forbidden":True,
        "next_action":result["next_action"],
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description=(
            "Crypto PAPER pilot: GET-only preflight by default; one-shot PAPER POST "
            "only with --execute and exact acknowledgement."
        )
    )
    parser.add_argument("--journal",required=True)
    parser.add_argument("--prepared",required=True)
    parser.add_argument("--dry-run",required=True)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--acknowledgement",default="")
    args=parser.parse_args(argv)

    prepared=_load_receipt(Path(args.prepared))
    dry_run=_load_receipt(Path(args.dry_run))
    credentials=PaperCredentials.from_environment(os.environ)
    journal_path=_existing_journal_path(Path(args.journal))
    with MultiMarketExecutionJournal(journal_path) as journal:
        result=run_crypto_paper_pilot(
            prepared=prepared,
            dry_run=dry_run,
            journal=journal,
            credentials=credentials,
            execute=args.execute,
            acknowledgement=args.acknowledgement,
            at=datetime.now(timezone.utc),
        )
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
