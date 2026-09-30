"""Strict Kalshi public/demo GET-only market-data request builder.

No credentials, signatures, POST/PUT/PATCH/DELETE methods, or order endpoints
are represented here. Network execution belongs to a later adapter and must
keep the same allowlist semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlsplit

PRODUCTION_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"
_ALLOWED_HOSTS = {"api.elections.kalshi.com", "demo-api.kalshi.co"}
_ALLOWED_COLLECTIONS = {"markets", "events", "series", "trades"}


@dataclass(frozen=True)
class PublicKalshiRequest:
    method: str
    url: str
    environment: str
    credentials_required: bool = False
    order_submission: str = "DISABLED"

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "url": self.url,
            "environment": self.environment,
            "credentials_required": self.credentials_required,
            "order_submission": self.order_submission,
        }


def _base(environment: str) -> str:
    if environment == "production":
        return PRODUCTION_BASE
    if environment == "demo":
        return DEMO_BASE
    raise ValueError("Kalshi environment must be demo or production")


def public_collection_request(
    collection: str,
    *,
    environment: str = "demo",
    params: dict[str, str | int] | None = None,
) -> PublicKalshiRequest:
    if collection not in _ALLOWED_COLLECTIONS:
        raise ValueError("Kalshi public collection is not allowlisted")
    query = urlencode(params or {}, doseq=False)
    url = f"{_base(environment)}/{collection}"
    if query:
        url += "?" + query
    _validate_get_url(url)
    return PublicKalshiRequest("GET", url, environment)


def public_market_request(
    market_ticker: str,
    *,
    environment: str = "demo",
) -> PublicKalshiRequest:
    ticker = market_ticker.strip()
    if not ticker or len(ticker) > 128 or any(c.isspace() for c in ticker):
        raise ValueError("invalid Kalshi market ticker")
    url = f"{_base(environment)}/markets/{quote(ticker, safe='-._')}"
    _validate_get_url(url)
    return PublicKalshiRequest("GET", url, environment)


def _validate_get_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _ALLOWED_HOSTS
        or not parsed.path.startswith("/trade-api/v2/")
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Kalshi GET URL escaped strict public/demo allowlist")


def safety_snapshot() -> dict[str, object]:
    return {
        "kind": "KALSHI_PUBLIC_DATA_ADAPTER_FOUNDATION",
        "allowed_http_methods": ["GET"],
        "allowed_hosts": sorted(_ALLOWED_HOSTS),
        "credentials_required": False,
        "request_signing": "NOT_IMPLEMENTED",
        "paper_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
    }
