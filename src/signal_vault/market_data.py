"""Strict, source-attributed closed crypto OHLCV bars and a read-only Alpaca feed.

Nothing in this module can access a trading endpoint or place an order.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .read_retry import retry_read


CRYPTO_BARS_ENDPOINT = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
SYMBOL = "BTC/USD"
HOUR = 3600


def utc_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid bar timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("timezone is required")
    return stamp.astimezone(timezone.utc)


def _number(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"invalid {field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite() or (result < 0 if allow_zero else result <= 0):
        raise ValueError(f"non-finite or invalid {field}")
    return result


@dataclass(frozen=True)
class Bar:
    start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str
    timeframe_seconds: int = HOUR
    symbol: str = SYMBOL

    @property
    def close_time(self) -> datetime:
        return self.start + timedelta(seconds=self.timeframe_seconds)


def parse_bar(row: Mapping[str, object], *, source: str, timeframe_seconds: int = HOUR,
              symbol: str = SYMBOL) -> Bar:
    """Accept Alpaca's t/o/h/l/c/v OR named CSV columns, not inferred data."""
    if not source.strip() or symbol != SYMBOL or timeframe_seconds != HOUR:
        raise ValueError("unsupported source, symbol or timeframe")
    fields = {"start": ("t", "timestamp"), "open": ("o", "open"),
              "high": ("h", "high"), "low": ("l", "low"),
              "close": ("c", "close"), "volume": ("v", "volume")}

    def required(name: str) -> object:
        for key in fields[name]:
            if key in row:
                return row[key]
        raise ValueError(f"missing {name}")

    stamp = utc_timestamp(required("start"))
    if stamp.minute or stamp.second or stamp.microsecond:
        raise ValueError("hourly bar timestamp must align to UTC hour")
    bar = Bar(stamp, _number(required("open"), "open"),
              _number(required("high"), "high"), _number(required("low"), "low"),
              _number(required("close"), "close"),
              _number(required("volume"), "volume", allow_zero=True),
              source, timeframe_seconds, symbol)
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.low > bar.high:
        raise ValueError("inconsistent OHLC")
    return bar


