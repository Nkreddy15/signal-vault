"""FIRST ONE-TIME supervised $15 Alpaca PAPER smoke. NEVER scheduled or live.

There are two explicit CLI modes:
  --execute    Requires an interactive local terminal AND exact typed consent
               before Keychain/network. Rechecks fresh account/asset/quote,
               Guardian/durable journal, then attempts at most one PAPER POST.
  --reconcile  No POST. Reconcile the same persisted order by exact client ID,
               preserving UNKNOWN_RESULT and funds until independently audited.

Never invoke this module from LaunchAgent. It is a diagnostic broker-system
acceptance test, NOT a promoted strategy, automated trading or profit claim.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from .alpaca_paper import PaperAlpacaReadClient
from .domain import Side, TradeIntent
from .operator_view import read_local_paper_snapshot
from .paper_executor import PaperOnceExecutor, parse_paper_observation
from .paper_order_state import Stage
from .paper_reconciliation import audit_terminal_paper_order, release_verified_terminal, _btc_position_qty
from .paper_audit import audit_crypto_fee_activities
from .paper_smoke_preview import (
    AMOUNT, MAX_SPREAD_BPS, _quote_client, _usd, _valid_local, _validate_quote,
)
from .paper_store import PersistentPaperOrderStore
from .preflight import check_sqlite_runtime, inspect_paper_runtime
from .runtime_lock import RuntimeFileLock
from .venue_rules import CryptoVenueRules

# Explicit one-time local authorization to use the owner's PAPER Keychain
# credentials for a broker PAPER POST. An earlier GET-only preview is NOT this.
CONSENT = "AUTHORIZE ONE $15 BTC/USD ALPACA PAPER BUY"
_FORBIDDEN_LIVE_ENV = ("SIGNAL_VAULT_LIVE", "SIGNAL_VAULT_LIVE_TRADING",
                       "SIGNAL_VAULT_MODE")


def _report(kind: str) -> dict[str, object]:
    return {
        "kind": kind, "status": "BLOCKED", "reason_code": "NOT_CHECKED",
        "failure_class": None, "instrument": "BTC/USD",
        "diagnostic_notional_usd": "15.00",
        "actual_paper_post_possibly_attempted": False,
        "automatic_paper_orders": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "installed_mac_collector_modified": False,
        "credentials_logged": False,
        "warning": (
            "A one-time PAPER broker-engineering test, NOT evidence of strategy "
            "profitability. UNKNOWN_RESULT must be reconciled, NEVER blindly retried."
        ),
    }


def _env_safe() -> bool:
    return not any(
        os.environ.get(name, "").strip().lower() in
        ("live", "true", "1", "enabled", "yes")
        for name in _FORBIDDEN_LIVE_ENV
    )


def _clock(clock: Callable[[], datetime]) -> datetime:
    instant = clock()
    if (not isinstance(instant, datetime) or instant.tzinfo is None
            or instant.utcoffset() is None):
        raise ValueError("timezone-aware current clock required")
    return instant.astimezone(timezone.utc)


def _private_existing_db(db: str | Path) -> Path:
    path = Path(db).expanduser()
    # inspect/check BEFORE opening the writer to avoid silently creating a DB.
    check_sqlite_runtime(path)
    return path


def _credentials(loader: Callable[[], object] | None) -> tuple[str, str]:
    if loader is None:
        from .unattended_forward_cycle import load_keychain_paper_data_credentials
        loader = load_keychain_paper_data_credentials
    value = loader()
    key, secret = value.key_id, value.secret_key
    if (not isinstance(key, str) or not isinstance(secret, str)
            or not key.strip() or not secret.strip()):
        raise ValueError("invalid PAPER Keychain credentials")
    return key, secret


def _fresh_paper_checks(
    key: str, secret: str, *, instant: datetime,
    paper_factory: Callable[..., object],
    quote_factory: Callable[..., object],
) -> tuple[object, CryptoVenueRules]:
    reader = paper_factory(key, secret)
    account = reader.get_account()
    asset = reader.get_btc_asset()
    positions = reader.get_positions()
    orders = reader.get_open_orders()
    rules = CryptoVenueRules.from_asset(asset)
    buying_power = _usd(account.get("non_marginable_buying_power"))
    if (str(account.get("status", "")).upper() != "ACTIVE"
            or account.get("trading_blocked") is not False
            or buying_power < AMOUNT or positions or orders):
        raise PermissionError("paper account status, buying power, or inventory drift")
    quotes = quote_factory(key, secret)
    quote = _validate_quote(
        quotes.latest_btc_usd(as_of=instant, max_age_seconds=90,
                              max_spread_bps=MAX_SPREAD_BPS),
        now=instant)
    # Both the conservative internal $10 floor and the provider's CURRENT
    # dynamic venue minimum apply; never auto-upsize the $15 diagnostic.
    if AMOUNT < Decimal("10"):
        raise ValueError("internal notional floor not met")
    rules.validate_buy_notional(AMOUNT, quote.ask)
    return quote, rules


def execute_one_paper_smoke(
    *, approval: str,
    db: str | Path = "data/signal-vault-paper.sqlite3",
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    credential_loader: Callable[[], object] | None = None,
    paper_factory: Callable[..., object] = PaperAlpacaReadClient,
    quote_factory: Callable[..., object] = _quote_client,
    submit_transport: Callable[..., object] | None = None,
    client_id_factory: Callable[[], str] | None = None,
) -> dict[str, object]:
    """One explicit operator-approved PAPER-only attempt. No generic scheduler."""
    report = _report("SUPERVISED_ONE_TIME_ALPACA_PAPER_SMOKE")
    if approval != CONSENT:
        report["reason_code"] = "EXACT_LOCAL_CONSENT_REQUIRED"
        return report
    if not _env_safe():
        report["reason_code"] = "LIVE_MODE_ENVIRONMENT_FORBIDDEN"
        return report

    try:
        path = _private_existing_db(db)
    except Exception as exc:
        report["reason_code"] = "MISSING_OR_INVALID_EXISTING_PAPER_LEDGER"
        report["failure_class"] = type(exc).__name__
        return report

    # Same process lock as paper_worker. It is NOT the collector's separate lock.
    lock_path = path.with_name(path.name + ".lock")
    try:
        with RuntimeFileLock(lock_path):
            local = inspect_paper_runtime(path)
            snapshot = read_local_paper_snapshot(path)
            if not _valid_local(local, snapshot):
                report["reason_code"] = "NOT_THE_EMPTY_INITIAL_100_USD_LEDGER"
                return report
            with PersistentPaperOrderStore(path) as store:
                if (store.has_unresolved_provider_order()
                        or store.operator_halt()[0]
                        or store.list_states()
                        or store.connection.execute(
                            "SELECT COUNT(*) FROM drafts").fetchone()[0] != 0):
                    report["reason_code"] = "PREVIOUS_DRAFT_ORDER_OR_HALT_PRESENT"
                    return report

                try:
                    key, secret = _credentials(credential_loader)
                except Exception as exc:
                    report["reason_code"] = "OWNER_PAPER_KEYCHAIN_UNAVAILABLE"
                    report["failure_class"] = type(exc).__name__
                    return report

                try:
                    asof = _clock(clock)
                    quote, rules = _fresh_paper_checks(
                        key, secret, instant=asof, paper_factory=paper_factory,
                        quote_factory=quote_factory)
                    # Re-evaluate freshness AFTER all provider reads and immediately
                    # before persisting a draft. A stale quote is never rescued.
                    checked_at = _clock(clock)
                    _validate_quote(quote, now=checked_at)
                    rules.validate_buy_notional(AMOUNT, quote.ask)
                except Exception as exc:
                    report["reason_code"] = "CURRENT_PAPER_ACCOUNT_QUOTE_OR_RULES_FAILED"
                    report["failure_class"] = type(exc).__name__
                    return report

                token = client_id_factory() if client_id_factory is not None else secrets.token_hex(4)
                if (not isinstance(token, str) or len(token) != 8
                        or any(ch not in "0123456789abcdef" for ch in token)):
                    report["reason_code"] = "INVALID_DIAGNOSTIC_ORDER_ID_TOKEN"
                    return report
                client_id = "svsmk-" + checked_at.strftime("%Y%m%dT%H%M%SZ") + "-" + token
                report["client_order_id"] = client_id
                try:
                    # Actual $100 experiment is derived from local ledger, not Alpaca's
                    # default high simulated buying power. No strategy promotion.
                    portfolio = store.mark_portfolio(
                        mark_price=quote.mid, at=checked_at, halted=False)
                    intent = TradeIntent(
                        "crypto", "alpaca", "BTC/USD", Side.BUY, AMOUNT,
                        client_id, "DIAGNOSTIC_NOT_PROMOTED_STRATEGY_" + client_id,
                        quote.timestamp)
                    draft = store.record_logical_draft(
                        intent, portfolio, checked_at=checked_at,
                        reference_price=quote.ask)
                    # Draft is durable; any unexpected error from here onward
                    # demands operator review rather than blindly re-running.
                    _validate_quote(quote, now=_clock(clock))
                    rules.validate_buy_notional(AMOUNT, quote.ask)
                except Exception as exc:
                    report["reason_code"] = "DURABLE_GUARDIAN_DRAFT_OR_FRESHNESS_FAILED"
                    report["failure_class"] = type(exc).__name__
                    report["operator_review_required"] = True
                    return report

                # The only production POST site in this module. Exactly one call,
                # hardcoded paper host in PaperOnceExecutor. Timeout -> UNKNOWN.
                executor = (PaperOnceExecutor(
                    paper_key=key, paper_secret=secret, store=store)
                    if submit_transport is None else PaperOnceExecutor(
                        paper_key=key, paper_secret=secret, store=store,
                        transport=submit_transport))
                report["actual_paper_post_possibly_attempted"] = True
                try:
                    outcome = executor.submit_once(draft, at=_clock(clock))
                except Exception as exc:
                    report["status"] = "STOP_AND_RECONCILE_BEFORE_ANY_OTHER_ACTION"
                    report["reason_code"] = "POST_BOUNDARY_RESULT_UNCERTAIN"
                    report["failure_class"] = type(exc).__name__
                    report["operator_review_required"] = True
                    return report
                report["provider_stage"] = outcome.stage.value
                report["status"] = (
                    "UNKNOWN_RESULT_RECONCILE_NO_RETRY"
                    if outcome.stage is Stage.UNKNOWN_RESULT
                    else "ONE_PAPER_POST_ATTEMPT_RECORDED_RECONCILIATION_REQUIRED")
                report["reason_code"] = "NONE"
                report["operator_review_required"] = True
                report["paper_order_filled_and_reconciled"] = False
                return report
    except Exception as exc:
        # Do not leak an untrusted provider exception body or local file contents.
        report["status"] = "STOP_AND_REVIEW_EXISTING_PAPER_LEDGER"
        report["reason_code"] = "LOCAL_LOCK_OR_PERSISTENCE_FAILURE"
        report["failure_class"] = type(exc).__name__
        report["operator_review_required"] = True
        return report


def _check_and_finalize_deferred_buy_fee(
    *, store: PersistentPaperOrderStore, reader: PaperAlpacaReadClient,
    state, at: datetime,
) -> bool:
    """One GET-only provider fee check for an already RECONCILED first BUY.

    A broker fee may post later than its fill. Only the first persisted order's
    own fee can be settled, and only if independent read-only provider checks
    still match the exact broker order, inventory and fee quantity inferred at
    fill reconciliation. No POST/cancel/withdrawal is reachable here.
    """
    pending = store.pending_fee_order_ids()
    if not pending:
        return True
    if (pending != (state.client_order_id,) or state.stage is not Stage.RECONCILED
            or state.provider_status != "filled" or not state.broker_order_id
            or state.cumulative_filled_qty <= 0):
        raise ValueError("deferred fee does not belong to reconciled first filled order")

    raw = reader.lookup_order(state.client_order_id)
    if raw is None:
        raise ValueError("original provider order lookup missing")
    observed = parse_paper_observation(raw, state.client_order_id)
    if (observed.broker_order_id != state.broker_order_id
            or observed.provider_status != "filled"
            or observed.cumulative_filled_qty != state.cumulative_filled_qty
            or observed.filled_avg_price != state.filled_avg_price):
        raise ValueError("original provider filled order changed since reconciliation")

    account = reader.get_account()
    if (str(account.get("status", "")).upper() != "ACTIVE"
            or account.get("trading_blocked") is not False):
        raise ValueError("provider paper account not active/unblocked")
    _usd(account.get("non_marginable_buying_power"))
    if reader.get_open_orders():
        raise ValueError("unexpected paper open order during deferred fee audit")
    positions = reader.get_positions()
    if any(str(row.get("symbol", "")).replace("/", "") != "BTCUSD"
           for row in positions):
        raise ValueError("unexpected paper account position during deferred fee audit")
    if _btc_position_qty(positions) != store.logical_account()["btc_qty"]:
        raise ValueError("provider BTC quantity no longer matches reconciled local ledger")

    audited = audit_crypto_fee_activities(
        state.broker_order_id, reader.get_fee_activities(state.broker_order_id))
    if not audited.final:
        # No fee activity yet. Retain the inferred provisional fee and the
        # durable fee-pending record; never silently assume the fee was zero.
        return False
    store.settle_pending_buy_fee(
        state.client_order_id, at=at,
        final_fee_usd_equiv=audited.fee_usd_equivalent,
        final_btc_fee_qty=audited.btc_fee_qty,
        final_usd_fee_amount=audited.usd_fee_amount)
    return True


def reconcile_one_paper_smoke(
    *, db: str | Path = "data/signal-vault-paper.sqlite3",
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    credential_loader: Callable[[], object] | None = None,
    paper_factory: Callable[..., object] = PaperAlpacaReadClient,
) -> dict[str, object]:
    """Explicit GET-only broker lookup and existing journal audit; NEVER POST."""
    report = _report("SUPERVISED_PAPER_SMOKE_READ_ONLY_PROVIDER_RECONCILIATION")
    report["broker_order_submission"] = "DISABLED_ALWAYS_FOR_RECONCILIATION"
    if not _env_safe():
        report["reason_code"] = "LIVE_MODE_ENVIRONMENT_FORBIDDEN"
        return report
    try:
        path = _private_existing_db(db)
        with RuntimeFileLock(path.with_name(path.name + ".lock")):
            with PersistentPaperOrderStore(path) as store:
                states = store.list_states()
                if len(states) != 1:
                    report["reason_code"] = "EXACTLY_ONE_EXISTING_PAPER_ORDER_STATE_REQUIRED"
                    return report
                state = states[0]
                report["client_order_id"] = state.client_order_id
                if state.stage is Stage.RECONCILED:
                    report["provider_stage"] = state.stage.value
                    pending = store.pending_fee_order_ids()
                    if not pending:
                        report["status"] = "ALREADY_RECONCILED_FEES_FINAL"
                        report["reason_code"] = "NONE"
                        report["pending_fee_audits"] = 0
                        return report
                    # Even once the order/position is reconciled, its provider
                    # crypto fee may post later. --reconcile is the ONLY manual
                    # first-smoke continuation and it never sends a new POST.
                    try:
                        key, secret = _credentials(credential_loader)
                        reader = paper_factory(key, secret)
                        final = _check_and_finalize_deferred_buy_fee(
                            store=store, reader=reader, state=state, at=_clock(clock))
                    except Exception as exc:
                        report["status"] = "RECONCILED_ORDER_FEE_AUDIT_REQUIRES_REVIEW"
                        report["reason_code"] = "PROVIDER_FEE_FINALIZATION_FAILED_CLOSED"
                        report["failure_class"] = type(exc).__name__
                        report["pending_fee_audits"] = len(store.pending_fee_order_ids())
                        report["operator_review_required"] = True
                        return report
                    report["status"] = ("PAPER_ORDER_RECONCILED_FEE_FINALIZED"
                                        if final else "PAPER_ORDER_RECONCILED_FEE_STILL_PENDING")
                    report["reason_code"] = "NONE"
                    report["pending_fee_audits"] = len(store.pending_fee_order_ids())
                    report["operator_review_required"] = False
                    return report
                try:
                    key, secret = _credentials(credential_loader)
                    reader = paper_factory(key, secret)
                    executor = PaperOnceExecutor(
                        paper_key=key, paper_secret=secret, store=store,
                        # A defensive, unreachable fake POST closure: even a
                        # future refactor of reconciliation cannot submit.
                        transport=lambda *_: (_ for _ in ()).throw(
                            RuntimeError("POST FORBIDDEN IN RECONCILIATION")))
                    at = _clock(clock)
                    if state.stage is Stage.SUBMISSION_PENDING:
                        store.recover_inflight_pending_after_restart(at=at)
                        state = store.get(state.client_order_id)
                    if state.stage is Stage.UNKNOWN_RESULT:
                        state = executor.lookup_unknown_once(
                            state.client_order_id, at=at, reader=reader).state
                    elif state.stage in (Stage.BROKER_ACCEPTED, Stage.PARTIALLY_FILLED):
                        state = executor.poll_known_once(
                            state.client_order_id, at=at, reader=reader).state
                    if state.stage is Stage.BROKER_TERMINAL_UNRECONCILED:
                        audit = audit_terminal_paper_order(
                            store=store, reader=reader,
                            client_order_id=state.client_order_id)
                        if audit.ready_to_release:
                            state = release_verified_terminal(
                                store=store, audit=audit, at=at)
                except Exception as exc:
                    report["reason_code"] = "PROVIDER_LOOKUP_OR_AUDIT_PENDING_REVIEW"
                    report["failure_class"] = type(exc).__name__
                    report["operator_review_required"] = True
                    return report

                report["provider_stage"] = state.stage.value
                report["pending_fee_audits"] = len(store.pending_fee_order_ids())
                report["reason_code"] = "NONE"
                report["status"] = (
                    "PAPER_ORDER_RECONCILED"
                    if state.stage is Stage.RECONCILED
                    else "PROVIDER_LOOKUP_OR_FEE_FINALIZATION_STILL_REQUIRED")
                report["operator_review_required"] = state.stage is not Stage.RECONCILED
                return report
    except Exception as exc:
        report["reason_code"] = "MISSING_BAD_OR_LOCKED_EXISTING_PAPER_LEDGER"
        report["failure_class"] = type(exc).__name__
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-time SUPERVISED $15 PAPER BTC smoke; NEVER live or scheduled.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--execute", action="store_true",
                       help="Interactive explicit consent; ONE actual PAPER POST may occur.")
    group.add_argument("--reconcile", action="store_true",
                       help="GET-only provider lookup/reconciliation, NEVER POST.")
    parser.add_argument("--db", default="data/signal-vault-paper.sqlite3")
    args = parser.parse_args(argv)

    if args.reconcile:
        result = reconcile_one_paper_smoke(db=args.db)
    else:
        # Never allow piped input, remote scheduler, env-only approval or API
        # fallback to supply an unattended execution consent.
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            result = _report("SUPERVISED_ONE_TIME_ALPACA_PAPER_SMOKE")
            result["reason_code"] = "INTERACTIVE_LOCAL_TERMINAL_REQUIRED"
        else:
            print("WARNING: This will submit ONE actual $15 virtual-money BTC/USD BUY")
            print("to Alpaca PAPER ONLY, using your local Keychain PAPER credentials.")
            print("Market execution price and fees are not guaranteed.")
            print("It does NOT promote a strategy or enable autonomous paper orders.")
            entered = input("Type exactly '" + CONSENT + "' to proceed: ")
            result = execute_one_paper_smoke(approval=entered, db=args.db)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in (
        "ONE_PAPER_POST_ATTEMPT_RECORDED_RECONCILIATION_REQUIRED",
        "PAPER_ORDER_RECONCILED", "ALREADY_RECONCILED_FEES_FINAL",
        "PAPER_ORDER_RECONCILED_FEE_FINALIZED",
        "PAPER_ORDER_RECONCILED_FEE_STILL_PENDING") else 2


if __name__ == "__main__":
    raise SystemExit(main())
