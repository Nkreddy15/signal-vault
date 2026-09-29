"""Fully OFFLINE synthetic paper-order state-machine acceptance drill.

This command never reads local journal/Keychain/network, never calls Alpaca,
and never opens the real paper transport. Uses separate in-memory SQLite
stores, mock credentials, and explicitly injected fake provider callbacks.
All status is SYNTHETIC, never evidence of an actual broker paper order.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from .alpaca_paper import PaperAlpacaReadClient, PaperOrderDraft
from .domain import PortfolioSnapshot, Side, TradeIntent
from .paper_executor import PaperOnceExecutor
from .paper_order_state import Stage
from .paper_store import PersistentPaperOrderStore

_AT = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
_PRICE = Decimal("65000")
_FAKE_KEY = "synthetic-paper-key"
_FAKE_SECRET = "synthetic-paper-secret"


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeError("synthetic drill did not satisfy " + code)


def _draft(store: PersistentPaperOrderStore, suffix: str) -> PaperOrderDraft:
    intent = TradeIntent(
        "crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
        "sim-" + suffix, "synthetic-evidence-" + suffix, _AT,
    )
    snapshot = PortfolioSnapshot(
        Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"),
    )
    return store.journal.record(intent, snapshot, checked_at=_AT, reference_price=_PRICE)


def _accepted(client_id: str) -> dict[str, object]:
    return {
        "id": "synthetic-provider-001",
        "client_order_id": client_id,
        "status": "accepted",
        "filled_qty": "0",
        "filled_avg_price": None,
    }


def run_offline_execution_drill() -> dict[str, object]:
    """Five isolated failure/success scenarios using FAKE callbacks only."""
    scenarios: dict[str, str] = {}
    fake_post_attempts = 0

    # 1. Persist SUBMISSION_PENDING before fake POST. Accepted is NOT a fill.
    with PersistentPaperOrderStore(":memory:") as store:
        draft = _draft(store, "accepted")
        seen: list[str] = []

        def accepted_transport(payload, key, secret):
            seen.append("FAKE_ONLY")
            _require((key, secret) == (_FAKE_KEY, _FAKE_SECRET), "mock key boundary")
            _require(store.get(draft.client_order_id).stage is Stage.SUBMISSION_PENDING,
                     "durable pending before transport")
            _require(payload["client_order_id"] == draft.client_order_id, "client ID")
            return _accepted(draft.client_order_id)

        executor = PaperOnceExecutor(
            paper_key=_FAKE_KEY, paper_secret=_FAKE_SECRET,
            store=store, transport=accepted_transport,
        )
        outcome = executor.submit_once(draft, at=_AT)
        _require(outcome.stage is Stage.BROKER_ACCEPTED, "accepted is not a fill")
        _require(store.has_unresolved_provider_order(), "accepted blocks a second order")
        _require(store.journal.total_reserved_usd() == Decimal("15"), "reservation retained")
        _require(len(seen) == 1, "one fake attempt")
        fake_post_attempts += len(seen)
        try:
            executor.submit_once(draft, at=_AT)
        except ValueError:
            pass
        else:
            raise RuntimeError("synthetic duplicate not rejected")
        _require(len(seen) == 1, "duplicate did not trigger mock transport")
        scenarios["accepted_not_assumed_filled_and_duplicate_refused"] = "PASS"

    # 2. Timeout => UNKNOWN_RESULT, preserve reserve and never blindly retry.
    with PersistentPaperOrderStore(":memory:") as store:
        draft = _draft(store, "timeout")
        calls: list[str] = []

        def timeout_transport(payload, key, secret):
            calls.append("FAKE_ONLY")
            _require(store.get(draft.client_order_id).stage is Stage.SUBMISSION_PENDING,
                     "timeout had pending durable state")
            raise TimeoutError("injected fake timeout")

        executor = PaperOnceExecutor(
            paper_key=_FAKE_KEY, paper_secret=_FAKE_SECRET,
            store=store, transport=timeout_transport,
        )
        outcome = executor.submit_once(draft, at=_AT)
        _require(outcome.stage is Stage.UNKNOWN_RESULT, "timeout becomes UNKNOWN")
        _require(store.journal.total_reserved_usd() == Decimal("15"),
                 "unknown retains reserved cash")
        _require(store.has_unresolved_provider_order(), "unknown blocks execution")
        _require(len(calls) == 1, "timeout only one fake attempt")
        fake_post_attempts += len(calls)
        unavailable = PaperAlpacaReadClient(
            _FAKE_KEY, _FAKE_SECRET, transport=lambda *_: {"found": False},
        )
        lookup = executor.lookup_unknown_once(draft.client_order_id, at=_AT, reader=unavailable)
        _require(lookup.stage is Stage.UNKNOWN_RESULT, "missing lookup remains unknown")
        try:
            executor.submit_once(draft, at=_AT)
        except ValueError:
            pass
        else:
            raise RuntimeError("synthetic timeout duplicate not blocked")
        _require(len(calls) == 1, "no blind fake POST retry")
        recovered = PaperAlpacaReadClient(
            _FAKE_KEY, _FAKE_SECRET,
            transport=lambda *_: _accepted(draft.client_order_id),
        )
        lookup = executor.lookup_unknown_once(draft.client_order_id, at=_AT, reader=recovered)
        _require(lookup.stage is Stage.BROKER_ACCEPTED, "lookup can recover by exact client ID")
        _require(len(calls) == 1, "lookup never submits another fake POST")
        scenarios["timeout_unknown_no_retry_then_read_only_recovery"] = "PASS"

    # 3. Malformed broker identity cannot become a successful fill.
    with PersistentPaperOrderStore(":memory:") as store:
        draft = _draft(store, "malformed")
        calls: list[str] = []

        def malformed_transport(*_):
            calls.append("FAKE_ONLY")
            return {
                "id": "synthetic-provider-001", "client_order_id": "wrong-id",
                "status": "filled", "filled_qty": "0.0002",
                "filled_avg_price": "65000",
            }

        executor = PaperOnceExecutor(
            paper_key=_FAKE_KEY, paper_secret=_FAKE_SECRET,
            store=store, transport=malformed_transport,
        )
        result = executor.submit_once(draft, at=_AT)
        _require(result.stage is Stage.UNKNOWN_RESULT, "malformed fill remains unknown")
        _require(store.has_unresolved_provider_order(), "bad identity blocks next order")
        fake_post_attempts += len(calls)
        scenarios["mismatched_broker_identity_fails_closed"] = "PASS"

    # 4. Invalid amount is rejected BEFORE any injected transport.
    with PersistentPaperOrderStore(":memory:") as store:
        draft = _draft(store, "invalid")
        calls: list[str] = []

        def forbidden_transport(*_):
            calls.append("FAKE_ONLY")
            raise AssertionError("invalid draft may not reach even mock transport")

        executor = PaperOnceExecutor(
            paper_key=_FAKE_KEY, paper_secret=_FAKE_SECRET,
            store=store, transport=forbidden_transport,
        )
        invalid = PaperOrderDraft(
            draft.client_order_id, {**draft.payload, "notional": "100"},
        )
        try:
            executor.submit_once(invalid, at=_AT)
        except ValueError:
            pass
        else:
            raise RuntimeError("synthetic invalid amount was not rejected")
        _require(not calls, "invalid payload never reaches mock POST")
        _require(store.connection.execute(
            "SELECT COUNT(*) FROM paper_order_states").fetchone()[0] == 0,
            "invalid payload created no submission state")
        _require(store.connection.execute(
            "SELECT status FROM drafts WHERE client_order_id=?",
            (draft.client_order_id,)).fetchone()[0] == "DRAFT_APPROVED",
            "invalid payload preserved the untouched approved draft")
        scenarios["guardian_envelope_invalid_amount_rejected_pretransport"] = "PASS"

    # 5. Even a synthetic FILLED broker response is terminal UNRECONCILED.
    with PersistentPaperOrderStore(":memory:") as store:
        draft = _draft(store, "filled")
        calls: list[str] = []

        def filled_transport(*_):
            calls.append("FAKE_ONLY")
            return {
                "id": "synthetic-provider-001",
                "client_order_id": draft.client_order_id,
                "status": "filled",
                "filled_qty": "0.00023",
                "filled_avg_price": "65100",
            }

        executor = PaperOnceExecutor(
            paper_key=_FAKE_KEY, paper_secret=_FAKE_SECRET,
            store=store, transport=filled_transport,
        )
        outcome = executor.submit_once(draft, at=_AT)
        _require(outcome.stage is Stage.BROKER_TERMINAL_UNRECONCILED,
                 "filled cannot mean reconciled")
        _require(store.journal.total_reserved_usd() == Decimal("15"),
                 "fill retains reservation pending separate audit")
        _require(store.has_unresolved_provider_order(), "unreconciled fill blocks future orders")
        fake_post_attempts += len(calls)
        scenarios["filled_requires_independent_reconciliation"] = "PASS"

    _require(len(scenarios) == 5, "all distinct cases completed")
    return {
        "kind": "OFFLINE_ISOLATED_SYNTHETIC_PAPER_EXECUTION_DRILL",
        "result": "PASS_FAKE_PROVIDER_STATE_TRANSITIONS_ONLY",
        "scenarios": scenarios,
        "scenarios_passed": len(scenarios),
        "injected_fake_transport_attempts": fake_post_attempts,
        "database": "FRESH_IN_MEMORY_SQLITE_PER_SCENARIO",
        "network_requests": "NONE",
        "provider_account_access": "NONE",
        "credentials": "FAKE_LITERALS_ONLY",
        "actual_paper_order_posts": "NONE",
        "live_orders": "DISABLED",
        "installed_mac_observer_modified": False,
        "warning": "Synthetic engineering rehearsal, NOT an Alpaca paper order, fill, profitability proof or trading authorization.",
    }


def main() -> int:
    try:
        result = run_offline_execution_drill()
    except Exception as exc:
        result = {
            "kind": "OFFLINE_ISOLATED_SYNTHETIC_PAPER_EXECUTION_DRILL",
            "result": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "actual_paper_order_posts": "NONE",
            "network_requests": "NONE",
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