def validate_bars(bars: Iterable[Bar], *, as_of: datetime, min_count: int = 1) -> tuple[Bar, ...]:
    """Fail closed on gaps, duplicates and incomplete bars; never silently repair them."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    items = tuple(bars)
    if len(items) < min_count:
        raise ValueError("not enough market data")
    previous: Bar | None = None
    for bar in items:
        if (bar.symbol != SYMBOL or bar.timeframe_seconds != HOUR or
            not bar.source or bar.start.tzinfo is None or
            bar.start.utcoffset() != timedelta(0) or
            bar.start.minute or bar.start.second or bar.start.microsecond):
            raise ValueError("invalid bar metadata")
        for name in ("open", "high", "low", "close"):
            _number(getattr(bar, name), name)
        _number(bar.volume, "volume", allow_zero=True)
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.low > bar.high:
            raise ValueError("inconsistent OHLC")
        if bar.close_time > as_of.astimezone(timezone.utc):
            raise ValueError("open / future bar is not usable for decisions")
        if previous is not None:
            if bar.source != previous.source:
                raise ValueError("mixed data sources cannot be treated as one stream")
            if bar.start != previous.close_time:
                raise ValueError("out-of-order, duplicate or missing hourly bar")
        previous = bar
    return items


def load_csv(path: str | Path, *, as_of: datetime, min_count: int = 1) -> tuple[Bar, ...]:
    """Load an explicit timestamped OHLCV dataset (not evidence of real live performance)."""
    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = csv.DictReader(stream)
        if not rows.fieldnames or not {"timestamp", "open", "high", "low", "close", "volume"}.issubset(rows.fieldnames):
            raise ValueError("CSV requires timestamp,open,high,low,close,volume")
        bars = (parse_bar(row, source="imported_csv") for row in rows)
        return validate_bars(bars, as_of=as_of, min_count=min_count)


def _read_public_json(url: str) -> Mapping[str, object]:
    # Current Alpaca crypto historical-data docs require API authentication.
    # This function remains only as the default for injected/offline research
    # tests and must not silently attempt an unauthenticated production read.
    raise ValueError("authenticated Alpaca crypto historical data client required")


class AlpacaPublicCryptoBars:
    """Offline/injected research adapter retained for deterministic tests.

    Current provider documentation requires authentication, so the default
    transport deliberately fails. Production paper runtime must use
    `AlpacaAuthenticatedCryptoBars` below.
    """

    def __init__(self, fetch_json: Callable[[str], Mapping[str, object]] = _read_public_json,
                 *, max_pages: int = 30) -> None:
        if max_pages < 1 or max_pages > 100:
            raise ValueError("invalid maximum pages")
        self.fetch_json = fetch_json
        self.max_pages = max_pages

    def fetch(self, *, start: datetime, end: datetime, as_of: datetime) -> tuple[Bar, ...]:
        for stamp in (start, end, as_of):
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("UTC-aware fetch boundaries required")
        start, end, as_of = (x.astimezone(timezone.utc) for x in (start, end, as_of))
        if not start < end <= as_of or (start.minute, start.second, start.microsecond) != (0, 0, 0) or (end.minute, end.second, end.microsecond) != (0, 0, 0):
            raise ValueError("request must end on a fully closed UTC-hour boundary")
        # Alpaca documents `end` as inclusive, while our validated dataset uses
        # the half-open interval [start, end). Request one second before the
        # exclusive boundary to avoid admitting the bar starting exactly at `end`.
        # Keep strict row/boundary validation below; never silently discard bars.
        params = {"symbols": SYMBOL, "timeframe": "1Hour", "start": start.isoformat(),
                  "end": (end - timedelta(seconds=1)).isoformat(),
                  "limit": "1000", "sort": "asc"}
        all_bars: list[Bar] = []
        seen_tokens: set[str] = set()
        for _ in range(self.max_pages):
            payload = self.fetch_json(CRYPTO_BARS_ENDPOINT + "?" + urlencode(params))
            if not isinstance(payload, Mapping) or not isinstance(payload.get("bars"), Mapping):
                raise ValueError("missing bars in Alpaca response")
            raw = payload["bars"].get(SYMBOL)
            if not isinstance(raw, list):
                raise ValueError("missing requested BTC/USD bars")
            for row in raw:
                if not isinstance(row, Mapping):
                    raise ValueError("malformed Alpaca candle")
                bar = parse_bar(row, source="alpaca_crypto_us")
                if not start <= bar.start or bar.close_time > end:
                    raise ValueError("provider returned bar outside requested closed interval")
                all_bars.append(bar)
            token = payload.get("next_page_token")
            if token in (None, ""):
                result = validate_bars(all_bars, as_of=as_of)
                if result[0].start != start or result[-1].close_time != end:
                    raise ValueError("market-data interval is incomplete at a boundary")
                return result
            if not isinstance(token, str) or len(token) > 500 or token in seen_tokens:
                raise ValueError("invalid or repeated Alpaca pagination token")
            seen_tokens.add(token)
            params["page_token"] = token
        raise ValueError("market-data pagination exhausted before completion")

CRYPTO_LATEST_QUOTES_ENDPOINT = "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes"


@dataclass(frozen=True)
class CryptoQuote:
    symbol: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime
    source: str = "alpaca_crypto_us_latest_quote"

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread_bps(self) -> Decimal:
        return ((self.ask - self.bid) / self.mid) * Decimal("10000")

    def execution_reference(self, side: str) -> Decimal:
        if side == "buy":
            return self.ask
        if side == "sell":
            return self.bid
        raise ValueError("unsupported quote side")


def parse_latest_crypto_quote(payload: Mapping[str, object], *, as_of: datetime,
                              max_age_seconds: int = 90,
                              max_spread_bps: Decimal = Decimal("50")) -> CryptoQuote:
    """Parse one authenticated latest BTC/USD quote and fail closed on stale/crossed data."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if max_age_seconds < 1 or max_age_seconds > 600:
        raise ValueError("invalid quote freshness bound")
    if not isinstance(max_spread_bps, Decimal) or not max_spread_bps.is_finite() or max_spread_bps <= 0:
        raise ValueError("invalid spread bound")
    quotes = payload.get("quotes")
    if not isinstance(quotes, Mapping) or set(quotes.keys()) != {SYMBOL}:
        raise ValueError("latest quote response must contain exactly BTC/USD")
    raw = quotes[SYMBOL]
    if not isinstance(raw, Mapping):
        raise ValueError("malformed latest BTC/USD quote")
    bid = _number(raw.get("bp"), "bid")
    ask = _number(raw.get("ap"), "ask")
    if ask < bid:
        raise ValueError("crossed crypto quote")
    stamp = utc_timestamp(raw.get("t"))
    now = as_of.astimezone(timezone.utc)
    age = now - stamp
    if age < timedelta(seconds=-2) or age > timedelta(seconds=max_age_seconds):
        raise ValueError("latest crypto quote is stale or future-dated")
    quote = CryptoQuote(SYMBOL, bid, ask, stamp)
    if quote.spread_bps > max_spread_bps:
        raise ValueError("crypto quote spread exceeds safety bound")
    return quote


