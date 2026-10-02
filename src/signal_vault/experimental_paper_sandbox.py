"""Tiny supervised experimental Alpaca PAPER sandbox.

Purpose: get observable PAPER execution faster without claiming strategy
validation. Uses only fixed predeclared BTC hypotheses, fresh closed Alpaca
data, a clean PAPER-account preflight, the shared cross-market risk governor,
deterministic duplicate protection, and exactly one PAPER POST attempt.

LIVE trading is unavailable by construction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .alpaca_paper import PaperAlpacaReadClient
from .cross_market_risk import assess_new_risk
from .market_data import AlpacaAuthenticatedCryptoBars
from .multi_asset_simulation import HYPOTHESES, HypothesisKind, decide_on_prior_closes
from .multimarket_alpaca_paper_executor import MultiMarketAlpacaPaperOnceExecutor
from .multimarket_execution_journal import MultiMarketExecutionJournal, MultiMarketOrderDraft
from .multimarket_paper_router import CRYPTO_PAPER_ACK
from .paper_credentials import PaperCredentials
from .research_universe import ResearchBar
from .strategy import Action

KIND="EXPERIMENTAL_SUPERVISED_BTC_PAPER_SANDBOX"
ALLOWED_STRATEGIES={
    h.name:h for h in HYPOTHESES
    if h.kind in (HypothesisKind.EMA,HypothesisKind.MOMENTUM)
}
NOTIONAL=Decimal("10")


def _closed_hour(now:datetime)->datetime:
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware time required")
    now=now.astimezone(timezone.utc)
    return now.replace(minute=0,second=0,microsecond=0)


def _research_rows(bars,*,captured:datetime):
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


def run_once(
    *,
    strategy_name:str,
    credentials:PaperCredentials,
    acknowledgement:str="",
    execute:bool=False,
    now:datetime,
    bars_factory=AlpacaAuthenticatedCryptoBars,
    reader_factory=PaperAlpacaReadClient,
    executor_factory=MultiMarketAlpacaPaperOnceExecutor,
)->dict[str,object]:
    if strategy_name not in ALLOWED_STRATEGIES:
        raise ValueError("strategy must be one fixed predeclared BTC hypothesis")
    if execute and acknowledgement!=CRYPTO_PAPER_ACK:
        raise PermissionError("exact crypto PAPER acknowledgement required")

    end=_closed_hour(now)
    start=end-timedelta(hours=72)
    bars_client=bars_factory(credentials.key_id,credentials.secret_key)
    bars=bars_client.fetch(start=start,end=end,as_of=now.astimezone(timezone.utc))
    rows=_research_rows(bars,captured=now.astimezone(timezone.utc))
    cfg=ALLOWED_STRATEGIES[strategy_name]
    decision=decide_on_prior_closes(
        rows,
        config=cfg,
        has_position=False,
        next_open_utc=end,
    )
    common={
        "kind":KIND,
        "strategy":strategy_name,
        "evaluated_close_utc":decision.evaluated_close_utc,
        "hypothetical_action":decision.action.value,
        "signal_evidence_sha256":decision.evidence_sha256,
        "experimental_only":True,
        "strategy_validated":False,
        "independent_prospective_gate_passed":False,
        "automatic_paper_activation":"DISABLED",
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
    }
    if decision.action is not Action.BUY:
        return {
            **common,
            "status":"NO_CURRENT_BUY_NO_PAPER_ORDER",
            "paper_post_attempted":False,
            "paper_order_submission":"DISABLED",
        }

    reader=reader_factory(credentials.key_id,credentials.secret_key)
    readiness=reader.readiness()
    if not readiness.ready:
        return {
            **common,
            "status":"BLOCKED_PAPER_ACCOUNT_PREFLIGHT",
            "preflight_reasons":list(readiness.reasons),
            "paper_post_attempted":False,
            "paper_order_submission":"DISABLED",
        }

    seed=f"experimental|{strategy_name}|{decision.evidence_sha256}|{decision.evaluated_close_utc}".encode()
    client_id="svexp-"+hashlib.sha256(seed).hexdigest()[:20]
    if reader.lookup_order(client_id) is not None:
        return {
            **common,
            "status":"BLOCKED_DUPLICATE_CLIENT_ORDER_ALREADY_EXISTS",
            "client_order_id":client_id,
            "paper_post_attempted":False,
            "paper_order_submission":"DISABLED",
        }

    risk=assess_new_risk(
        lane="crypto",
        proposed_max_loss_usd=NOTIONAL,
        exposure_by_lane={},
        open_positions=0,
        marked_equity_usd=Decimal("100"),
        daily_anchor_equity_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        operator_halted=False,
    )
    if risk["risk_admissible"] is not True:
        return {
            **common,
            "status":"BLOCKED_SHARED_RISK_GOVERNOR",
            "risk_assessment":risk,
            "paper_post_attempted":False,
            "paper_order_submission":"DISABLED",
        }

    draft=MultiMarketOrderDraft(
        client_order_id=client_id,
        market_lane="crypto",
        instrument="BTC/USD",
        max_loss_usd=NOTIONAL,
        payload={
            "symbol":"BTC/USD",
            "side":"buy",
            "type":"market",
            "time_in_force":"gtc",
            "client_order_id":client_id,
            "notional":str(NOTIONAL),
        },
    )
    if not execute:
        return {
            **common,
            "status":"READY_FOR_EXPLICIT_SUPERVISED_PAPER_EXECUTION",
            "client_order_id":client_id,
            "notional_usd":str(NOTIONAL),
            "risk_assessment":risk,
            "required_acknowledgement":CRYPTO_PAPER_ACK,
            "paper_post_attempted":False,
            "paper_order_submission":"DISABLED",
        }

    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"experimental-paper.sqlite3"
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
        "status":"EXPERIMENTAL_ONE_SHOT_PAPER_EXECUTOR_INVOKED",
        "client_order_id":client_id,
        "notional_usd":str(NOTIONAL),
        "paper_post_attempted":outcome.paper_post_attempted,
        "paper_order_submission":"ATTEMPT_RECORDED",
        "execution_stage":outcome.stage.value,
        "provider_status":outcome.state.provider_status,
        "blind_retry_forbidden":True,
        "next_action":"RECONCILE_PROVIDER_STATE_BEFORE_ANY_NEW_EXECUTION",
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--strategy",required=True,choices=sorted(ALLOWED_STRATEGIES))
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--acknowledgement",default="")
    args=parser.parse_args(argv)
    creds=PaperCredentials.from_environment(os.environ)
    result=run_once(
        strategy_name=args.strategy,
        credentials=creds,
        acknowledgement=args.acknowledgement,
        execute=args.execute,
        now=datetime.now(timezone.utc),
    )
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
