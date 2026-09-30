"""Bounded long-horizon historical research chunk planning.

Signal Vault deliberately stores provider history in small immutable source
bundles. This module plans longer research horizons as non-overlapping bounded
chunks without changing any network/order permission.

It is only a planner: no credentials, network requests, strategy selection or
orders are performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

CRYPTO_MAX_CHUNK_DAYS = 14
EQUITY_MAX_CHUNK_CALENDAR_DAYS = 35


@dataclass(frozen=True)
class HistoricalChunk:
    market: str
    start: str
    end_exclusive: str
    ordinal: int

    def as_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "start": self.start,
            "end_exclusive": self.end_exclusive,
            "ordinal": self.ordinal,
        }


def crypto_history_chunks(
    *,
    start_utc: datetime,
    end_utc_exclusive: datetime,
) -> tuple[HistoricalChunk, ...]:
    start = _utc_hour(start_utc)
    end = _utc_hour(end_utc_exclusive)
    if not start < end:
        raise ValueError("crypto historical range must be positive")
    return tuple(
        HistoricalChunk(
            market="crypto",
            start=a.isoformat(),
            end_exclusive=b.isoformat(),
            ordinal=i,
        )
        for i, (a, b) in enumerate(
            _datetime_chunks(start, end, timedelta(days=CRYPTO_MAX_CHUNK_DAYS)),
            start=1,
        )
    )


def equity_history_chunks(
    *,
    start_date: date,
    end_date_exclusive: date,
) -> tuple[HistoricalChunk, ...]:
    if type(start_date) is not date or type(end_date_exclusive) is not date:
        raise ValueError("equity historical range requires date-only bounds")
    if not start_date < end_date_exclusive:
        raise ValueError("equity historical range must be positive")
    chunks: list[HistoricalChunk] = []
    cursor = start_date
    ordinal = 1
    while cursor < end_date_exclusive:
        stop = min(
            cursor + timedelta(days=EQUITY_MAX_CHUNK_CALENDAR_DAYS),
            end_date_exclusive,
        )
        chunks.append(
            HistoricalChunk(
                market="us_equity",
                start=cursor.isoformat(),
                end_exclusive=stop.isoformat(),
                ordinal=ordinal,
            )
        )
        cursor = stop
        ordinal += 1
    return tuple(chunks)


def research_plan_summary(
    *,
    crypto_start_utc: datetime,
    crypto_end_utc_exclusive: datetime,
    equity_start_date: date,
    equity_end_date_exclusive: date,
) -> dict[str, object]:
    crypto = crypto_history_chunks(
        start_utc=crypto_start_utc,
        end_utc_exclusive=crypto_end_utc_exclusive,
    )
    equity = equity_history_chunks(
        start_date=equity_start_date,
        end_date_exclusive=equity_end_date_exclusive,
    )
    return {
        "kind": "MULTIMARKET_BOUNDED_HISTORICAL_RESEARCH_PLAN",
        "crypto_chunks": [x.as_dict() for x in crypto],
        "equity_chunks": [x.as_dict() for x in equity],
        "kalshi_history": "SEPARATE_RESOLVED_MARKET_DATASET_REQUIRED",
        "network_requests": "NONE",
        "credentials_accessed": "NONE",
        "broker_order_submission": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }


def _utc_hour(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware historical UTC bound required")
    result = value.astimezone(timezone.utc)
    if result.minute or result.second or result.microsecond:
        raise ValueError("crypto history bounds must align to exact UTC hours")
    return result


def _datetime_chunks(
    start: datetime,
    end: datetime,
    size: timedelta,
) -> tuple[tuple[datetime, datetime], ...]:
    output: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        stop = min(cursor + size, end)
        output.append((cursor, stop))
        cursor = stop
    return tuple(output)
