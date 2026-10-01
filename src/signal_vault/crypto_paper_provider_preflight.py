"""Fresh GET-only Alpaca PAPER preflight persisted before crypto pilot submission.

This is deliberately first-pilot conservative: the provider PAPER account must
be active/unblocked and empty of positions/open orders. Provider BTC/USD venue
constraints must be present. Only bounded non-secret fields are persisted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Protocol

from .crypto_paper_executor_draft import KIND as PREPARED_KIND
from .multimarket_execution_journal import MultiMarketExecutionJournal
from .venue_rules import CryptoVenueRules


KIND="CRYPTO_ALPACA_PAPER_PROVIDER_PREFLIGHT_PERSISTED_NOT_ORDER_AUTHORIZATION"


class CryptoPaperPreflightReader(Protocol):
    def get_account(self)->Mapping[str,object]: ...
    def get_btc_asset(self)->Mapping[str,object]: ...
    def get_positions(self)->tuple[Mapping[str,object],...]: ...
    def get_open_orders(self)->tuple[Mapping[str,object],...]: ...


def _nonnegative_decimal(raw:object, *, name:str)->Decimal:
    try:
        value=Decimal(str(raw))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not value.is_finite() or value<0:
        raise ValueError(f"invalid {name}")
    return value


def capture_crypto_paper_provider_preflight(
    prepared:Mapping[str,object],
    *,
    journal:MultiMarketExecutionJournal,
    reader:CryptoPaperPreflightReader,
    at:datetime,
    refresh_existing:bool=False,
)->dict[str,object]:
    if (
        not isinstance(prepared,Mapping)
        or prepared.get("kind")!=PREPARED_KIND
        or prepared.get("status")!="DURABLE_CRYPTO_PAPER_DRAFT_APPROVED_NOT_SUBMITTED"
        or prepared.get("market_lane")!="crypto"
        or prepared.get("provider_post_attempted") is not False
        or prepared.get("paper_executor_invoked") is not False
        or prepared.get("paper_order_submission")!="DISABLED"
        or prepared.get("live_trading")!="UNAVAILABLE"
    ):
        raise ValueError("valid persisted crypto PAPER draft receipt required")
    client_id=prepared.get("decision_id")
    if not isinstance(client_id,str) or not client_id:
        raise ValueError("prepared crypto PAPER decision id required")
    draft=journal.get_approved_draft(client_id)
    if (
        draft.market_lane!="crypto"
        or draft.instrument!="BTC/USD"
        or draft.instrument!=prepared.get("instrument")
        or draft.payload_sha256!=prepared.get("payload_sha256")
    ):
        raise ValueError("durable crypto PAPER draft mismatch")

    account=reader.get_account()
    if not isinstance(account,Mapping):
        raise ValueError("Alpaca PAPER account response must be mapping")
    if str(account.get("status","")).upper()!="ACTIVE":
        raise PermissionError("Alpaca PAPER account is not active")
    if account.get("trading_blocked") is not False:
        raise PermissionError("Alpaca PAPER account trading is not confirmed unblocked")
    buying_power=_nonnegative_decimal(
        account.get("non_marginable_buying_power"),
        name="Alpaca PAPER non-marginable buying power",
    )

    asset=reader.get_btc_asset()
    rules=CryptoVenueRules.from_asset(asset)
    positions=reader.get_positions()
    open_orders=reader.get_open_orders()
    if positions:
        raise PermissionError(
            "first autonomous crypto PAPER pilot requires empty provider positions"
        )
    if open_orders:
        raise PermissionError(
            "first autonomous crypto PAPER pilot requires zero provider open orders"
        )

    receipt={
        "kind":KIND,
        "captured_at_utc":at.astimezone(timezone.utc).isoformat(),
        "decision_id":client_id,
        "market_lane":"crypto",
        "instrument":"BTC/USD",
        "environment":"alpaca_paper",
        "account_active":True,
        "trading_blocked":False,
        "provider_positions_count":0,
        "provider_open_orders_count":0,
        "non_marginable_buying_power_usd":str(buying_power),
        "venue_rules":{
            "symbol":rules.symbol,
            "min_order_size":str(rules.min_order_size),
            "min_trade_increment":str(rules.min_trade_increment),
            "price_increment":str(rules.price_increment),
        },
        "draft_payload_sha256":draft.payload_sha256,
        "provider_reads":[
            "GET_ACCOUNT",
            "GET_BTC_ASSET",
            "GET_POSITIONS",
            "GET_OPEN_ORDERS",
        ],
        "credential_values_persisted":False,
        "provider_account_id_persisted":False,
        "provider_post_attempted":False,
        "paper_order_submission":"DISABLED",
        "live_order_submission":"UNAVAILABLE",
        "live_trading":"UNAVAILABLE",
        "preflight_is_not_order_authorization":True,
    }
    if refresh_existing:
        sha=journal.refresh_provider_preflight(client_id,receipt,at=at)
        status="FRESH_PROVIDER_PREFLIGHT_REFRESHED"
    else:
        sha=journal.record_provider_preflight(client_id,receipt,at=at)
        status="FRESH_PROVIDER_PREFLIGHT_PERSISTED"
    return {
        **receipt,
        "status":status,
        "receipt_sha256":sha,
        "refresh_existing":refresh_existing,
        "next_action":"REVALIDATE_PREFLIGHT_AT_ONE_SHOT_PAPER_EXECUTOR_BOUNDARY",
    }
