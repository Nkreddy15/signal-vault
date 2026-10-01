"""Explicit supervised historical-bootstrap crypto PAPER pilot.

Default mode performs a fresh Alpaca PAPER GET-only preflight and persists it.
Exactly one PAPER POST is possible only with:
- a Phase 136 durable bootstrap draft,
- the matching Phase 134 supervised bootstrap preview,
- separate Alpaca PAPER credentials,
- --execute plus the exact crypto PAPER acknowledgement.

The independent 168-hour forward gate remains false. LIVE trading is absent.
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
from .crypto_paper_provider_preflight import capture_crypto_paper_provider_preflight
from .historical_bootstrap_paper_draft import SOURCE_KIND
from .multimarket_alpaca_paper_executor import (
    MultiMarketAlpacaPaperOnceExecutor,
    _post_alpaca_paper,
)
from .multimarket_execution_journal import MultiMarketExecutionJournal
from .multimarket_paper_router import CRYPTO_PAPER_ACK
from .paper_credentials import PaperCredentials


KIND="CRYPTO_HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER_LOCAL_COMMAND"
MAX_RECEIPT_BYTES=2_000_000


def _load_receipt(path:Path)->dict[str,object]:
    item=Path(path).expanduser()
    if item.is_symlink() or not item.is_file() or not 0<item.stat().st_size<=MAX_RECEIPT_BYTES:
        raise ValueError("bounded regular receipt file required")
    value=json.loads(item.read_text())
    if not isinstance(value,dict):
        raise ValueError("receipt must be JSON object")
    return value


def _existing_journal_path(path:Path)->Path:
    item=Path(path).expanduser()
    if item.is_symlink() or not item.is_file():
        raise ValueError("existing execution journal regular file required")
    return item


def _validate(
    prepared:Mapping[str,object],
    bootstrap_preview:Mapping[str,object],
)->tuple[Mapping[str,object],Mapping[str,object]]:
    if (
        not isinstance(prepared,Mapping)
        or prepared.get("kind")!=PREPARED_KIND
        or prepared.get("status")!="DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED"
        or prepared.get("source_mode")!="HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER"
        or prepared.get("independent_prospective_gate_passed") is not False
        or prepared.get("paper_period_is_forward_validation") is not True
        or prepared.get("market_lane")!="crypto"
        or prepared.get("instrument")!="BTC/USD"
        or prepared.get("provider_post_attempted") is not False
        or prepared.get("paper_executor_invoked") is not False
        or prepared.get("paper_order_submission")!="DISABLED"
        or prepared.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible durable historical-bootstrap PAPER draft required")
    if (
        not isinstance(bootstrap_preview,Mapping)
        or bootstrap_preview.get("kind")!=SOURCE_KIND
        or bootstrap_preview.get("status")!="READY_FOR_SUPERVISED_PAPER_DRAFT_REVIEW"
        or bootstrap_preview.get("independent_prospective_gate_passed") is not False
        or bootstrap_preview.get("paper_period_is_forward_validation") is not True
        or bootstrap_preview.get("live_promotion_permitted") is not False
        or bootstrap_preview.get("automatic_paper_activation")!="DISABLED"
        or bootstrap_preview.get("provider_post_attempted") is not False
        or bootstrap_preview.get("paper_order_submission")!="DISABLED"
        or bootstrap_preview.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("eligible supervised bootstrap PAPER preview required")
    preview=bootstrap_preview.get("paper_preview")
    if not isinstance(preview,Mapping):
        raise ValueError("bootstrap PAPER preview required")
    risk=preview.get("risk_assessment")
    route=preview.get("route")
    if (
        preview.get("decision_id")!=prepared.get("decision_id")
        or preview.get("market_lane")!="crypto"
        or preview.get("instrument")!="BTC/USD"
        or preview.get("forward_gate_passed") is not False
        or preview.get("provider_post_attempted") is not False
        or preview.get("paper_order_submission")!="DISABLED"
        or preview.get("live_trading")!="UNAVAILABLE"
        or not isinstance(risk,Mapping)
        or risk.get("kind")!="CROSS_MARKET_RISK_ASSESSMENT_NOT_ORDER_AUTHORIZATION"
        or risk.get("lane")!="crypto"
        or risk.get("risk_admissible") is not True
        or risk.get("assessment_is_not_trading_authorization") is not True
        or risk.get("automatic_order_submission")!="DISABLED"
        or not isinstance(route,Mapping)
        or route.get("provider")!="alpaca"
        or route.get("environment")!="paper"
        or route.get("market_lane")!="crypto"
        or route.get("required_acknowledgement")!=CRYPTO_PAPER_ACK
        or route.get("live_trading_available") is not False
    ):
        raise ValueError("bootstrap PAPER route/risk mismatch")
    return risk,route


def run_bootstrap_crypto_paper_pilot(
    *,
    prepared:Mapping[str,object],
    bootstrap_preview:Mapping[str,object],
    journal:MultiMarketExecutionJournal,
    credentials:PaperCredentials,
    execute:bool=False,
    acknowledgement:str="",
    at:datetime,
    reader_factory=PaperAlpacaReadClient,
    execution_transport=_post_alpaca_paper,
)->dict[str,object]:
    if not isinstance(at,datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware pilot timestamp required")
    risk,route=_validate(prepared,bootstrap_preview)
    decision_id=prepared.get("decision_id")
    if not isinstance(decision_id,str) or not decision_id:
        raise ValueError("prepared decision id required")
    if execute and acknowledgement!=CRYPTO_PAPER_ACK:
        raise PermissionError("exact crypto PAPER acknowledgement required with execute mode")

    draft=journal.get_approved_draft(decision_id)
    if (
        draft.market_lane!="crypto"
        or draft.instrument!="BTC/USD"
        or draft.payload_sha256!=prepared.get("payload_sha256")
        or dict(draft.payload)!=route.get("payload")
        or str(draft.max_loss_usd)!=str(prepared.get("max_loss_usd"))
        or str(risk.get("proposed_max_loss_usd"))!=str(draft.max_loss_usd)
    ):
        raise ValueError("bootstrap preview and durable draft do not match")

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
        "source_mode":"HISTORICAL_BOOTSTRAP_SUPERVISED_PAPER",
        "independent_prospective_gate_passed":False,
        "paper_period_is_forward_validation":True,
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

    executor=MultiMarketAlpacaPaperOnceExecutor(
        paper_key=credentials.key_id,
        paper_secret=credentials.secret_key,
        journal=journal,
        transport=execution_transport,
    )
    outcome=executor.submit_once(
        draft,
        risk_assessment=risk,
        acknowledgement=acknowledgement,
        at=at,
    )
    return {
        **common,
        "status":"ONE_SHOT_SUPERVISED_BOOTSTRAP_PAPER_EXECUTOR_INVOKED",
        "paper_post_attempted":outcome.paper_post_attempted,
        "paper_executor_invoked":True,
        "paper_order_submission":"ATTEMPT_RECORDED",
        "execution_stage":outcome.stage.value,
        "provider_status":outcome.state.provider_status,
        "blind_retry_forbidden":True,
        "next_action":(
            "RECONCILE_PROVIDER_STATE_BEFORE_ANY_NEW_EXECUTION"
            if outcome.state.blocks_new_execution else
            "AUDIT_TERMINAL_PAPER_ORDER_BEFORE_ANY_NEW_EXECUTION"
        ),
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description=(
            "Historical-bootstrap crypto PAPER pilot: GET-only preflight by default; "
            "one-shot PAPER POST only with --execute and exact acknowledgement."
        )
    )
    parser.add_argument("--journal",required=True)
    parser.add_argument("--prepared",required=True)
    parser.add_argument("--bootstrap-preview",required=True)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--acknowledgement",default="")
    args=parser.parse_args(argv)
    prepared=_load_receipt(Path(args.prepared))
    preview=_load_receipt(Path(args.bootstrap_preview))
    credentials=PaperCredentials.from_environment(os.environ)
    journal_path=_existing_journal_path(Path(args.journal))
    with MultiMarketExecutionJournal(journal_path) as journal:
        result=run_bootstrap_crypto_paper_pilot(
            prepared=prepared,
            bootstrap_preview=preview,
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
