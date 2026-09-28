"""One-cycle autonomous PAPER runtime with fail-closed recovery and reconciliation.

This module is deliberately not a daemon and exposes no live-trading endpoint.
It can submit an Alpaca *paper* order only when `allow_paper_submission=True`
and only through the hard-bound PaperOnceExecutor. Tests use fake transports.

A cycle performs, in order:
1. recover any uncertain/known provider order without duplicate POSTs;
2. independently reconcile terminal fills/fees/account/position;
3. verify provider account has no unexplained order/position drift;
4. read fully closed hourly history and a fresh authenticated quote;
5. mark Signal Vault's own logical $100 ledger (never Alpaca default balance);
6. generate a versioned deterministic signal, or HOLD;
7. Guardian + dynamic venue-rule validation;
8. persist a durable draft, then optionally make exactly one paper POST.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol, Sequence

from .alpaca_paper import PaperAlpacaReadClient, PaperOrderDraft
from .domain import Side, TradeIntent
from .market_data import Bar, CryptoQuote, validate_bars
from .paper_executor import PaperOnceExecutor
from .paper_order_state import Stage
from .paper_reconciliation import audit_terminal_paper_order, release_verified_terminal
from .paper_audit import audit_crypto_fee_activities
from .paper_store import PersistentPaperOrderStore
from .paper_supervisor import PaperRecoverySupervisor
from .strategy import Action, StrategyConfig, generate_signal
from .venue_rules import CryptoVenueRules


class BarProvider(Protocol):
    def fetch(self, *, start: datetime, end: datetime, as_of: datetime) -> Sequence[Bar]: ...


class QuoteProvider(Protocol):
    def latest_btc_usd(self, *, as_of: datetime, max_age_seconds: int = 90,
                       max_spread_bps: Decimal = Decimal("50")) -> CryptoQuote: ...


@dataclass(frozen=True)
class PaperCycleResult:
    state: str
    explanation: str
    evidence_id: str | None = None
    client_order_id: str | None = None
    provider_stage: str | None = None
    paper_post_attempted: bool = False


def _provider_btc_qty(reader: PaperAlpacaReadClient) -> Decimal:
    qty = Decimal("0")
    seen = False
    for row in reader.get_positions():
        symbol = str(row.get("symbol", "")).replace("/", "")
        try:
            value = Decimal(str(row.get("qty", "0")))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("invalid provider position quantity") from exc
        if not value.is_finite() or value < 0:
            raise ValueError("invalid provider position quantity")
        if symbol == "BTCUSD":
            if seen:
                raise ValueError("duplicate BTC/USD provider positions")
            seen = True
            qty = value
        elif value != 0:
            raise ValueError("unexpected external provider position; operator review required")
    return qty


def _verify_idle_provider_alignment(store: PersistentPaperOrderStore,
                                    reader: PaperAlpacaReadClient) -> CryptoVenueRules:
    """Require a clean account when no Signal Vault order is unresolved."""
    if store.has_unresolved_provider_order():
        raise ValueError("cannot perform idle alignment while provider order is unresolved")
    account = reader.get_account()
    if str(account.get("status", "")).upper() != "ACTIVE" or account.get("trading_blocked") is not False:
        raise ValueError("paper account is not confirmed active and unblocked")
    try:
        power = Decimal(str(account.get("non_marginable_buying_power")))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid paper buying power") from exc
    if not power.is_finite() or power < 0:
        raise ValueError("invalid paper buying power")
    if reader.get_open_orders():
        raise ValueError("unexpected provider open order; operator review required")
    logical_btc = store.logical_account()["btc_qty"]
    if _provider_btc_qty(reader) != logical_btc:
        raise ValueError("provider BTC position differs from Signal Vault logical inventory")
    return reader.get_btc_rules()


def _closed_hour_end(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware runtime time required")
    utc = now.astimezone(timezone.utc)
    return utc.replace(minute=0, second=0, microsecond=0)


class PaperCycleRunner:
    def __init__(self, *, store: PersistentPaperOrderStore,
                 reader: PaperAlpacaReadClient,
                 executor: PaperOnceExecutor,
                 bars: BarProvider,
                 quotes: QuoteProvider,
                 strategy: StrategyConfig | None = None,
                 history_hours: int = 72) -> None:
        if history_hours < 30 or history_hours > 500:
            raise ValueError("history_hours outside reviewed bounds")
        self.store = store
        self.reader = reader
        self.executor = executor
        self.bars = bars
        self.quotes = quotes
        self.strategy = strategy or StrategyConfig()
        self.history_hours = history_hours

    def _recover_and_reconcile(self, *, now: datetime) -> PaperCycleResult | None:
        recovery = PaperRecoverySupervisor(store=self.store, executor=self.executor,
                                           reader=self.reader).recover_once(at=now)
        # A supervisor may advance a known order to terminal in this very cycle.
        for state in self.store.list_states():
            if state.stage is not Stage.BROKER_TERMINAL_UNRECONCILED:
                continue
            try:
                audit = audit_terminal_paper_order(store=self.store, reader=self.reader,
                                                   client_order_id=state.client_order_id)
            except Exception as exc:
                return PaperCycleResult("BLOCKED_RECONCILIATION",
                                        f"terminal audit failed closed: {type(exc).__name__}: {exc}",
                                        client_order_id=state.client_order_id)
            if not audit.ready_to_release:
                return PaperCycleResult("BLOCKED_RECONCILIATION", audit.explanation,
                                        client_order_id=state.client_order_id)
            release_verified_terminal(store=self.store, audit=audit, at=now)

        if self.store.has_unresolved_provider_order():
            detail = recovery.explanation
            unresolved = next((s for s in self.store.list_states() if s.blocks_new_execution), None)
            return PaperCycleResult("BLOCKED_PROVIDER_ORDER", detail,
                                    client_order_id=unresolved.client_order_id if unresolved else None,
                                    provider_stage=unresolved.stage.value if unresolved else None)

        # CFEE for crypto buys may post later. A buy can be released using the
        # exact fee quantity inferred from provider net BTC inventory, then the
        # USD-equivalent valuation is finalized asynchronously when CFEE appears.
        for client_order_id in self.store.pending_fee_order_ids():
            state = self.store.get(client_order_id)
            if not state.broker_order_id:
                return PaperCycleResult("BLOCKED_FEE_AUDIT", "pending fee audit lost broker identity",
                                        client_order_id=client_order_id)
            try:
                fee = audit_crypto_fee_activities(
                    state.broker_order_id, self.reader.get_fee_activities(state.broker_order_id))
                if fee.final:
                    self.store.settle_pending_buy_fee(
                        client_order_id, at=now, final_fee_usd_equiv=fee.fee_usd_equivalent,
                        final_btc_fee_qty=fee.btc_fee_qty,
                        final_usd_fee_amount=fee.usd_fee_amount)
            except Exception as exc:
                return PaperCycleResult("BLOCKED_FEE_AUDIT",
                                        f"deferred provider fee audit failed closed: {type(exc).__name__}: {exc}",
                                        client_order_id=client_order_id)
        return None

    def run_once(self, *, now: datetime, allow_paper_submission: bool = False) -> PaperCycleResult:
        """Run one autonomous decision cycle; default never sends a paper order."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("timezone-aware runtime time required")

        blocked = self._recover_and_reconcile(now=now)
        if blocked is not None:
            return blocked

        try:
            rules = _verify_idle_provider_alignment(self.store, self.reader)
        except Exception as exc:
            return PaperCycleResult("BLOCKED_PROVIDER_DRIFT",
                                    f"provider alignment failed closed: {type(exc).__name__}: {exc}")

        end = _closed_hour_end(now)
        start = end - timedelta(hours=self.history_hours)
        try:
            history = tuple(self.bars.fetch(start=start, end=end, as_of=now))
            history = validate_bars(history, as_of=now, min_count=self.strategy.slow_hours + 2)
            quote = self.quotes.latest_btc_usd(as_of=now)
        except Exception as exc:
            return PaperCycleResult("HOLD_BAD_MARKET_DATA",
                                    f"market data failed closed: {type(exc).__name__}: {exc}")

        halted, halt_reason = self.store.operator_halt()
        portfolio = self.store.mark_portfolio(mark_price=quote.mid, at=now, halted=halted)
        if halted:
            return PaperCycleResult("OPERATOR_HALTED",
                                    "operator emergency halt active" +
                                    (f": {halt_reason}" if halt_reason else ""))
        signal = generate_signal(history, self.strategy)
        if signal.action is Action.HOLD:
            return PaperCycleResult("HOLD", signal.explanation, evidence_id=signal.evidence_id)

        logical_btc = self.store.logical_account()["btc_qty"]
        if signal.action is Action.BUY and logical_btc > 0:
            return PaperCycleResult("HOLD", "already holding reconciled BTC; V1 does not pyramid",
                                    evidence_id=signal.evidence_id)
        if signal.action is Action.SELL and logical_btc <= 0:
            return PaperCycleResult("HOLD", "no reconciled BTC inventory to sell",
                                    evidence_id=signal.evidence_id)

        side = Side(signal.action.value)
        execution_price = quote.execution_reference(side.value)
        notional = Decimal("15") if side is Side.BUY else logical_btc * execution_price
        order_id = "sv-" + signal.evidence_id[:30]
        intent = TradeIntent("crypto", "alpaca", "BTC/USD", side, notional,
                             order_id, signal.evidence_id, quote.timestamp)
        try:
            if side is Side.BUY:
                rules.validate_buy_notional(notional, execution_price)
                sell_qty = None
            else:
                rules.validate_sell_qty(logical_btc, execution_price)
                sell_qty = logical_btc
            draft = self.store.record_logical_draft(
                intent, portfolio, checked_at=now, reference_price=execution_price,
                full_sell_quantity=sell_qty)
        except Exception as exc:
            return PaperCycleResult("REJECTED", f"Guardian/venue draft rejected: {exc}",
                                    evidence_id=signal.evidence_id, client_order_id=order_id)

        # Same closed bar may be evaluated repeatedly by a scheduler. If this ID
        # already entered provider execution, never POST it a second time.
        existing = next((s for s in self.store.list_states()
                         if s.client_order_id == draft.client_order_id), None)
        if existing is not None:
            return PaperCycleResult("ALREADY_PROCESSED",
                                    "signal/order ID already entered durable provider lifecycle",
                                    evidence_id=signal.evidence_id,
                                    client_order_id=draft.client_order_id,
                                    provider_stage=existing.stage.value)

        if not allow_paper_submission:
            return PaperCycleResult("PAPER_DRAFT_READY",
                                    "durable Guardian-approved paper draft recorded; POST disabled for this cycle",
                                    evidence_id=signal.evidence_id,
                                    client_order_id=draft.client_order_id,
                                    paper_post_attempted=False)

        outcome = self.executor.submit_once(draft, at=now)
        return PaperCycleResult("PAPER_SUBMISSION_RECORDED", outcome.explanation,
                                evidence_id=signal.evidence_id,
                                client_order_id=draft.client_order_id,
                                provider_stage=outcome.stage.value,
                                paper_post_attempted=True)
