"""Bounded, authenticated historical DATA GET for a predeclared multi-asset universe.

This is a separate OFFLINE research client, not imported by Railway's BTC/USD
forward cron or any broker module. NO trading endpoints, POST, account reads,
live host, unbounded pagination, redirects or arbitrary asset/host URLs.
Data returned by Alpaca is HISTORICAL even when downloaded this hour.

Alpaca docs (reviewed 2026-09-29):
  crypto: https://data.alpaca.markets/v1beta3/crypto/us/bars
  stocks: https://data.alpaca.markets/v2/stocks/bars
Multi-symbol pages have a TOTAL row limit, not a per-symbol row limit; a
single page may contain only the first symbol. Always consume next_page_token.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener

from .forward_capture import _RejectRedirects
from .read_retry import retry_read
from .research_universe import (
    AssetClass, CandidateAsset, ResearchBar, candidate, validate_asset_dataset,
)

CRYPTO_ENDPOINT = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
EQUITY_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
PAGE_LIMIT = 1000
MAX_PAGES = 40
MAX_SYMBOLS = 6
MAX_WINDOW_HOURS = 24 * 14
MAX_RESPONSE_BYTES = 6_000_000


def _utc(ts: datetime) -> datetime:
    if not isinstance(ts, datetime) or ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("UTC-aware query timestamp required")
    return ts.astimezone(timezone.utc)


def _price(raw: object, label: str, *, allow_zero: bool = False) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, float, int, Decimal)):
        raise ValueError("missing/invalid " + label)
    try:
        value = Decimal(str(raw))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("invalid " + label) from exc
    if not value.is_finite() or (value < 0 if allow_zero else value <= 0):
        raise ValueError("negative/zero/nonfinite " + label)
    return value


def _read_historical_data_no_redirect(url: str, key: str, secret: str) -> Mapping[str, object]:
    """Enforce exact DATA-only host and two fixed paths BEFORE attaching keys."""
    p = urlsplit(url)
    q = parse_qs(p.query, strict_parsing=True)
    if (p.scheme != "https" or p.netloc != "data.alpaca.markets" or
            p.path not in (
                "/v1beta3/crypto/us/bars", "/v2/stocks/bars") or
            p.fragment or p.username or p.password or
            not key.strip() or not secret.strip()):
        raise ValueError("unauthorized research data URL or credentials")
    required = {"symbols", "timeframe", "start", "end", "limit", "sort"}
    optional = ({"page_token", "feed", "adjustment"} if p.path == "/v2/stocks/bars"
                else {"page_token"})
    if (not required.issubset(q) or set(q) - required - optional or
            any(len(vals) != 1 for vals in q.values()) or
            q["timeframe"] != ["1Hour"] or q["limit"] != [str(PAGE_LIMIT)]
            or q["sort"] != ["asc"]):
        raise ValueError("non-allowlisted multi-asset data query")
    symbols = q["symbols"][0].split(",")
    if (not 1 <= len(symbols) <= MAX_SYMBOLS or
            len(symbols) != len(set(symbols)) or
            any(candidate(sym).asset_class != (
                AssetClass.CRYPTO if p.path == "/v1beta3/crypto/us/bars"
                else AssetClass.US_EQUITY) for sym in symbols)):
        raise ValueError("unapproved multi-asset research symbols")
    if p.path == "/v2/stocks/bars" and (
            q.get("feed") not in (["iex"], ["sip"]) or
            q.get("adjustment") != ["all"]):
        raise ValueError("explicit equity feed/adjustment required")
    if "page_token" in q and (not q["page_token"][0] or len(q["page_token"][0]) > 512):
        raise ValueError("invalid pagination token")
    # Validate bounds rather than permitting arbitrary client-crafted query.
    try:
        start = _utc(datetime.fromisoformat(q["start"][0]))
        inclusive_end = _utc(datetime.fromisoformat(q["end"][0]))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid data query bounds") from exc
    if not start < inclusive_end < start + timedelta(hours=MAX_WINDOW_HOURS + 1):
        raise ValueError("research GET interval outside time cap")
    request = Request(url, method="GET", headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
        "User-Agent": "SignalVault/research-historical-get-only",
    })
    def once() -> bytes:
        with build_opener(_RejectRedirects).open(request, timeout=12) as response:
            return response.read(MAX_RESPONSE_BYTES + 1)
    raw = retry_read(once)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("multi-symbol provider page exceeds response limit")
    value = json.loads(raw)
    if not isinstance(value, Mapping):
        raise ValueError("malformed historical provider page")
    return value


@dataclass(frozen=True)
class HistoricalDataBatch:
    """Unambiguous provenance + purely historical candles, never a forward audit."""

    asset_class: str
    symbols: tuple[str, ...]
    feed: str
    adjustment: str
    start_utc: str
    end_utc: str
    downloaded_utc: str
    page_count: int
    bars: Mapping[str, tuple[ResearchBar, ...]]

    def canonical(self) -> dict[str, object]:
        return {
            "kind": "BOUNDED_HISTORICAL_MULTIASSET_DATA_GET_NOT_FORWARD_EVIDENCE",
            "schema_version": 1,
            "asset_class": self.asset_class,
            "symbols": list(self.symbols),
            "feed": self.feed,
            "adjustment": self.adjustment,
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "downloaded_utc": self.downloaded_utc,
            "page_count": self.page_count,
            "bars": {s: [b.to_dict() for b in self.bars[s]] for s in self.symbols},
            "prospective_observations_verified": 0,
            "broker_order_submission": "DISABLED",
            "historical_not_independent_validation": True,
        }

    def canonical_bytes(self) -> bytes:
        return (json.dumps(self.canonical(), separators=(",", ":"), sort_keys=True)
                + "\n").encode("utf-8")


class BoundedAlpacaHistoricalBatch:
    def __init__(
        self, key: str, secret: str,
        *,
        transport: Callable[[str, str, str], Mapping[str, object]] = _read_historical_data_no_redirect,
        max_pages: int = MAX_PAGES,
    ) -> None:
        if (not isinstance(key, str) or not isinstance(secret, str) or
                not key.strip() or not secret.strip()):
            raise ValueError("dedicated PAPER historical DATA credentials required")
        if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES:
            raise ValueError("historical page cap must be bounded")
        self._key = key
        self._secret = secret
        self._transport = transport
        self._max_pages = max_pages

    def fetch(
        self,
        *, specs: Sequence[CandidateAsset], start: datetime, end: datetime,
        as_of: datetime, equity_feed: str | None = None,
        equity_expected_open_minutes: Mapping[str, Sequence[datetime]] | None = None,
    ) -> HistoricalDataBatch:
        items = tuple(specs)
        if not 1 <= len(items) <= MAX_SYMBOLS:
            raise ValueError("request must contain 1-6 predeclared assets")
        if len({a.symbol for a in items}) != len(items):
            raise ValueError("duplicate symbol in research batch")
        if any(candidate(a.symbol) != a for a in items):
            raise ValueError("research batch contains unregistered/enabled asset")
        classes = {a.asset_class for a in items}
        if len(classes) != 1:
            raise ValueError("crypto and equities require separate provider requests")
        category = items[0].asset_class
        start, end, as_of = _utc(start), _utc(end), _utc(as_of)
        if not start < end <= as_of or end - start > timedelta(hours=MAX_WINDOW_HOURS):
            raise ValueError("research history must be fully closed and <=14 days/request")
        if (start.minute or start.second or start.microsecond or
                end.minute or end.second or end.microsecond):
            raise ValueError("request bounds must be whole UTC hours")
        if category == AssetClass.CRYPTO:
            if equity_feed is not None or equity_expected_open_minutes is not None:
                raise ValueError("crypto fetch cannot claim an equity data feed")
            url = CRYPTO_ENDPOINT
            feed, adjustment = "alpaca_crypto_us", "not_applicable"
        else:
            if equity_feed not in ("iex", "sip"):
                raise ValueError("choose an explicitly entitled equity feed (iex or sip)")
            if (equity_expected_open_minutes is None or
                    set(equity_expected_open_minutes) != {a.symbol for a in items}):
                raise ValueError("explicit per-equity-session calendar required")
            url = EQUITY_ENDPOINT
            feed, adjustment = "alpaca_equity_" + equity_feed, "all"
        symbols = tuple(sorted(spec.symbol for spec in items))
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Hour",
            "start": start.isoformat(),
            "end": (end - timedelta(seconds=1)).isoformat(),
            "limit": str(PAGE_LIMIT),
            "sort": "asc",
        }
        if category == AssetClass.US_EQUITY:
            params.update({"feed": equity_feed, "adjustment": adjustment})
        pages = 0
        tokens: set[str] = set()
        by_symbol: dict[str, list[ResearchBar]] = {s: [] for s in symbols}
        while pages < self._max_pages:
            result = self._transport(url + "?" + urlencode(params),
                                     self._key, self._secret)
            pages += 1
            if not isinstance(result, Mapping) or not isinstance(result.get("bars"), Mapping):
                raise ValueError("historical page missing bars mapping")
            incoming = result["bars"]
            if set(incoming) - set(symbols):
                raise ValueError("provider returned unrequested historical symbol")
            for sym, rows in incoming.items():
                if not isinstance(rows, list) or len(rows) > PAGE_LIMIT:
                    raise ValueError("invalid per-symbol provider bar list")
                for row in rows:
                    if not isinstance(row, Mapping):
                        raise ValueError("malformed historical candle")
                    try:
                        at = _utc(datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00")))
                    except (KeyError, ValueError) as exc:
                        raise ValueError("malformed provider bar timestamp") from exc
                    if not start <= at or at + timedelta(hours=1) > end:
                        raise ValueError("provider candle outside closed request interval")
                    bar = ResearchBar(
                        symbol=sym, start_utc=at,
                        open=_price(row.get("o"), "open"),
                        high=_price(row.get("h"), "high"),
                        low=_price(row.get("l"), "low"),
                        close=_price(row.get("c"), "close"),
                        volume=_price(row.get("v"), "volume", allow_zero=True),
                        feed=(feed if category == AssetClass.CRYPTO
                              else feed + "|adjustment=" + adjustment),
                        captured_utc=as_of,
                        prospective=False,
                    )
                    by_symbol[sym].append(bar)
            token = result.get("next_page_token")
            if token in (None, ""):
                break
            if (not isinstance(token, str) or len(token) > 512 or
                    token in tokens):
                raise ValueError("missing/repeated/oversized historical page token")
            tokens.add(token)
            params["page_token"] = token
        else:
            raise ValueError("provider data pagination cap exceeded")

        # The API's total page limit can put each instrument on separate pages.
        # Never infer missing requested symbols from the first response alone.
        for spec in items:
            rows = tuple(by_symbol[spec.symbol])
            if not rows:
                raise ValueError("no requested bars for " + spec.symbol)
            if category == AssetClass.CRYPTO:
                if rows[0].start_utc != start or rows[-1].closed_utc != end:
                    raise ValueError("incomplete crypto historical time window")
            calendar = (None if category == AssetClass.CRYPTO
                        else equity_expected_open_minutes[spec.symbol])
            validate_asset_dataset(
                rows, spec=spec, as_of=as_of,
                expected_session_opens_utc=calendar)
        return HistoricalDataBatch(
            category.value, symbols, feed, adjustment, start.isoformat(),
            end.isoformat(), as_of.isoformat(), pages,
            {sym: tuple(by_symbol[sym]) for sym in symbols},
        )


def archive_historical_batch(
    batch: HistoricalDataBatch, *, output_folder: str | Path,
) -> Path:
    """One atomic, CREATE-only historical archive; no forward-root arguments.

    No overwrite, no shadow signal, no trade permissions. If an archived
    dataset already exists, compare exact content before idempotent reuse.
    """
    if not isinstance(batch, HistoricalDataBatch):
        raise ValueError("batch provenance contract required")
    root = Path(output_folder)
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        raise ValueError("historical archive root must PREEXIST as private 0700 directory")
    # Forbid passing the separate production collector volume in the common
    # host layout. Operator still bears responsibility for other custom paths.
    if root.resolve() == Path("/var/lib/signal-vault/forward"):
        raise ValueError("historical research must not write to the forward evidence root")
    raw = batch.canonical_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    first = datetime.fromisoformat(batch.start_utc)
    last = datetime.fromisoformat(batch.end_utc)
    name = (f"historical-{batch.asset_class}-{first.strftime('%Y%m%dT%H%MZ')}-"
            f"{last.strftime('%Y%m%dT%H%MZ')}-{digest[:16]}.json")
    path = root / name
    if path.exists() or path.is_symlink():
        if (path.is_symlink() or not path.is_file() or
                path.stat().st_mode & 0o077 or path.read_bytes() != raw):
            raise ValueError("immutable historical dataset path collision")
        return path
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return path
