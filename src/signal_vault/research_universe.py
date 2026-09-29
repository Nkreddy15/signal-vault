"""Multi-asset OFFLINE research contracts, independent of the live BTC collector.

DOES NOT activate additional Alpaca symbols, market-data calls, paper/live
orders, feed permissions, costs, or cloud deployments. This deliberately avoids
removing the BTC/USD strictness from the production capture and risk engine.

Candidates are RESEARCH TARGETS only; market-data entitlement/tradability,
exchange calendars, provider fees, bid/ask behavior and risk rules must each be
verified before activating an instrument. Equity hours are NOT 24/7.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence

HOUR = timedelta(hours=1)


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    US_EQUITY = "us_equity"


@dataclass(frozen=True)
class CandidateAsset:
    symbol: str
    asset_class: AssetClass
    calendar: str
    venue: str
    # Candidate only. Market-data support and permissions NOT established.
    enabled_for_data_collection: bool = False
    enabled_for_order_submission: bool = False

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.isascii() or len(self.symbol) > 24:
            raise ValueError("invalid research candidate symbol")
        if self.enabled_for_data_collection or self.enabled_for_order_submission:
            raise ValueError("research registry does not activate provider access or trading")
        if self.asset_class == AssetClass.CRYPTO and self.calendar != "24_7_utc":
            raise ValueError("crypto market calendar mismatch")
        if self.asset_class == AssetClass.US_EQUITY and self.calendar != "XNYS":
            raise ValueError("US equity calendar mismatch")


# Deliberate bounded launch set, not a claim all these are available on Alpaca.
# Expand only after provider coverage, data entitlement and cost review.
RESEARCH_CANDIDATES: tuple[CandidateAsset, ...] = (
    CandidateAsset("BTC/USD", AssetClass.CRYPTO, "24_7_utc", "crypto_us"),
    CandidateAsset("ETH/USD", AssetClass.CRYPTO, "24_7_utc", "crypto_us"),
    CandidateAsset("SOL/USD", AssetClass.CRYPTO, "24_7_utc", "crypto_us"),
    CandidateAsset("LTC/USD", AssetClass.CRYPTO, "24_7_utc", "crypto_us"),
    CandidateAsset("LINK/USD", AssetClass.CRYPTO, "24_7_utc", "crypto_us"),
    CandidateAsset("AVAX/USD", AssetClass.CRYPTO, "24_7_utc", "crypto_us"),
    CandidateAsset("SPY", AssetClass.US_EQUITY, "XNYS", "us_equities"),
    CandidateAsset("QQQ", AssetClass.US_EQUITY, "XNYS", "us_equities"),
    CandidateAsset("AAPL", AssetClass.US_EQUITY, "XNYS", "us_equities"),
    CandidateAsset("MSFT", AssetClass.US_EQUITY, "XNYS", "us_equities"),
    CandidateAsset("NVDA", AssetClass.US_EQUITY, "XNYS", "us_equities"),
    CandidateAsset("AMD", AssetClass.US_EQUITY, "XNYS", "us_equities"),
)


def candidate(symbol: str) -> CandidateAsset:
    matches = tuple(spec for spec in RESEARCH_CANDIDATES if spec.symbol == symbol)
    if len(matches) != 1:
        raise ValueError("unknown or undeclared asset research candidate")
    return matches[0]


def _utc(moment: datetime) -> datetime:
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("explicit timezone-aware timestamp required")
    return moment.astimezone(timezone.utc)


def _number(value: object, *, allow_zero: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("research prices/volume must be finite Decimals")
    if (value < 0 if allow_zero else value <= 0):
        raise ValueError("negative/zero price or negative volume")
    return value


@dataclass(frozen=True)
class ResearchBar:
    """Per-asset canonical OHLCV; separate from production's BTC-only Bar."""

    symbol: str
    start_utc: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    feed: str
    captured_utc: datetime
    prospective: bool = False

    @property
    def closed_utc(self) -> datetime:
        return _utc(self.start_utc) + HOUR

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "symbol": self.symbol,
            "start_utc": _utc(self.start_utc).isoformat(),
            "closed_utc": self.closed_utc.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "feed": self.feed,
            "captured_utc": _utc(self.captured_utc).isoformat(),
            "prospective": self.prospective,
        }


@dataclass(frozen=True)
class AssetDatasetReview:
    symbol: str
    asset_class: str
    feed: str
    bar_count: int
    first_open_utc: str
    last_close_utc: str
    historical_bars: int
    prospective_bars: int
    content_sha256: str
    eligible_for_trading: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "OFFLINE_ASSET_DATASET_QUALITY_RESEARCH_ONLY",
            **self.__dict__,
            "broker_order_submission": "DISABLED",
        }


