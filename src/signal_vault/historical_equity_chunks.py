"""Bounded long-horizon US-equity historical research planner.

The existing per-run equity downloader intentionally caps each batch at 25
XNYS sessions.  This module preserves that invariant and splits a larger
historical date range into independent, auditable chunks.  It does not access
credentials or submit orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .equity_session_grid import conservative_core_hour_plan

MAX_LONG_CALENDAR_DAYS=400
MAX_CHUNKS=20
CHUNK_CALENDAR_DAYS=28

@dataclass(frozen=True)
class EquityHistoryChunk:
    start_date:str
    end_date_exclusive:str
    session_count:int
    complete_core_hours:int

    def as_dict(self) -> dict[str,object]:
        return self.__dict__.copy()

def long_horizon_equity_plan(
    *,start_date:date,end_date_exclusive:date,as_of:datetime,
) -> dict[str,object]:
    if (type(start_date) is not date or type(end_date_exclusive) is not date or
            not start_date<end_date_exclusive):
        raise ValueError("valid long-horizon equity dates required")
    days=(end_date_exclusive-start_date).days
    if days>MAX_LONG_CALENDAR_DAYS:
        raise ValueError("long-horizon equity plan exceeds bounded research window")
    chunks=[]
    cursor=start_date
    while cursor<end_date_exclusive:
        stop=min(cursor+timedelta(days=CHUNK_CALENDAR_DAYS),end_date_exclusive)
        try:
            sessions=conservative_core_hour_plan(
                start_date=cursor,end_date_exclusive=stop,as_of=as_of)
        except ValueError as exc:
            # A chunk containing only exchange holidays/weekends can be skipped,
            # but any other calendar failure must remain visible.
            if "equity batch requires 1-25" not in str(exc):
                raise
            cursor=stop
            continue
        if len(sessions)>25:
            raise AssertionError("chunk violated existing 25-session safety bound")
        chunks.append(EquityHistoryChunk(
            start_date=cursor.isoformat(),
            end_date_exclusive=stop.isoformat(),
            session_count=len(sessions),
            complete_core_hours=sum(len(x.expected_opens) for x in sessions),
        ))
        cursor=stop
        if len(chunks)>MAX_CHUNKS:
            raise ValueError("too many equity history chunks")
    if not chunks:
        raise ValueError("no closed XNYS sessions in requested history")

    # The bounded per-chunk historical collector intentionally requires at
    # least 56 complete core hours so it can produce its own chronological
    # research report. A short final calendar remainder must never be emitted
    # as a standalone chunk.
    minimum_core_hours=56
    if chunks[-1].complete_core_hours<minimum_core_hours:
        if len(chunks)<2:
            raise ValueError("long-horizon range is too short for equity research")
        previous=chunks[-2]
        final=chunks[-1]
        combined_start=date.fromisoformat(previous.start_date)
        combined_end=date.fromisoformat(final.end_date_exclusive)
        merged=None
        try:
            sessions=conservative_core_hour_plan(
                start_date=combined_start,
                end_date_exclusive=combined_end,
                as_of=as_of,
            )
            hours=sum(len(x.expected_opens) for x in sessions)
            if hours>=minimum_core_hours:
                merged=EquityHistoryChunk(
                    start_date=combined_start.isoformat(),
                    end_date_exclusive=combined_end.isoformat(),
                    session_count=len(sessions),
                    complete_core_hours=hours,
                )
        except ValueError:
            merged=None
        if merged is not None:
            chunks[-2:]=[merged]
        else:
            best=None
            span=(combined_end-combined_start).days
            for offset in range(10,max(10,span-9)):
                split=combined_start+timedelta(days=offset)
                if split>=combined_end:
                    break
                try:
                    left=conservative_core_hour_plan(
                        start_date=combined_start,
                        end_date_exclusive=split,
                        as_of=as_of,
                    )
                    right=conservative_core_hour_plan(
                        start_date=split,
                        end_date_exclusive=combined_end,
                        as_of=as_of,
                    )
                except ValueError:
                    continue
                left_hours=sum(len(x.expected_opens) for x in left)
                right_hours=sum(len(x.expected_opens) for x in right)
                if left_hours<minimum_core_hours or right_hours<minimum_core_hours:
                    continue
                score=abs(left_hours-right_hours)
                candidate=(score,split,left,left_hours,right,right_hours)
                if best is None or candidate[0]<best[0]:
                    best=candidate
            if best is None:
                raise ValueError(
                    "long-horizon final remainder cannot satisfy bounded "
                    "per-chunk research minimum"
                )
            _,split,left,left_hours,right,right_hours=best
            chunks[-2:]=[
                EquityHistoryChunk(
                    start_date=combined_start.isoformat(),
                    end_date_exclusive=split.isoformat(),
                    session_count=len(left),
                    complete_core_hours=left_hours,
                ),
                EquityHistoryChunk(
                    start_date=split.isoformat(),
                    end_date_exclusive=combined_end.isoformat(),
                    session_count=len(right),
                    complete_core_hours=right_hours,
                ),
            ]

    if any(x.complete_core_hours<minimum_core_hours for x in chunks):
        raise ValueError("every long-horizon equity chunk must support chronological research")
    return {
        "kind":"BOUNDED_LONG_HORIZON_XNYS_IEX_RESEARCH_PLAN",
        "chunks":[x.as_dict() for x in chunks],
        "chunk_count":len(chunks),
        "total_sessions":sum(x.session_count for x in chunks),
        "total_complete_core_hours_per_symbol":
            sum(x.complete_core_hours for x in chunks),
        "symbols":["AAPL","AMD","MSFT","NVDA","QQQ","SPY"],
        "feed":"iex",
        "credentials_accessed":"NONE",
        "network_requests":0,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
