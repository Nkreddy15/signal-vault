"""Explicit READ-ONLY preview for a future supervised $15 BTC/USD PAPER smoke.

NO strategy orders, no broker POST/cancel, no journal writes, no order ID,
no draft creation, no live host, no LaunchAgent modification. Never interpret
a successful preview as authorization to submit an order. The result is valid
only at its checked UTC time; any eventual separately approved smoke needs
fresh quote/account/venue/Guardian preflight immediately before POST.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .alpaca_paper import PaperAlpacaReadClient, _NoRedirects
from .market_data import (
    CRYPTO_LATEST_QUOTES_ENDPOINT, AlpacaAuthenticatedLatestQuote, CryptoQuote,
)
from .operator_view import read_local_paper_snapshot
from .preflight import inspect_paper_runtime
from .read_retry import retry_read
from .venue_rules import CryptoVenueRules

AMOUNT = Decimal("15.00")
MAX_QUOTE_AGE = timedelta(seconds=90)
MAX_SPREAD_BPS = Decimal("50")
_QUOTE_URL = CRYPTO_LATEST_QUOTES_ENDPOINT + "?" + urlencode({"symbols": "BTC/USD"})


def _strict_latest_quote_get(url: str, key: str, secret: str) -> Mapping[str, object]:
    """Only the exact quote DATA GET; reject redirects before credentials follow."""
    if url != _QUOTE_URL or not key.strip() or not secret.strip():
        raise ValueError("latest quote request outside immutable GET-only allowlist")
    req = Request(url, method="GET", headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json", "User-Agent": "SignalVault/paper-smoke-preview",
    })
    def once() -> bytes:
        with build_opener(_NoRedirects).open(req, timeout=12) as response:
            return response.read(1_000_001)
    raw = retry_read(once)
    if len(raw) > 1_000_000:
        raise ValueError("quote response too large")
    result = json.loads(raw)
    if not isinstance(result, Mapping):
        raise ValueError("latest quote must be a mapping")
    return result


def _quote_client(key: str, secret: str) -> AlpacaAuthenticatedLatestQuote:
    return AlpacaAuthenticatedLatestQuote(key, secret, transport=_strict_latest_quote_get)


def _usd(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("invalid account/ledger decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid account/ledger decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("nonfinite or negative account/ledger decimal")
    return result


def _valid_local(local: object, snapshot: object) -> bool:
    if not isinstance(local, Mapping) or not isinstance(snapshot, Mapping):
        return False
    if (local.get("status") != "READ_ONLY_PREFLIGHT_OK"
            or local.get("mode") != "ALPACA_PAPER_ONLY"
            or local.get("paper_order_post_enabled") is not False
            or local.get("authenticated_provider_read_performed") is not False
            or local.get("live_trading_available") is not False
            or local.get("sqlite_wal") is not True
            or local.get("operator_halted") is not False
            or local.get("provider_lookup_required") is not False
            or type(local.get("unresolved_paper_orders")) is not int
            or local["unresolved_paper_orders"] != 0):
        return False
    if (snapshot.get("source") != "LOCAL_SQLITE_LEDGER_NOT_LIVE_MARKET_DATA"
            or snapshot.get("mode") != "ALPACA_PAPER_ONLY"
            or snapshot.get("operator_halted") is not False):
        return False
    ledger = snapshot.get("logical")
    orders = snapshot.get("paper_orders")
    if not isinstance(ledger, Mapping) or not isinstance(orders, Mapping):
        return False
    if type(orders.get("count")) is not int or orders["count"] != 0:
        return False
    if type(orders.get("unresolved")) is not int or orders["unresolved"] != 0:
        return False
    # This preview covers the very FIRST paper smoke only, never a replay over
    # an account with preexisting exposure/drafts/reservations.
    try:
        return (_usd(ledger.get("cash_usd")) == Decimal("100")
                and _usd(ledger.get("btc_qty")) == 0
                and _usd(ledger.get("reserved_usd")) == 0
                and _usd(ledger.get("unreserved_cash_usd")) == Decimal("100"))
    except ValueError:
        return False


def _validate_quote(quote: object, *, now: datetime) -> CryptoQuote:
    # Enforce locally even if an injected quote provider bypasses parser.
    if (not isinstance(quote, CryptoQuote) or quote.symbol != "BTC/USD"
            or not isinstance(quote.bid, Decimal) or not isinstance(quote.ask, Decimal)
            or not quote.bid.is_finite() or not quote.ask.is_finite()
            or quote.bid <= 0 or quote.ask < quote.bid
            or not isinstance(quote.timestamp, datetime)
            or quote.timestamp.tzinfo is None or quote.timestamp.utcoffset() is None):
        raise ValueError("unverified BTC/USD quote")
    age = now.astimezone(timezone.utc) - quote.timestamp.astimezone(timezone.utc)
    if age < timedelta(seconds=-2) or age > MAX_QUOTE_AGE:
        raise ValueError("quote outside current freshness window")
    if quote.spread_bps > MAX_SPREAD_BPS:
        raise ValueError("quote spread outside supervised smoke envelope")
    return quote


def preview_supervised_smoke(
    *,
    db: str | Path = "data/signal-vault-paper.sqlite3",
    now: datetime | None = None,
    local_reader: Callable[..., object] = inspect_paper_runtime,
    snapshot_reader: Callable[..., object] = read_local_paper_snapshot,
    credential_loader: Callable[[], object] | None = None,
    paper_factory: Callable[..., object] = PaperAlpacaReadClient,
    quote_factory: Callable[..., object] = _quote_client,
) -> dict[str, object]:
    """Explicit preview. No persistent draft or broker mutation is possible."""
    result: dict[str, object] = {
        "kind": "SUPERVISED_PAPER_SMOKE_GET_ONLY_PREVIEW",
        "status": "BLOCKED",
        "reason_code": "NOT_CHECKED",
        "failure_class": None,
        "instrument": "BTC/USD",
        "hypothetical_market_buy_notional_usd": "15.00",
        "local_ledger_read": False,
        "paper_provider_get_attempted": False,
        "quote_data_get_attempted": False,
        "draft_created": False,
        "order_id_created": False,
        "local_journal_modified": False,
        "automatic_collector_modified": False,
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "credential_source": "OWNER_KEYCHAIN_ONLY_AFTER_LOCAL_PRECHECK",
        "warning": (
            "Ephemeral market-data preview, NOT a trade instruction, persistent "
            "approval, fee/fill guarantee or consent to submit a PAPER POST."
        ),
    }
    stamp = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(stamp, datetime) or stamp.tzinfo is None
            or stamp.utcoffset() is None):
        result["reason_code"] = "INVALID_CLOCK"
        return result

    try:
        local = local_reader(db)
        snapshot = snapshot_reader(db)
    except Exception as exc:
        result["reason_code"] = "LOCAL_LEDGER_PREFLIGHT_UNAVAILABLE"
        result["failure_class"] = type(exc).__name__
        return result
    result["local_ledger_read"] = True
    if not _valid_local(local, snapshot):
        result["reason_code"] = "LOCAL_LEDGER_NOT_EMPTY_CLEAN_INITIAL_100_USD"
        return result

    if credential_loader is None:
        from .unattended_forward_cycle import load_keychain_paper_data_credentials
        credential_loader = load_keychain_paper_data_credentials
    try:
        credentials = credential_loader()
        key, secret = credentials.key_id, credentials.secret_key
        if (not isinstance(key, str) or not isinstance(secret, str)
                or not key.strip() or not secret.strip()):
            raise ValueError("invalid local credentials")
    except Exception as exc:
        result["reason_code"] = "LOCAL_PAPER_KEYCHAIN_UNAVAILABLE"
        result["failure_class"] = type(exc).__name__
        return result

    try:
        reader = paper_factory(key, secret)
        result["paper_provider_get_attempted"] = True
        account = reader.get_account()
        asset = reader.get_btc_asset()
        positions = reader.get_positions()
        orders = reader.get_open_orders()
        rules = CryptoVenueRules.from_asset(asset)
    except Exception as exc:
        result["reason_code"] = "PAPER_PROVIDER_GET_OR_ASSET_RULES_FAILED"
        result["failure_class"] = type(exc).__name__
        return result

    try:
        power = _usd(account.get("non_marginable_buying_power"))
        if (str(account.get("status", "")).upper() != "ACTIVE"
                or account.get("trading_blocked") is not False
                or power < AMOUNT):
            result["reason_code"] = "PAPER_ACCOUNT_BLOCKED_OR_INSUFFICIENT_BUYING_POWER"
            return result
        if positions or orders:
            result["reason_code"] = "PROVIDER_ACCOUNT_NOT_EMPTY"
            return result
    except Exception as exc:
        result["reason_code"] = "PAPER_ACCOUNT_STATE_INVALID"
        result["failure_class"] = type(exc).__name__
        return result

    try:
        quotes = quote_factory(key, secret)
        result["quote_data_get_attempted"] = True
        quote = _validate_quote(
            quotes.latest_btc_usd(as_of=stamp, max_age_seconds=90,
                                  max_spread_bps=MAX_SPREAD_BPS),
            now=stamp,
        )
        rules.validate_buy_notional(AMOUNT, quote.ask)
        minimum = rules.minimum_notional_at(quote.ask)
    except Exception as exc:
        result["reason_code"] = "QUOTE_OR_DYNAMIC_VENUE_MINIMUM_FAILED"
        result["failure_class"] = type(exc).__name__
        return result

    # Useful for reviewing a hypothetical diagnostic order; no client order ID,
    # no order payload, and no reservation or state transition exists.
    result.update({
        "status": "BASIC_SMOKE_PREVIEW_PASSED_NO_ORDER",
        "reason_code": "NONE",
        "checked_utc": stamp.astimezone(timezone.utc).isoformat(),
        "quote_utc": quote.timestamp.astimezone(timezone.utc).isoformat(),
        "reference_ask_usd": str(quote.ask),
        "spread_bps": str(quote.spread_bps),
        "provider_minimum_usd_at_reference_ask": str(minimum),
        "paper_order_post_attempted": False,
        "requires_separate_supervised_order_authorization": True,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Owner-initiated read-only $15 PAPER smoke preview. NEVER an order.")
    parser.add_argument("--preview", action="store_true", required=True)
    parser.add_argument("--db", default="data/signal-vault-paper.sqlite3")
    args = parser.parse_args(argv)
    result = preview_supervised_smoke(db=args.db)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "BASIC_SMOKE_PREVIEW_PASSED_NO_ORDER" else 2


if __name__ == "__main__":
    raise SystemExit(main())