def validate_asset_dataset(
    bars: Sequence[ResearchBar],
    *,
    spec: CandidateAsset,
    as_of: datetime,
    expected_session_opens_utc: Sequence[datetime] | None = None,
) -> AssetDatasetReview:
    """Fail on symbol/feed contamination, gaps, duplicates and open/future candles.

    Crypto requires exactly consecutive hourly UTC bars. US equities require
    an explicit independently sourced XNYS session-open timeline from the
    caller: NEVER infer a 24/7 calendar, DST, holiday or extended-hours bar.
    This function checks DATA SHAPE, not a claim that a feed is entitled or
    that an historical import was captured prospectively.
    """
    if candidate(spec.symbol) != spec:
        raise ValueError("research spec must match the disabled allowlist")
    observed_at = _utc(as_of)
    items = tuple(bars)
    if not items:
        raise ValueError("empty dataset is not market evidence")
    if (spec.asset_class == AssetClass.US_EQUITY
            and expected_session_opens_utc is None):
        raise ValueError("verified equity exchange-session timeline required")
    if spec.asset_class == AssetClass.CRYPTO and expected_session_opens_utc is not None:
        raise ValueError("crypto timeline is fixed to continuous UTC hours")

    all_times: list[datetime] = []
    feed: str | None = None
    last: datetime | None = None
    prospective_count = 0
    for bar in items:
        if not isinstance(bar, ResearchBar) or bar.symbol != spec.symbol:
            raise ValueError("mixed symbols / malformed asset row")
        at = _utc(bar.start_utc)
        captured = _utc(bar.captured_utc)
        if (bar.start_utc.utcoffset() != timedelta(0) or at.minute or at.second
                or at.microsecond):
            raise ValueError("research hour must have UTC-aligned start")
        if at + HOUR > observed_at:
            raise ValueError("unclosed or future bar cannot enter research")
        if not isinstance(bar.feed, str) or not bar.feed.strip() or len(bar.feed) > 100:
            raise ValueError("explicit provider/feed provenance required")
        if feed is not None and feed != bar.feed:
            raise ValueError("do not silently mix provider feeds")
        feed = bar.feed
        if last is not None and at <= last:
            raise ValueError("duplicate/out-of-order asset bar")
        if (last is not None and spec.asset_class == AssetClass.CRYPTO
                and at != last + HOUR):
            raise ValueError("crypto hourly gap must never be backfilled or hidden")
        for val in (bar.open, bar.high, bar.low, bar.close):
            _number(val)
        _number(bar.volume, allow_zero=True)
        if (bar.low > bar.high or bar.high < max(bar.open, bar.close)
                or bar.low > min(bar.open, bar.close)):
            raise ValueError("invalid OHLC consistency")
        # Prospective is a provenance claim: capture time must fall in the
        # current close's own hour, not simply a flag on historical bars.
        if type(bar.prospective) is not bool:
            raise ValueError("prospective marker must be boolean")
        if bar.prospective:
            if captured < at + HOUR or captured >= at + 2 * HOUR:
                raise ValueError("historical/replayed candle cannot masquerade as prospective")
            prospective_count += 1
        elif captured < at + HOUR:
            raise ValueError("historical row captured before it closed")
        all_times.append(at)
        last = at

    if expected_session_opens_utc is not None:
        timeline = tuple(_utc(m) for m in expected_session_opens_utc)
        if any(m.minute or m.second or m.microsecond for m in timeline):
            raise ValueError("equity exchange timeline must be UTC-hour-aligned")
        if tuple(all_times) != timeline:
            raise ValueError("equity bars differ from independently specified sessions")
    canonical = [bar.to_dict() for bar in items]
    digest = hashlib.sha256(
        (json.dumps(canonical, separators=(",", ":"), sort_keys=True) + "\n")
        .encode("utf-8")
    ).hexdigest()
    return AssetDatasetReview(
        spec.symbol, spec.asset_class.value, feed or "", len(items),
        all_times[0].isoformat(), (all_times[-1] + HOUR).isoformat(),
        len(items) - prospective_count, prospective_count, digest,
    )


def summarize_parallel_research(
    verified_datasets: Mapping[str, tuple[ResearchBar, ...]],
    *,
    reviews: Mapping[str, AssetDatasetReview],
) -> dict[str, object]:
    """A dozen same-hour assets are not a dozen elapsed independent hours."""
    if set(verified_datasets) != set(reviews):
        raise ValueError("every input symbol must have a validated review")
    all_prospective_hours: set[str] = set()
    cross_asset_bars = 0
    for sym, rows in verified_datasets.items():
        review = reviews[sym]
        if review.symbol != sym or review.bar_count != len(rows):
            raise ValueError("dataset and quality review identity mismatch")
        # Revalidate SHA-bound canonical data instead of trusting count alone.
        canonical = [bar.to_dict() for bar in rows]
        digest = hashlib.sha256(
            (json.dumps(canonical, separators=(",", ":"), sort_keys=True) + "\n")
            .encode("utf-8")
        ).hexdigest()
        if digest != review.content_sha256:
            raise ValueError("asset dataset content changed after quality review")
        cross_asset_bars += review.prospective_bars
        for row in rows:
            if row.prospective:
                all_prospective_hours.add(row.closed_utc.isoformat())
    return {
        "kind": "OFFLINE_PARALLEL_ASSET_RESEARCH_COUNTS_NOT_PERFORMANCE",
        "asset_count": len(verified_datasets),
        "prospective_asset_bar_count": cross_asset_bars,
        "distinct_prospective_clock_hours": len(all_prospective_hours),
        "strategy_validated": False,
        "live_trading": "UNAVAILABLE",
        "broker_order_submission": "DISABLED",
    }
