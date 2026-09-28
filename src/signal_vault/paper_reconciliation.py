"""Conservative terminal-order reconciliation audit for Alpaca paper.

This is an AUDITOR, not an executor. It performs authenticated GET-only checks
through the already hard-bound paper client. A filled order is intentionally
*not* considered fully reconciled until crypto-fee accounting is implemented;
zero-fill terminal orders may be released after order/account/position checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .paper_audit import (CryptoFeeAudit, FillAudit, audit_crypto_fee_activities,
                          audit_fill_activities)
from .paper_executor import parse_paper_observation
from .paper_order_state import Stage
from .paper_store import PersistentPaperOrderStore


def _finite_nonnegative(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid provider {field}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"invalid provider {field}")
    return result


def _btc_position_qty(positions: tuple[Mapping[str, object], ...]) -> Decimal:
    matches: list[Decimal] = []
    for item in positions:
        symbol = str(item.get("symbol", "")).replace("/", "")
        if symbol != "BTCUSD":
            continue
        qty = _finite_nonnegative(item.get("qty"), "BTC position quantity")
        matches.append(qty)
    if len(matches) > 1:
        raise ValueError("multiple BTC/USD provider position rows; halt")
    return matches[0] if matches else Decimal("0")


@dataclass(frozen=True)
class TerminalReconciliationAudit:
    client_order_id: str
    order_verified: bool
    fills_verified: bool
    account_verified: bool
    position_verified: bool
    fees_final: bool
    provider_btc_qty: Decimal
    fill_audit: FillAudit
    fee_audit: CryptoFeeAudit
    accounted_fee_usd_equiv: Decimal
    inferred_btc_fee_qty: Decimal
    fee_pending: bool
    ready_to_release: bool
    explanation: str


def audit_terminal_paper_order(*, store: PersistentPaperOrderStore,
                               reader: PaperAlpacaReadClient,
                               client_order_id: str) -> TerminalReconciliationAudit:
    state = store.get(client_order_id)
    if state.stage is not Stage.BROKER_TERMINAL_UNRECONCILED:
        raise ValueError("terminal unreconciled paper order required")
    payload = store.get_draft_payload(client_order_id)
    side = payload.get("side")
    if side not in ("buy", "sell"):
        raise ValueError("stored paper order side is invalid")

    raw_order = reader.lookup_order(client_order_id)
    if raw_order is None:
        raise ValueError("terminal provider order disappeared during reconciliation")
    observed = parse_paper_observation(raw_order, client_order_id)
    # Reuse state machine's immutable terminal consistency checks without saving.
    repeated = state.observe(observed)
    if repeated != state:
        raise ValueError("terminal provider order changed during reconciliation")
    order_verified = True

    activities = reader.get_fill_activities(state.broker_order_id) if state.cumulative_filled_qty else ()
    fill_audit = audit_fill_activities(state, activities)

    account = reader.get_account()
    if str(account.get("status", "")).upper() != "ACTIVE" or account.get("trading_blocked") is not False:
        raise ValueError("paper account is not active/unblocked during reconciliation")
    _finite_nonnegative(account.get("non_marginable_buying_power"), "non-marginable buying power")
    account_verified = True

    if state.cumulative_filled_qty == 0:
        fee_audit = CryptoFeeAudit(state.broker_order_id, Decimal("0"), Decimal("0"),
                                   Decimal("0"), (), True)
    else:
        fee_audit = audit_crypto_fee_activities(state.broker_order_id,
                                                reader.get_fee_activities(state.broker_order_id))

    btc_qty = _btc_position_qty(reader.get_positions())
    prior_btc = store.logical_account()["btc_qty"]
    if state.cumulative_filled_qty == 0:
        expected_btc = prior_btc
        position_verified = btc_qty == expected_btc
    elif side == "buy":
        # Alpaca documents BTC/USD buy fees as charged in received BTC and fee
        # activities may post later. Until final, accept only the narrow physical
        # range [prior, prior+fill]; once posted, require exact net inventory.
        if fee_audit.final:
            if fee_audit.usd_fee_amount != 0:
                raise ValueError("BTC/USD buy unexpectedly has USD-denominated fee")
            expected_btc = prior_btc + state.cumulative_filled_qty - fee_audit.btc_fee_qty
            position_verified = btc_qty == expected_btc
        else:
            expected_btc = prior_btc + state.cumulative_filled_qty
            position_verified = prior_btc <= btc_qty <= expected_btc
    else:
        # BTC/USD sell receives USD, so fee should not consume extra BTC.
        if fee_audit.final and fee_audit.btc_fee_qty != 0:
            raise ValueError("BTC/USD sell unexpectedly has BTC-denominated fee")
        expected_btc = prior_btc - state.cumulative_filled_qty
        if expected_btc < 0:
            raise ValueError("terminal fill exceeds logical BTC inventory")
        position_verified = btc_qty == expected_btc
    if expected_btc < 0:
        raise ValueError("terminal fill exceeds logical BTC inventory")
    if not position_verified:
        raise ValueError("provider BTC position does not reconcile to logical inventory, fills and fees")

    fees_final = fee_audit.final
    inferred_btc_fee = Decimal("0")
    accounted_fee = fee_audit.fee_usd_equivalent
    fee_pending = False
    if state.cumulative_filled_qty > 0 and side == "buy" and not fees_final:
        # Buy fee is charged in received BTC. Provider net position plus audited
        # gross FILL quantity lets us infer the exact base-asset fee immediately,
        # so a risk-reducing sell does not have to wait until end-of-day CFEE.
        inferred_btc_fee = state.cumulative_filled_qty - (btc_qty - prior_btc)
        if inferred_btc_fee < 0 or inferred_btc_fee > state.cumulative_filled_qty:
            raise ValueError("cannot infer a sane BTC buy fee from provider position")
        if state.filled_avg_price is None:
            raise ValueError("filled buy lacks provider average price")
        accounted_fee = inferred_btc_fee * state.filled_avg_price
        fee_pending = True

    ready = order_verified and fill_audit.verified and account_verified and position_verified and (
        fees_final or (side == "buy" and fee_pending))
    if ready and fee_pending:
        explanation = "terminal buy verified; BTC fee inferred from net provider position and queued for later CFEE finalization"
    elif ready:
        explanation = "terminal paper order independently verified including provider fee activities"
    else:
        explanation = "order/fill/account/position verified but sell fee activity is not final; keep blocked"
    return TerminalReconciliationAudit(client_order_id, order_verified, fill_audit.verified,
                                       account_verified, position_verified, fees_final, btc_qty,
                                       fill_audit, fee_audit, accounted_fee, inferred_btc_fee,
                                       fee_pending, ready, explanation)


def release_verified_terminal(*, store: PersistentPaperOrderStore,
                              audit: TerminalReconciliationAudit, at):
    if not audit.ready_to_release:
        raise ValueError("terminal paper order is not fully audited")
    return store.finish_reconciliation_with_accounting(
        audit.client_order_id, at=at, provider_btc_qty=audit.provider_btc_qty,
        fee_usd_equiv=audit.accounted_fee_usd_equiv,
        usd_fee_amount=audit.fee_audit.usd_fee_amount,
        provider_cash_verified=True, provider_position_verified=True,
        provider_order_verified=True, fee_pending=audit.fee_pending,
        inferred_btc_fee_qty=audit.inferred_btc_fee_qty)


def release_verified_zero_fill(*, store: PersistentPaperOrderStore,
                               audit: TerminalReconciliationAudit, at) -> None:
    if audit.fill_audit.cumulative_qty != 0:
        raise ValueError("zero-fill release helper requires a zero-fill order")
    release_verified_terminal(store=store, audit=audit, at=at)
