"""Optional *paper-host-only* order writer, NEVER invoked by the offline CLI.

A call can only be made with an already Guardian-approved DURABLE draft and an
atomic journal transition to SUBMISSION_PENDING. All uncertain failures become
UNKNOWN_RESULT: the same order is never retried blindly. No live URL, host
argument, transfers, leverage, or automatic funding exist in this module.

REAL PAPER ORDER WARNING: invoking submit_once with actual paper keys WILL place
a paper order. The CLI and tests never invoke the production transport.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Mapping
from urllib.request import Request, build_opener

from .alpaca_paper import PAPER_ROOT, PaperAlpacaReadClient, PaperOrderDraft, _NoRedirects
from .paper_order_state import BrokerObservation, PaperOrderState, Stage
from .paper_store import PersistentPaperOrderStore
from .paper_audit import PaperHoldings
from .venue_rules import BtcVenueRules
from hmac import compare_digest

_ORDER_PATH = "/v2/orders"
_COMMON = {"symbol", "side", "type", "time_in_force", "client_order_id"}


def _check_draft_payload(raw: Mapping[str, str]) -> dict[str, str]:
    order = dict(raw)
    if order.get("symbol") != "BTC/USD" or order.get("type") != "market" or order.get("time_in_force") != "gtc":
        raise ValueError("unsupported paper BTC order shape")
    if order.get("side") == "buy":
        if set(order) != _COMMON | {"notional"}:
            raise ValueError("buy must contain notional and no extra fields")
        try:
            amount = Decimal(order["notional"])
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise ValueError("invalid USD amount") from exc
        if not amount.is_finite() or amount < Decimal("10") or amount > Decimal("15"):
            raise ValueError("paper buy outside Guardian envelope")
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError("invalid paper buy cent precision")
    elif order.get("side") == "sell":
        if set(order) != _COMMON | {"qty"}:
            raise ValueError("sell must contain quantity and no extra fields")
        try:
            qty = Decimal(order["qty"])
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise ValueError("invalid BTC quantity") from exc
        if not qty.is_finite() or qty <= 0 or qty.as_tuple().exponent < -9:
            raise ValueError("invalid BTC base quantity")
    else:
        raise ValueError("unsupported paper order side")
    client_id = order.get("client_order_id", "")
    if not isinstance(client_id, str) or len(client_id) > 48 or not client_id or not all(
        x.isascii() and (x.isalnum() or x in "_-") for x in client_id
    ):
        raise ValueError("invalid client order ID")
    return order


def _post_paper_json(payload: Mapping[str, str], key: str, secret: str) -> Mapping[str, object]:
    order = _check_draft_payload(payload)
    if not key or not secret:
        raise ValueError("separate PAPER credentials are required")
    # Only this literal host and this one literal POST path can be used.
    req = Request(PAPER_ROOT + _ORDER_PATH, method="POST",
                  data=json.dumps(order, separators=(",", ":")).encode("utf-8"),
                  headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                           "Accept": "application/json", "Content-Type": "application/json",
                           "User-Agent": "SignalVault/0.2"})
    with build_opener(_NoRedirects).open(req, timeout=12) as result:
        body = result.read(1_000_001)
    if len(body) > 1_000_000:
        raise ValueError("paper broker response too large")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("malformed paper order response")
    return data


def parse_paper_observation(data: Mapping[str, object], expected_client_id: str) -> BrokerObservation:
    if not isinstance(data, Mapping):
        raise ValueError("invalid provider response")
    if data.get("client_order_id") != expected_client_id:
        raise ValueError("provider client order ID mismatch")
    broker_id, status = data.get("id"), data.get("status")
    if not isinstance(broker_id, str) or not broker_id:
        raise ValueError("missing provider order ID")
    if not isinstance(status, str) or not status:
        raise ValueError("missing provider order status")
    try:
        qty = Decimal(str(data.get("filled_qty", "0")))
        avg = data.get("filled_avg_price")
        price = Decimal(str(avg)) if avg is not None else None
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ValueError("malformed provider fill attributes") from exc
    return BrokerObservation(expected_client_id, broker_id, status, qty, price)


@dataclass(frozen=True)
class PaperSubmissionOutcome:
    stage: Stage
    explanation: str
    state: PaperOrderState


class PaperOnceExecutor:
    """Single-attempt paper POST with mandatory durable state and no auto-retry."""

    def __init__(self, *, paper_key: str, paper_secret: str,
                 store: PersistentPaperOrderStore,
                 transport: Callable[[Mapping[str, str], str, str], Mapping[str, object]] = _post_paper_json):
        if not paper_key.strip() or not paper_secret.strip():
            raise ValueError("paper credentials required")
        self._key, self._secret, self._store, self._transport = paper_key, paper_secret, store, transport

    def submit_once(self, draft: PaperOrderDraft, *, at: datetime,
                    reader: PaperAlpacaReadClient) -> PaperSubmissionOutcome:
        """Preflight with independent PAPER GETs then persist baseline BEFORE POST.

        A caller cannot swap a different paper account for baseline verification.
        All preflight failures happen before the persistent submission transition
        and therefore before any network POST.
        """
        _check_draft_payload(draft.payload)
        if draft.client_order_id != draft.payload["client_order_id"]:
            raise ValueError("draft ID and payload ID do not match")
        if not isinstance(reader, PaperAlpacaReadClient) or (
            not compare_digest(reader._paper_key, self._key) or
            not compare_digest(reader._paper_secret, self._secret)
        ):
            raise PermissionError("preflight reader must be the same PAPER account as executor")
        constraints = BtcVenueRules.from_asset(reader.get_btc_asset())
        px = draft.reference_price_usd
        if not isinstance(px, Decimal) or not px.is_finite() or px <= 0:
            raise ValueError("missing original approved reference price")
        if draft.payload["side"] == "buy":
            constraints.check_buy(notional_usd=Decimal(draft.payload["notional"]),
                                  reference_price=px)
        else:
            quantity = Decimal(draft.payload["qty"])
            if (quantity < constraints.minimum_base_qty or
                quantity % constraints.base_trade_step != 0):
                raise PermissionError("sell below venue minimum/step; manual dust policy required")
        baseline = reader.get_holdings(observed_at=at)
        if reader.get_open_orders():
            raise PermissionError("existing external orders: isolated account required")
        # This is a PAPER-only isolated portfolio. All other positions fail the
        # holdings parser. For BUY, use strictly non-marginable cash availability.
        account = reader.get_account()
        available = Decimal(str(account.get("non_marginable_buying_power")))
        if not available.is_finite() or available < 0:
            raise ValueError("invalid nonmargin buying power")
        if draft.payload["side"] == "buy" and (
            baseline.cash_usd < Decimal(draft.payload["notional"]) or
            available < Decimal(draft.payload["notional"])
        ):
            raise PermissionError("insufficient cash-only paper funds")
        self._store.begin_submission(draft, at=at, baseline=baseline)  # COMMIT BEFORE network POST
        try:
            response = self._transport(draft.payload, self._key, self._secret)
            observation = parse_paper_observation(response, draft.client_order_id)
            state = self._store.observe_provider(observation, at=at)
            return PaperSubmissionOutcome(state.stage,
                                          "Broker response recorded; never presume accepted means filled", state)
        except Exception:
            # A POST error/timeout can still mean a successful order at the broker.
            # Deliberately do not retry. Keep pending cash reserved for lookup.
            state = self._store.mark_unknown(draft.client_order_id, at=at)
            return PaperSubmissionOutcome(state.stage,
                                          "UNCERTAIN PAPER POST: look up by client ID before any further action", state)

    def lookup_unknown_once(self, client_order_id: str, *, at: datetime,
                            reader: PaperAlpacaReadClient) -> PaperSubmissionOutcome:
        state = self._store.get(client_order_id)
        if state.stage is not Stage.UNKNOWN_RESULT:
            raise ValueError("lookup recovery requires unknown submission state")
        data = reader.lookup_order(client_order_id)  # paper-host GET, never a new POST
        if data is None:
            return PaperSubmissionOutcome(state.stage,
                                          "Not visible yet: remain UNKNOWN and block all new execution", state)
        observation = parse_paper_observation(data, client_order_id)
        state = self._store.observe_provider(observation, at=at)
        return PaperSubmissionOutcome(state.stage, "Paper provider order recovered by client ID", state)

    def reconcile_terminal_once(self, client_order_id: str, *, at: datetime,
                                reader: PaperAlpacaReadClient) -> PaperSubmissionOutcome:
        """Independent PAPER GETs corroborate terminal order, cash and BTC qty.

        Three-way source evidence is checked inside a single durable DB
        transaction. Any mismatch retains the reservation and blocks execution.
        """
        if (not isinstance(reader, PaperAlpacaReadClient) or
            not compare_digest(reader._paper_key, self._key) or
            not compare_digest(reader._paper_secret, self._secret)):
            raise PermissionError("auditor reader must use the identical PAPER account")
        state = self._store.get(client_order_id)
        if state.stage is not Stage.BROKER_TERMINAL_UNRECONCILED:
            raise ValueError("only terminal, unreconciled paper orders may be audited")
        if reader.get_open_orders():
            raise PermissionError("unexpected open broker order prevents isolated audit")
        order = reader.lookup_order(client_order_id)
        if order is None:
            raise ValueError("terminal paper order absent from independent provider lookup")
        latest_observation = parse_paper_observation(order, client_order_id)
        if (latest_observation.broker_order_id != state.broker_order_id or
            latest_observation.provider_status != state.provider_status or
            latest_observation.cumulative_filled_qty != state.cumulative_filled_qty or
            latest_observation.filled_avg_price != state.filled_avg_price):
            raise ValueError("broker terminal order changed; keep reservation")
        post = reader.get_holdings(observed_at=at)
        new_state = self._store.finish_reconciliation(client_order_id, at=at,
                                                       post=post, provider_order=order)
        return PaperSubmissionOutcome(new_state.stage,
                                      "Independent paper order/cash/quantity evidence reconciled", new_state)

    def poll_known_once(self, client_order_id: str, *, at: datetime,
                        reader: PaperAlpacaReadClient) -> PaperSubmissionOutcome:
        """Reconcile an already-seen accepted/partial order; no order POST here."""
        state = self._store.get(client_order_id)
        if state.stage not in (Stage.BROKER_ACCEPTED, Stage.PARTIALLY_FILLED):
            raise ValueError("only known nonterminal broker orders may be polled")
        data = reader.lookup_order(client_order_id)
        if data is None:
            return PaperSubmissionOutcome(state.stage,
                                          "Previously observed order missing in lookup: halt, retain reserves", state)
        state = self._store.observe_provider(parse_paper_observation(data, client_order_id), at=at)
        return PaperSubmissionOutcome(state.stage,
                                      "Provider status updated; terminal still requires audit", state)
