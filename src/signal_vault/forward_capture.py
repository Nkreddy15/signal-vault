"""Explicit operator-invoked READ-ONLY fresh BTC/USD capture for the forward journal.

One fixed Alpaca crypto DATA GET endpoint, no broker trading account, POST,
order drafts, daemon, scheduled execution, or persisted API keys. Terminal
prompts hide both paper DATA key fields; never send them to chat or GitHub.
"""
from __future__ import annotations

import getpass
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .data_capture import HistoricalBarsProvider, DatasetManifest, capture_dataset
from .market_data import AlpacaAuthenticatedCryptoBars, CRYPTO_BARS_ENDPOINT
from .read_retry import retry_read

WINDOW_HOURS = 72
CAPTURE_FOLDER = Path("data/forward/captures")


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect refused to protect local data credentials")


def _read_data_get_no_redirect(url: str, key: str, secret: str) -> dict:
    """Allow only the exact historical-data HTTPS host/path and expected GET query."""
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, strict_parsing=True)
    required = {"symbols", "timeframe", "start", "end", "limit", "sort"}
    if (parsed.scheme != "https" or parsed.netloc != "data.alpaca.markets"
            or parsed.path != "/v1beta3/crypto/us/bars" or parsed.fragment
            or not required.issubset(query)
            or set(query) - (required | {"page_token"})
            or any(len(values) != 1 for values in query.values())
            or query["symbols"] != ["BTC/USD"] or query["timeframe"] != ["1Hour"]
            or query["limit"] != ["1000"] or query["sort"] != ["asc"]
            or not key.strip() or not secret.strip()):
        raise ValueError("historical data GET outside strict allowlist")
    req = Request(url, method="GET", headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json", "User-Agent": "SignalVault/forward-read-only",
    })
    def once():
        with build_opener(_RejectRedirects).open(req, timeout=12) as response:
            return response.read(4_000_001)
    raw = retry_read(once)
    if len(raw) > 4_000_000:
        raise ValueError("provider data GET response too large")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("malformed historical data JSON")
    return payload


def default_capture_path(now: datetime) -> Path:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("capture time must be timezone-aware")
    end = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return CAPTURE_FOLDER / f"btcusd_72h_end_{end:%Y%m%dT%H%MZ}.csv"


def capture_current_window(provider: HistoricalBarsProvider, *,
                           now: datetime, output_csv: str | Path | None = None
                           ) -> DatasetManifest:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("capture time must be timezone-aware")
    instant = now.astimezone(timezone.utc)
    end = instant.replace(minute=0, second=0, microsecond=0)
    if instant - end < timedelta(minutes=3):
        raise ValueError("wait at least three minutes after the UTC hour for provider candle publication")
    output = Path(output_csv) if output_csv is not None else default_capture_path(instant)
    manifest = output.with_suffix(output.suffix + ".manifest.json")
    # Deliberately never overwrite previously captured raw hourly evidence.
    if output.is_symlink() or manifest.is_symlink() or output.exists() or manifest.exists():
        raise ValueError("capture already exists; previously recorded raw evidence is immutable")
    start = end - timedelta(hours=WINDOW_HOURS)
    result = capture_dataset(
        provider, start=start, end=end, as_of=instant,
        output_csv=output, captured_at=instant,
    )
    if result.row_count != WINDOW_HOURS or result.source != "alpaca_crypto_us":
        raise ValueError("unexpected forward capture count/source")
    return result


def main() -> int:
    print("Signal Vault: explicitly requested Alpaca BTC/USD DATA GET only.")
    print("No paper-order endpoint, live endpoint, funding or trading action is called.")
    key = getpass.getpass("Local Alpaca PAPER key ID (hidden): ")
    secret = getpass.getpass("Local Alpaca PAPER secret (hidden): ")
    if not key.strip() or not secret.strip():
        raise ValueError("local read-only data credentials required")
    provider = AlpacaAuthenticatedCryptoBars(key, secret, transport=_read_data_get_no_redirect)
    now = datetime.now(timezone.utc)
    target = default_capture_path(now)
    result = capture_current_window(provider, now=now, output_csv=target)
    print(json.dumps({
        "kind": "EXPLICIT_OPERATOR_INVOKED_READ_ONLY_DATA_CAPTURE",
        "csv": str(target),
        "manifest": str(target.with_suffix(target.suffix + ".manifest.json")),
        "sha256": result.csv_sha256,
        "first_bar_start": result.start_utc,
        "last_bar_closed": result.end_utc,
        "row_count": result.row_count,
        "broker_order_submission": "DISABLED",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
