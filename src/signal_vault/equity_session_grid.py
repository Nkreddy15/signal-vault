"""Optional OFFLINE US equity calendar: FULL regular-session hours only.

Alpaca's 1Hour stock bars are clock-hour buckets according to the published
community report, while XNYS opens at 09:30 Eastern on regular sessions.
A 09:00-10:00 bucket could contain PREMARKET from 09:00-09:30, so this
research intentionally EXCLUDES that first partial/open bucket and EVERY
noncomplete final bucket. We start at the next full UTC hour at/after
XNYS session open and end no later than the actual early/regular close.

For a typical US summer session 13:30-20:00Z, keep 14:00,15:00,..,19:00Z
(six complete 60-minute CORE trading buckets). For an early close
14:30-18:00Z, keep 15:00,16:00,17:00Z (three buckets).
This is NOT full-session stock return data, extended-hours exposure or
evidence of broker/market-data feed entitlement. Each actual response is
required to match this grid exactly; missing IEX trade bars FAIL CLOSED,
never backfilled/interpolated.

Depend on optional [equity-research], not imported by the Railway BTC cron.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

HOUR=timedelta(hours=1)
MAX_SESSIONS=25
MAX_CALENDAR_DAYS=60


@dataclass(frozen=True)
class ConservativeEquitySession:
    trading_date: str
    market_calendar: str
    exchange_calendar_package_version: str
    exchange_open_utc: str
    exchange_close_utc: str
    first_core_bucket_open_utc: str
    last_core_bucket_close_utc: str
    expected_core_bucket_opens_utc: tuple[str,...]
    minutes_excluded_after_open: int
    minutes_excluded_before_close: int
    session_is_early_close: bool

    def as_dict(self) -> dict[str,object]:
        return {
            **self.__dict__,
            "expected_core_bucket_opens_utc":
                list(self.expected_core_bucket_opens_utc),
            "calendar_is_independent_of_actual_feed": True,
            "data_not_yet_requested_or_entitled": True,
            "first_partial_0930_hour_intentionally_excluded": True,
            "extended_hours_excluded": True,
        }

    @property
    def expected_opens(self) -> tuple[datetime,...]:
        return tuple(datetime.fromisoformat(x) for x in
                     self.expected_core_bucket_opens_utc)

    @property
    def query_start(self) -> datetime:
        return datetime.fromisoformat(self.first_core_bucket_open_utc)

    @property
    def query_end(self) -> datetime:
        return datetime.fromisoformat(self.last_core_bucket_close_utc)


def conservative_core_hour_plan(
    *,
    start_date: date,
    end_date_exclusive: date,
    as_of: datetime,
) -> tuple[ConservativeEquitySession,...]:
    """Generate a bounded real XNYS schedule, never guess US holidays/DST.

    The provider's actual IEX hourly bars must match each hour in this
    separately sourced calendar BEFORE a historical bundle is accepted.
    """
    if (type(start_date) is not date or type(end_date_exclusive) is not date
            or not start_date<end_date_exclusive
            or (end_date_exclusive-start_date).days>MAX_CALENDAR_DAYS):
        raise ValueError("explicit bounded date-only equity history window required")
    if (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("equity as_of must be timezone aware")
    checked=as_of.astimezone(timezone.utc)
    try:
        import exchange_calendars as xc
    except ImportError as exc:
        raise RuntimeError(
            "offline exchange session module requires optional [equity-research]"
        ) from exc
    try:
        # ExchangeCalendars requires start < end even for a one-session
        # history request. Build through the EXCLUSIVE endpoint and then
        # explicitly filter it out if it happens to be a trading day.
        # This also handles weekend/holiday endpoints without out-of-bounds.
        x=xc.get_calendar(
            "XNYS",start=start_date.isoformat(),
            end=end_date_exclusive.isoformat())
        sessions=tuple(
            session for session in x.sessions
            if start_date<=session.date()<end_date_exclusive)
    except Exception as exc:
        raise ValueError("requested date outside supported independent XNYS calendar") from exc
    if not 1<=len(sessions)<=MAX_SESSIONS:
        raise ValueError("equity batch requires 1-25 fully historical market sessions")
    early_closes=set(x.early_closes)
    output=[]
    for session in sessions:
        opened=x.session_open(session).to_pydatetime().astimezone(timezone.utc)
        closed=x.session_close(session).to_pydatetime().astimezone(timezone.utc)
        if not opened<closed<=checked-timedelta(minutes=20):
            raise ValueError("do not query open/future/effectively realtime stock sessions")
        first=opened.replace(minute=0,second=0,microsecond=0)
        if first<opened:
            first+=HOUR
        final=closed.replace(minute=0,second=0,microsecond=0)
        if final>closed:
            final-=HOUR
        if first>=final:
            raise ValueError("XNYS session lacks at least one full closed CORE hour")
        stamps=[]
        now=first
        while now+HOUR<=final:
            stamps.append(now.isoformat())
            now+=HOUR
        session_spec=ConservativeEquitySession(
            trading_date=session.date().isoformat(),
            market_calendar="XNYS_US_EQUITY_REGULAR_CORE_FULL_CLOCK_HOURS_ONLY",
            exchange_calendar_package_version=xc.__version__,
            exchange_open_utc=opened.isoformat(),
            exchange_close_utc=closed.isoformat(),
            first_core_bucket_open_utc=first.isoformat(),
            last_core_bucket_close_utc=final.isoformat(),
            expected_core_bucket_opens_utc=tuple(stamps),
            minutes_excluded_after_open=int((first-opened).total_seconds()//60),
            minutes_excluded_before_close=int((closed-final).total_seconds()//60),
            session_is_early_close=session in early_closes,
        )
        output.append(session_spec)
    return tuple(output)