class AlpacaAuthenticatedLatestQuote:
    """Read-only latest crypto quote client using Alpaca API credentials.

    It has one hard-coded data endpoint and cannot reach trading/order routes.
    Tests inject the transport and perform no network activity.
    """
    def __init__(self, key_id: str, secret_key: str,
                 transport: Callable[[str, str, str], Mapping[str, object]] | None = None) -> None:
        if not key_id.strip() or not secret_key.strip():
            raise ValueError("paper/data credentials required")
        self._key, self._secret = key_id, secret_key
        self._transport = transport or self._read

    @staticmethod
    def _read(url: str, key: str, secret: str) -> Mapping[str, object]:
        expected = CRYPTO_LATEST_QUOTES_ENDPOINT + "?" + urlencode({"symbols": SYMBOL})
        if url != expected:
            raise ValueError("non-allowlisted market-data endpoint")
        request = Request(url, method="GET", headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "User-Agent": "SignalVault/0.3",
        })
        # Deliberately avoid a generic URL argument anywhere else in the runtime.
        def read_once() -> bytes:
            with urlopen(request, timeout=12) as response:
                return response.read(1_000_001)
        raw = retry_read(read_once)
        if len(raw) > 1_000_000:
            raise ValueError("latest quote response too large")
        value = json.loads(raw)
        if not isinstance(value, Mapping):
            raise ValueError("malformed latest quote response")
        return value

    def latest_btc_usd(self, *, as_of: datetime,
                       max_age_seconds: int = 90,
                       max_spread_bps: Decimal = Decimal("50")) -> CryptoQuote:
        url = CRYPTO_LATEST_QUOTES_ENDPOINT + "?" + urlencode({"symbols": SYMBOL})
        payload = self._transport(url, self._key, self._secret)
        if not isinstance(payload, Mapping):
            raise ValueError("malformed latest quote response")
        return parse_latest_crypto_quote(payload, as_of=as_of,
                                         max_age_seconds=max_age_seconds,
                                         max_spread_bps=max_spread_bps)


class AlpacaAuthenticatedCryptoBars(AlpacaPublicCryptoBars):
    """Authenticated read-only historical BTC/USD bars from the fixed data host."""
    def __init__(self, key_id: str, secret_key: str,
                 transport: Callable[[str, str, str], Mapping[str, object]] | None = None,
                 *, max_pages: int = 30) -> None:
        if not key_id.strip() or not secret_key.strip():
            raise ValueError("paper/data credentials required")
        self._key, self._secret = key_id, secret_key
        self._transport = transport or self._read
        super().__init__(fetch_json=self._fetch_authenticated, max_pages=max_pages)

    @staticmethod
    def _read(url: str, key: str, secret: str) -> Mapping[str, object]:
        if not url.startswith(CRYPTO_BARS_ENDPOINT + "?"):
            raise ValueError("historical market-data URL outside allowlist")
        request = Request(url, headers={
            "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json", "User-Agent": "SignalVault/0.3"}, method="GET")
        def read_once() -> bytes:
            with urlopen(request, timeout=12) as response:
                return response.read(4_000_001)
        raw = retry_read(read_once)
        if len(raw) > 4_000_000:
            raise ValueError("market-data response exceeds size limit")
        value = json.loads(raw)
        if not isinstance(value, Mapping):
            raise ValueError("unexpected market-data response")
        return value

    def _fetch_authenticated(self, url: str) -> Mapping[str, object]:
        return self._transport(url, self._key, self._secret)
