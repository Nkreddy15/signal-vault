"""Alpaca PAPER ACCOUNT read-only client plus non-executable order drafts.

No method in this module submits or cancels orders. Credentials are supplied
explicitly at call time, never imported from an environment live-key variable.
Production URLs cannot be overridden.  Redirects are blocked so credentials
cannot follow a redirect outside the hardcoded paper host.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .domain import PortfolioSnapshot, Side, TradeIntent
from .risk import RiskEngine, RiskLimits
from .read_retry import retry_read
from .venue_rules import CryptoVenueRules

PAPER_ROOT = "https://paper-api.alpaca.markets"
_MIN_NOTIONAL = Decimal("10")
_CLIENT_ID = re.compile(r"^[a-zA-Z0-9_-]{1,48}$")
_BROKER_ORDER_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("paper API redirects refused to protect credentials")


def _get_paper_json(path: str, key: str, secret: str) -> object:
    fixed = path in ("/v2/account", "/v2/assets/BTC%2FUSD", "/v2/positions", "/v2/orders?status=open")
    lookup = re.fullmatch(r"/v2/orders:by_client_order_id\?client_order_id=[a-zA-Z0-9_-]{1,48}", path)
    fills = re.fullmatch(r"/v2/account/activities/FILL\?order_id=[0-9a-fA-F-]{36}", path)
    fees = re.fullmatch(r"/v2/account/activities/(?:CFEE|FEE)\?order_id=[0-9a-fA-F-]{36}", path)
    if not (fixed or lookup or fills or fees):
        raise ValueError("non-allowlisted paper account read")
    req = Request(PAPER_ROOT + path, method="GET", headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json", "User-Agent": "SignalVault/0.2"})
    def read_once() -> bytes:
        with build_opener(_NoRedirects).open(req, timeout=12) as response:
            return response.read(1_000_001)
    try:
        raw = retry_read(read_once)
    except HTTPError as exc:
        if exc.code == 404 and path.startswith("/v2/orders:by_client_order_id"):
            return {"found": False}
        raise  # no secret-bearing error body logged
    if len(raw) > 1_000_000:
        raise ValueError("paper response too large")
    result = json.loads(raw)
    if not isinstance(result, (dict, list)):
        raise ValueError("invalid paper response type")
    return result


class PaperAlpacaReadClient:
    """Read-only and hardcoded to the PAPER host, no transfer/order endpoints."""
    def __init__(self, paper_key: str, paper_secret: str,
                 transport: Callable[[str, str, str], object] = _get_paper_json):
        if not paper_key.strip() or not paper_secret.strip():
            raise ValueError("separate paper credentials required")
        self._paper_key, self._paper_secret = paper_key, paper_secret
        self._transport = transport

    def get_account(self) -> Mapping[str, object]:
        value = self._transport("/v2/account", self._paper_key, self._paper_secret)
        if not isinstance(value, Mapping) or "equity" not in value:
            raise ValueError("malformed paper account response")
        return value

    def get_btc_asset(self) -> Mapping[str, object]:
        value = self._transport("/v2/assets/BTC%2FUSD", self._paper_key, self._paper_secret)
        if (not isinstance(value, Mapping) or value.get("symbol") != "BTC/USD" or
            value.get("class") != "crypto" or value.get("status") != "active" or
            value.get("tradable") is not True or value.get("fractionable") is not True):
            raise ValueError("BTC/USD paper asset not confirmed tradable")
        return value

    def get_btc_rules(self) -> CryptoVenueRules:
        """Return provider-reported dynamic BTC/USD order constraints.

        Missing fields fail closed; no hardcoded fallback is permitted at the
        authenticated paper-order boundary.
        """
        return CryptoVenueRules.from_asset(self.get_btc_asset())

    def lookup_order(self, client_order_id: str) -> Mapping[str, object] | None:
        if not _CLIENT_ID.fullmatch(client_order_id):
            raise ValueError("unsafe client-order ID")
        value = self._transport("/v2/orders:by_client_order_id?client_order_id=" +
                                quote(client_order_id, safe=""),
                                self._paper_key, self._paper_secret)
        if not isinstance(value, Mapping):
            raise ValueError("invalid paper lookup result")
        if value.get("found") is False:
            return None
        if value.get("client_order_id") != client_order_id:
            raise ValueError("provider lookup ID does not match query")
        return value


    def get_positions(self) -> tuple[Mapping[str, object], ...]:
        value = self._transport("/v2/positions", self._paper_key, self._paper_secret)
        if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
            raise ValueError("malformed paper positions response")
        return tuple(value)

    def get_open_orders(self) -> tuple[Mapping[str, object], ...]:
        value = self._transport("/v2/orders?status=open", self._paper_key, self._paper_secret)
        if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
            raise ValueError("malformed paper open-orders response")
        return tuple(value)

    def get_fill_activities(self, broker_order_id: str) -> tuple[Mapping[str, object], ...]:
        if not _BROKER_ORDER_ID.fullmatch(broker_order_id):
            raise ValueError("unsafe provider order ID")
        path = "/v2/account/activities/FILL?order_id=" + broker_order_id
        value = self._transport(path, self._paper_key, self._paper_secret)
        if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
            raise ValueError("malformed paper fill activities response")
        return tuple(value)

    def get_fee_activities(self, broker_order_id: str) -> tuple[Mapping[str, object], ...]:
        """Read only CFEE/FEE activities filtered by the provider order UUID.

        Alpaca documents crypto fees as potentially posted end-of-day, so an
        empty result is never interpreted as a confirmed zero fee.
        """
        if not _BROKER_ORDER_ID.fullmatch(broker_order_id):
            raise ValueError("unsafe provider order ID")
        items: list[Mapping[str, object]] = []
        for activity_type in ("CFEE", "FEE"):
            path = f"/v2/account/activities/{activity_type}?order_id={broker_order_id}"
            value = self._transport(path, self._paper_key, self._paper_secret)
            if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
                raise ValueError("malformed paper fee activities response")
            items.extend(value)
        return tuple(items)

    def readiness(self) -> "PaperReadiness":
        """Read-only gate: never use default simulated broker balance as our $100 cap."""
        account = self.get_account()
        asset = self.get_btc_asset()
        try:
            CryptoVenueRules.from_asset(asset)
        except ValueError as exc:
            raise ValueError("provider BTC/USD trading constraints unavailable") from exc
        positions = self.get_positions()
        open_orders = self.get_open_orders()
        problems: list[str] = []
        if str(account.get("status", "")).upper() != "ACTIVE":
            problems.append("paper account not active")
        if account.get("trading_blocked") is not False:
            problems.append("paper account trading status not confirmed unblocked")
        if positions:
            problems.append("account has pre-existing positions; cannot assume empty test portfolio")
        if open_orders:
            problems.append("account has existing open orders; cannot assume empty test portfolio")
        try:
            power = Decimal(str(account["non_marginable_buying_power"]))
            if not power.is_finite() or power < 0:
                raise ValueError
        except (KeyError, ValueError, TypeError, ArithmeticError):
            problems.append("invalid non-marginable buying power")
        return PaperReadiness(not problems, tuple(problems), logical_cap_usd=Decimal("100"))



@dataclass(frozen=True)
class PaperReadiness:
    ready: bool
    reasons: tuple[str, ...]
    logical_cap_usd: Decimal



@dataclass(frozen=True)
class PaperOrderDraft:
    """Approval to RECORD an intended order, NOT permission to send it to Alpaca."""
    client_order_id: str
    payload: Mapping[str, str]
    note: str = "DRAFT ONLY: no order submission implemented in this module"


def build_non_executable_draft(intent: TradeIntent, portfolio: PortfolioSnapshot, *,
                               checked_at: datetime, reference_price: Decimal,
                               full_sell_quantity: Decimal | None = None,
                               risk_engine: RiskEngine | None = None) -> PaperOrderDraft:
    """Reject unsupported/minimum-violating requests without scaling trade size.

    A sell must be the known provider-confirmed quantity of the held position;
    estimated USD notional alone is not sufficient for an actual crypto sell.
    """
    risk = risk_engine or RiskEngine(RiskLimits(max_single_buy_usd=Decimal("15"),
                                                 max_total_long_exposure_usd=Decimal("30")))
    if intent.side is Side.BUY and intent.notional_usd.is_finite() and intent.notional_usd != intent.notional_usd.quantize(Decimal("0.01")):
        raise ValueError("USD order must use exact cent precision; no hidden rounding")
    decision = risk.evaluate(intent, portfolio, now=checked_at)
    if not decision.approved:
        raise PermissionError(f"Guardian rejected: {decision.reasons}")
    if not _CLIENT_ID.fullmatch(intent.client_order_id):
        raise ValueError("unsafe client-order ID")
    if (not isinstance(reference_price, Decimal) or not reference_price.is_finite() or
        reference_price <= 0):
        raise ValueError("invalid source-verified price")
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("timezone-aware screening time required")
    if intent.side is Side.BUY:
        if intent.notional_usd < _MIN_NOTIONAL:
            raise ValueError("BTC/USD USD order below estimated $10 venue minimum")
        cents = Decimal("0.01")
        if intent.notional_usd != intent.notional_usd.quantize(cents):
            raise ValueError("USD order must use exact cent precision; no hidden rounding")
        payload = {"symbol": "BTC/USD", "side": "buy", "type": "market", "time_in_force": "gtc",
                   "notional": str(intent.notional_usd), "client_order_id": intent.client_order_id}
    elif intent.side is Side.SELL:
        qty = full_sell_quantity
        if (not isinstance(qty, Decimal) or not qty.is_finite() or qty <= 0 or
            qty.as_tuple().exponent < -9):
            raise ValueError("sell requires provider-confirmed quantity, max 9 decimal places")
        if qty * reference_price < _MIN_NOTIONAL:
            raise ValueError("held position below estimated venue sell minimum; manual review")
        if abs(qty * reference_price - intent.notional_usd) > Decimal("0.05"):
            raise ValueError("sell estimate does not reconcile to provider quantity and price")
        payload = {"symbol": "BTC/USD", "side": "sell", "type": "market", "time_in_force": "gtc",
                   "qty": format(qty, "f"), "client_order_id": intent.client_order_id}
    else:
        raise ValueError("unsupported crypto side")
    return PaperOrderDraft(intent.client_order_id, payload)
