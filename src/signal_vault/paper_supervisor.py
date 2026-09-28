"""Recovery-only supervisor for paper order lifecycle.

This component NEVER creates/submits an order. It exists so a restarted worker
can safely recover uncertain paper submissions and poll already-known provider
orders. Terminal orders remain blocked until a separate reconciliation audit.
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
    items: tuple[RecoveryItem, ...]
    safe_for_new_submission: bool
    explanation: str


class PaperRecoverySupervisor:
    def __init__(self, *, store: PersistentPaperOrderStore,
                 executor: PaperOnceExecutor, reader: PaperAlpacaReadClient) -> None:
        self.store = store
        self.executor = executor
        self.reader = reader

    def recover_once(self, *, at: datetime) -> RecoveryReport:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware recovery time required")

        # If process died after durable SUBMISSION_PENDING but before recording
        # broker result, the POST may still have reached Alpaca. Convert to UNKNOWN.
        self.store.recover_inflight_pending_after_restart(at=at)
        items: list[RecoveryItem] = []

        for old in self.store.list_states():
            before = old.stage
            if before is Stage.UNKNOWN_RESULT:
                outcome = self.executor.lookup_unknown_once(old.client_order_id, at=at,
                                                            reader=self.reader)
                items.append(RecoveryItem(old.client_order_id, before, outcome.stage,
                                          "lookup_by_client_order_id"))
            elif before in (Stage.BROKER_ACCEPTED, Stage.PARTIALLY_FILLED):
                outcome = self.executor.poll_known_once(old.client_order_id, at=at,
                                                        reader=self.reader)
                items.append(RecoveryItem(old.client_order_id, before, outcome.stage,
                                          "poll_known_order"))
            elif before is Stage.BROKER_TERMINAL_UNRECONCILED:
                # Deliberately do not call finish_reconciliation here. Cash,
                # position and order facts must be audited independently.
                items.append(RecoveryItem(old.client_order_id, before, before,
                                          "await_independent_reconciliation"))
            elif before is Stage.RECONCILED:
                items.append(RecoveryItem(old.client_order_id, before, before, "already_reconciled"))
            else:
                # Any unexpected pre-provider state after startup recovery is unsafe.
                items.append(RecoveryItem(old.client_order_id, before, before, "halt_unexpected_state"))

        safe = not self.store.has_unresolved_provider_order()
        return RecoveryReport(tuple(items), safe,
                              "no unresolved paper provider order" if safe else
                              "paper execution remains blocked pending provider resolution/reconciliation")
