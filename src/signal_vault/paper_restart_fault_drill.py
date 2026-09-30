"""OFFLINE persistent paper-order restart / partial-fill fault drill.

This is engineering-only and never imports the production paper HTTP POST
transport. It uses a temporary SQLite file, fake callbacks and fake literals to
prove restart semantics survive process/store reopen:
- SUBMISSION_PENDING on crash becomes UNKNOWN_RESULT before any retry;
- exact client-ID GET can recover partial fill without a second POST;
- partial-fill cumulative quantity may increase but never regress;
- accepted/new status may not regress from a partial fill;
- a partial-then-canceled terminal order stays UNRECONCILED until independent
  account/fill/fee/position audit; this drill deliberately does NOT release it;
- a terminal broker snapshot cannot later rewrite broker ID/status/qty/price.

No provider network, account access, credentials, broker order or live mode.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .alpaca_paper import PaperAlpacaReadClient, PaperOrderDraft
from .domain import PortfolioSnapshot, Side, TradeIntent
from .paper_executor import PaperOnceExecutor
from .paper_order_state import BrokerObservation, Stage
from .paper_store import PersistentPaperOrderStore
from .paper_supervisor import PaperRecoverySupervisor

AT=datetime(2026,9,30,5,0,tzinfo=timezone.utc)
FAKE_KEY="offline-key"
FAKE_SECRET="offline-secret"


def _require(value:bool,label:str)->None:
    if not value:
        raise RuntimeError("fault drill failed "+label)


def _draft(store:PersistentPaperOrderStore)->PaperOrderDraft:
    intent=TradeIntent(
        "crypto","alpaca","BTC/USD",Side.BUY,Decimal("15"),
        "restart-partial-1","offline-fault-signal",AT)
    portfolio=PortfolioSnapshot(
        Decimal("100"),Decimal("100"),Decimal("100"),Decimal("100"))
    return store.journal.record(
        intent,portfolio,checked_at=AT,reference_price=Decimal("65000"))


def run_persistent_restart_partial_fault_drill()->dict[str,object]:
    fake_post_attempts=0
    fake_get_attempts=0
    with tempfile.TemporaryDirectory(prefix="signal-vault-paper-fault-") as tmp:
        db=Path(tmp)/"paper.sqlite3"

        # Simulate crash AFTER durable pending but before transport result.
        with PersistentPaperOrderStore(db) as first:
            draft=_draft(first)
            first.begin_submission(draft,at=AT)
            _require(first.get(draft.client_order_id).stage is Stage.SUBMISSION_PENDING,
                     "durable pending before restart")

        # Reopen same persistent DB. Supervisor must make pending UNKNOWN before
        # any provider recovery and must use GET-only exact-client-ID lookup.
        post_calls=[]
        get_calls=[]
        with PersistentPaperOrderStore(db) as restarted:
            executor=PaperOnceExecutor(
                paper_key=FAKE_KEY,paper_secret=FAKE_SECRET,store=restarted,
                transport=lambda *_:(post_calls.append("POST") or {}))
            def first_lookup(path,*_):
                nonlocal fake_get_attempts
                get_calls.append(path);fake_get_attempts+=1
                _require(path.startswith("/v2/orders:by_client_order_id"),
                         "recovery only exact client-id lookup")
                return {
                    "id":"broker-1",
                    "client_order_id":draft.client_order_id,
                    "status":"partially_filled",
                    "filled_qty":"0.00010",
                    "filled_avg_price":"65000",
                }
            reader=PaperAlpacaReadClient(
                FAKE_KEY,FAKE_SECRET,transport=first_lookup)
            report=PaperRecoverySupervisor(
                store=restarted,executor=executor,reader=reader).recover_once(at=AT)
            _require(not report.safe_for_new_submission,"partial remains blocking")
            state=restarted.get(draft.client_order_id)
            _require(state.stage is Stage.PARTIALLY_FILLED,"restart recovered partial")
            _require(state.cumulative_filled_qty==Decimal("0.00010"),"partial qty")
            _require(not post_calls,"restart recovery made no POST")

            # Larger cumulative partial is valid via known-order GET poll.
            reader2=PaperAlpacaReadClient(
                FAKE_KEY,FAKE_SECRET,transport=lambda *_:{
                    "id":"broker-1","client_order_id":draft.client_order_id,
                    "status":"partially_filled","filled_qty":"0.00015",
                    "filled_avg_price":"65100"})
            fake_get_attempts+=1
            state2=executor.poll_known_once(
                draft.client_order_id,at=AT,reader=reader2).state
            _require(state2.stage is Stage.PARTIALLY_FILLED,"larger partial valid")
            _require(state2.cumulative_filled_qty==Decimal("0.00015"),"partial advanced")

            # Regression attempts are rejected without altering durable state.
            try:
                restarted.observe_provider(BrokerObservation(
                    draft.client_order_id,"broker-1","partially_filled",
                    Decimal("0.00014"),Decimal("65100")),at=AT)
            except ValueError:
                pass
            else:
                raise RuntimeError("fault drill accepted regressing cumulative fill")
            _require(restarted.get(draft.client_order_id)==state2,
                     "regression left durable state unchanged")
            try:
                restarted.observe_provider(BrokerObservation(
                    draft.client_order_id,"broker-1","accepted",
                    Decimal("0"),None),at=AT)
            except ValueError:
                pass
            else:
                raise RuntimeError("fault drill accepted status regression")
            _require(restarted.get(draft.client_order_id)==state2,
                     "status regression left state unchanged")

            # Partial then canceled is terminal but MUST remain unreconciled.
            terminal=restarted.observe_provider(BrokerObservation(
                draft.client_order_id,"broker-1","canceled",
                Decimal("0.00015"),Decimal("65100")),at=AT)
            _require(terminal.stage is Stage.BROKER_TERMINAL_UNRECONCILED,
                     "partial cancel terminal unreconciled")
            _require(restarted.has_unresolved_provider_order(),
                     "terminal unreconciled blocks next execution")
            _require(restarted.journal.total_reserved_usd()==Decimal("15"),
                     "reservation retained pending reconciliation")

            # Exact terminal repeat is idempotent; any rewrite is hard failure.
            same=restarted.observe_provider(BrokerObservation(
                draft.client_order_id,"broker-1","canceled",
                Decimal("0.00015"),Decimal("65100")),at=AT)
            _require(same==terminal,"identical terminal repeat")
            for bad in (
                BrokerObservation(draft.client_order_id,"broker-2","canceled",
                                  Decimal("0.00015"),Decimal("65100")),
                BrokerObservation(draft.client_order_id,"broker-1","filled",
                                  Decimal("0.00015"),Decimal("65100")),
                BrokerObservation(draft.client_order_id,"broker-1","canceled",
                                  Decimal("0.00016"),Decimal("65100")),
                BrokerObservation(draft.client_order_id,"broker-1","canceled",
                                  Decimal("0.00015"),Decimal("65200")),
            ):
                try:
                    restarted.observe_provider(bad,at=AT)
                except ValueError:
                    pass
                else:
                    raise RuntimeError("fault drill accepted terminal rewrite")
            _require(restarted.get(draft.client_order_id)==terminal,
                     "terminal rewrite attempts did not mutate state")
            fake_post_attempts+=len(post_calls)

        # Reopen a second time: terminal stays blocked; supervisor must NOT POST.
        with PersistentPaperOrderStore(db) as final:
            post_calls=[]
            executor=PaperOnceExecutor(
                paper_key=FAKE_KEY,paper_secret=FAKE_SECRET,store=final,
                transport=lambda *_:(post_calls.append("POST") or {}))
            reader=PaperAlpacaReadClient(
                FAKE_KEY,FAKE_SECRET,transport=lambda *_:{"found":False})
            report=PaperRecoverySupervisor(
                store=final,executor=executor,reader=reader).recover_once(at=AT)
            _require(not report.safe_for_new_submission,"terminal still blocks after second restart")
            _require(report.items[0].action=="await_independent_reconciliation",
                     "restart waits for independent reconciliation")
            _require(not post_calls,"second restart no POST")
            _require(final.journal.total_reserved_usd()==Decimal("15"),
                     "reservation still retained")
            fake_post_attempts+=len(post_calls)

    return {
        "kind":"OFFLINE_PERSISTENT_PAPER_RESTART_PARTIAL_FILL_FAULT_DRILL",
        "result":"PASS_SYNTHETIC_PERSISTENT_FAILURE_SEMANTICS_ONLY",
        "durable_restart_count":2,
        "fake_GET_attempts":fake_get_attempts,
        "fake_POST_attempts":fake_post_attempts,
        "terminal_reconciliation_performed":False,
        "reservation_retained_usd":"15",
        "new_execution_unblocked":False,
        "network_requests":"NONE",
        "provider_account_access":"NONE",
        "credentials":"FAKE_LITERALS_ONLY",
        "actual_paper_order_posts":"NONE",
        "automatic_paper_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "warning":"Synthetic fault drill only; NOT an Alpaca order or authorization.",
    }


def main()->int:
    try:
        result=run_persistent_restart_partial_fault_drill()
        code=0
    except Exception as exc:
        result={
            "kind":"OFFLINE_PERSISTENT_PAPER_RESTART_PARTIAL_FILL_FAULT_DRILL",
            "result":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "actual_paper_order_posts":"NONE",
            "automatic_paper_trading":"DISABLED",
            "live_trading":"UNAVAILABLE",
        }
        code=2
    print(json.dumps(result,indent=2,sort_keys=True))
    return code


if __name__=="__main__":
    raise SystemExit(main())
