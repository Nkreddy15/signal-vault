"""Read-only PAPER provider recovery; NEVER makes new orders or transfers.

Terminal-order reconciliation uses the independent before/after source evidence
checks inside PaperOnceExecutor, not caller-provided success booleans. The
recovery loop deliberately takes only one transition per order per invocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .alpaca_paper import PaperAlpacaReadClient
from .paper_executor import PaperOnceExecutor
from .paper_order_state import Stage
from .paper_store import PersistentPaperOrderStore


@dataclass(frozen=True)
class RecoveryItem:
    client_order_id: str
    before: Stage
    after: Stage
    action: str


@dataclass(frozen=True)
class RecoveryReport:
    items: tuple[RecoveryItem,...]
    safe_for_new_submission: bool
    explanation: str


class PaperRecoverySupervisor:
    def __init__(self, *, store:PersistentPaperOrderStore,
                 executor:PaperOnceExecutor,reader:PaperAlpacaReadClient) -> None:
        executor._require_same_paper_reader(reader)
        self.store=store
        self.executor=executor
        self.reader=reader

    def recover_once(self, *, at:datetime) -> RecoveryReport:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('aware recovery time required')
        self.store.recover_inflight_pending_after_restart(at=at)
        results=[]
        for previous in self.store.list_states():
            before=previous.stage
            action='no_operation'
            after=before
            try:
                if before is Stage.UNKNOWN_RESULT:
                    outcome=self.executor.lookup_unknown_once(previous.client_order_id,
                                                              at=at,reader=self.reader)
                    action='source_lookup_by_client_id'
                    after=outcome.stage
                elif before in (Stage.BROKER_ACCEPTED,Stage.PARTIALLY_FILLED):
                    outcome=self.executor.poll_known_once(previous.client_order_id,
                                                          at=at,reader=self.reader)
                    action='source_poll_known_order'
                    after=outcome.stage
                elif before is Stage.BROKER_TERMINAL_UNRECONCILED:
                    outcome=self.executor.reconcile_terminal_once(previous.client_order_id,
                                                                   at=at,reader=self.reader)
                    action='three_way_source_evidence_verified'
                    after=outcome.stage
                elif before is Stage.RECONCILED:
                    action='already_reconciled'
                else:
                    action='unexpected_stage_keep_halted'
            except Exception as exc:
                # A paper provider API outage or incompatible response is NOT
                # evidence of absence. Preserve reservation and require review;
                # never print API error bodies (which can contain credentials).
                action='SOURCE_FAILED_'+type(exc).__name__
                after=self.store.get(previous.client_order_id).stage
            results.append(RecoveryItem(previous.client_order_id,before,after,action))
        safe=(not self.store.has_unresolved_provider_order() and
              not self.store.is_operator_halted())
        return RecoveryReport(tuple(results),safe,
            'all paper source evidence reconciled and no manual HALT' if safe else
            'submissions blocked pending source resolution or owner HALT')
