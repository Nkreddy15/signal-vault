"""Strict read-back and offline multi-asset analysis of immutable history bundles.

This file NEVER imports a network transport, cloud credentials, real positions,
PAPER order tools or LIVE trading. It consumes only our explicitly created
historical batch JSON files (with their SHA-bound filename), independently
revalidates chronology, and produces descriptive comparisons; no optimization
against the held-out research fold or strategy promotion.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .multi_asset_historical import HistoricalDataBatch
from .multi_asset_simulation import (
    ExplicitRoundTripCosts, HYPOTHESES, ResearchHypothesis,
    chronological_three_way_review,
)
from .research_universe import (
    AssetClass, ResearchBar, candidate, validate_asset_dataset,
)
from .shared_research_book import SharedResearchLimits, simulate_shared_research_book

ARCHIVE_RE=re.compile(
    r"historical-(crypto|us_equity)-(\d{8}T\d{4}Z)-(\d{8}T\d{4}Z)-([0-9a-f]{16})\.json\Z")
MAX_ARCHIVE_BYTES=8_000_000


def _stamp(raw: object) -> datetime:
    if not isinstance(raw,str) or len(raw)>64:
        raise ValueError("invalid historical archive timestamp")
    try:
        ts=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("invalid archive timestamp") from exc
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("archive timestamp missing UTC offset")
    return ts.astimezone(timezone.utc)


def read_historical_archive(path: str | Path) -> HistoricalDataBatch:
    """Read only our own canonical <=8 MB SHA-named 0600 historical snapshot.

    Hash validation binds metadata, all symbols, provider feed, OHLCV, capture
    timestamps and the historical-only labels, so a renamed/edited file is
    not silently treated as a valid input.
    """
    src=Path(path)
    match=ARCHIVE_RE.fullmatch(src.name)
    if (match is None or src.is_symlink() or not src.is_file() or
            src.stat().st_mode & 0o077 or not 0<src.stat().st_size<=MAX_ARCHIVE_BYTES):
        raise ValueError("invalid/unprivate historical research archive")
    raw=src.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if not digest.startswith(match[4]):
        raise ValueError("historical archive content SHA does not match filename")
    payload=json.loads(raw)
    if not isinstance(payload,dict) or set(payload)!={
            "kind","schema_version","asset_class","symbols","feed","adjustment",
            "start_utc","end_utc","downloaded_utc","page_count","bars",
            "prospective_observations_verified","broker_order_submission",
            "historical_not_independent_validation"}:
        raise ValueError("unexpected/missing historical dataset manifest fields")
    if (payload["kind"]!="BOUNDED_HISTORICAL_MULTIASSET_DATA_GET_NOT_FORWARD_EVIDENCE"
            or payload["schema_version"]!=1
            or payload["prospective_observations_verified"]!=0
            or payload["historical_not_independent_validation"] is not True
            or payload["broker_order_submission"]!="DISABLED"
            or payload["asset_class"]!=match[1]):
        raise ValueError("cannot promote or relabel retrospective data")
    symbols=payload["symbols"]
    if (not isinstance(symbols,list) or not 1<=len(symbols)<=6
            or symbols!=sorted(set(symbols))
            or not isinstance(payload["bars"],dict)
            or set(symbols)!=set(payload["bars"])
            or not isinstance(payload["page_count"],int)
            or not 1<=payload["page_count"]<=40):
        raise ValueError("invalid historical batch symbol/page manifest")
    start=_stamp(payload["start_utc"])
    end=_stamp(payload["end_utc"])
    downloaded=_stamp(payload["downloaded_utc"])
    if not start<end<=downloaded or end-start>timedelta(days=14):
        raise ValueError("incomplete or future historical window")
    if (start.strftime("%Y%m%dT%H%MZ")!=match[2] or
            end.strftime("%Y%m%dT%H%MZ")!=match[3]):
        raise ValueError("historical archive filename bounds do not match payload")
    category=AssetClass(payload["asset_class"])
    feed=payload["feed"]
    adjust=payload["adjustment"]
    expected_feed=(feed if category==AssetClass.CRYPTO
                   else feed+"|adjustment="+adjust)
    if ((category==AssetClass.CRYPTO and
         (feed!="alpaca_crypto_us" or adjust!="not_applicable")) or
        (category==AssetClass.US_EQUITY and
         (feed not in ("alpaca_equity_iex","alpaca_equity_sip") or adjust!="all"))):
        raise ValueError("historical provider provenance/feed mismatch")
    parsed={}
    for symbol in symbols:
        if candidate(symbol).asset_class!=category:
            raise ValueError("wrong market category in historical manifest")
        source_rows=payload["bars"][symbol]
        if not isinstance(source_rows,list) or not source_rows:
            raise ValueError("missing historical asset rows")
        rebuilt=[]
        last_at=None
        for obj in source_rows:
            if not isinstance(obj,dict) or set(obj)!={
                    "symbol","start_utc","closed_utc","open","high","low","close",
                    "volume","feed","captured_utc","prospective"}:
                raise ValueError("unexpected historical row schema")
            at=_stamp(obj["start_utc"])
            closed=_stamp(obj["closed_utc"])
            captured=_stamp(obj["captured_utc"])
            if (obj["symbol"]!=symbol or obj["feed"]!=expected_feed or
                    obj["prospective"] is not False or
                    at+timedelta(hours=1)!=closed or
                    not start<=at or closed>end or
                    captured<closed or captured>downloaded or
                    (last_at is not None and at<=last_at)):
                raise ValueError("invalid historical row provenance/chronology")
            try:
                values=[Decimal(v) for v in (obj["open"],obj["high"],obj["low"],
                                              obj["close"],obj["volume"])]
            except (TypeError,ValueError) as exc:
                raise ValueError("invalid historical numeric fields") from exc
            rebuilt.append(ResearchBar(
                symbol,at,*values,expected_feed,captured,False))
            last_at=at
        parsed[symbol]=tuple(rebuilt)
    batch=HistoricalDataBatch(
        payload["asset_class"],tuple(symbols),feed,adjust,
        start.isoformat(),end.isoformat(),downloaded.isoformat(),
        payload["page_count"],parsed)
    if batch.canonical_bytes()!=raw:
        raise ValueError("noncanonical historical archive, do not trust edited content")
    return batch


def combine_historical_archives(
    archives: Sequence[HistoricalDataBatch],
    *,
    as_of: datetime,
    equity_calendars: Mapping[str,Sequence[datetime]] | None = None,
) -> tuple[dict[str,tuple[ResearchBar,...]],dict[str,object]]:
    """No overlapping segments, different feeds, or unverified calendar joins."""
    parts=tuple(archives)
    if not parts:
        raise ValueError("no historical market datasets")
    latest=as_of.astimezone(timezone.utc)
    by_sym:dict[str,list[tuple[HistoricalDataBatch,tuple[ResearchBar,...]]]]={}
    sources:dict[str,tuple[str,str,str]]={}
    for batch in parts:
        start=_stamp(batch.start_utc)
        end=_stamp(batch.end_utc)
        if end>latest:
            raise ValueError("historical segment ends after as_of")
        for sym,segment in batch.bars.items():
            identity=(batch.asset_class,batch.feed,batch.adjustment)
            if sym in sources and sources[sym]!=identity:
                raise ValueError("cannot combine mixed feeds/adjustments for a symbol")
            sources[sym]=identity
            by_sym.setdefault(sym,[]).append((batch,tuple(segment)))
    calendars={} if equity_calendars is None else dict(equity_calendars)
    combined={}
    reviews={}
    for sym,segments in by_sym.items():
        ordered=sorted(segments,key=lambda pair:_stamp(pair[0].start_utc))
        category=candidate(sym).asset_class
        for (before,_),(after,_) in zip(ordered,ordered[1:]):
            before_end=_stamp(before.end_utc)
            after_start=_stamp(after.start_utc)
            if before_end>after_start:
                raise ValueError("overlapping/replayed historical provider segments for "+sym)
            if category==AssetClass.CRYPTO and before_end!=after_start:
                raise ValueError("nonconsecutive crypto historical windows for "+sym)
        if category==AssetClass.US_EQUITY:
            grid=calendars.get(sym)
            if grid is None:
                raise ValueError("verified exchange session grid required for equity archive joins")
            # A stock MUST have no fabricated rows during overnight, weekends,
            # holidays or early closes. A missing session bucket inside an
            # expected market session is NOT patched into history either.
            timeline=tuple(_stamp(x.isoformat()) for x in grid)
            for batch,group in ordered:
                start,end=_stamp(batch.start_utc),_stamp(batch.end_utc)
                expected=tuple(t for t in timeline
                               if start<=t and t+timedelta(hours=1)<=end)
                if not expected or tuple(bar.start_utc for bar in group)!=expected:
                    raise ValueError("stock historical window diverges from verified exchange grid")
        rows=tuple(bar for _,group in ordered for bar in group)
        report=validate_asset_dataset(
            rows,spec=candidate(sym),as_of=latest,
            expected_session_opens_utc=calendars.get(sym))
        combined[sym]=rows
        reviews[sym]=report.to_dict()
    return combined,reviews


def describe_multi_asset_research(
    datasets: Mapping[str,Sequence[ResearchBar]],
    *,
    as_of: datetime,
    costs: Mapping[str,ExplicitRoundTripCosts],
    equity_calendars: Mapping[str,Sequence[datetime]] | None = None,
    hypotheses: Sequence[ResearchHypothesis]=HYPOTHESES,
    limits:SharedResearchLimits=SharedResearchLimits(),
) -> dict[str,object]:
    """Run all predeclared hypotheses, always include one SHARED portfolio.

    Every result is descriptive and historical. This function never selects a
    strategy to deploy based on its validation or test-period performance.
    """
    names=tuple(sorted(datasets))
    if not names or set(names)!=set(costs):
        raise ValueError("each historical asset needs separately specified estimated costs")
    if len({h.name for h in hypotheses})!=len(hypotheses) or not hypotheses:
        raise ValueError("duplicate/missing registered research hypothesis")
    calendars={} if equity_calendars is None else dict(equity_calendars)
    detail={}
    for sym in names:
        spec=candidate(sym)
        detail[sym]={}
        for hypothesis in hypotheses:
            folds=chronological_three_way_review(
                datasets[sym],spec=spec,as_of=as_of,hypothesis=hypothesis,
                costs=costs[sym],
                expected_equity_session_opens_utc=calendars.get(sym))
            detail[sym][hypothesis.name]={
                fold:{
                    "evaluation_start_utc":v["evaluation_start_utc"],
                    "evaluation_end_utc":v["evaluation_end_utc"],
                    "net_marked_pnl_usd":v["net_marked_pnl_usd"],
                    "passive_same_allocation_marked_pnl_usd":
                        v["passive_same_allocation_marked_pnl_usd"],
                    "max_marked_drawdown_usd":v["max_marked_drawdown_usd"],
                    "estimated_fees_usd":v["estimated_fees_usd"],
                    "fill_count":len(v["fills"]),
                    "data_sha256":v["data_sha256"],
                } for fold,v in folds["evaluation_folds"].items()
            }
    # Compare each PREDECLARED hypothesis using ONE shared $100 across all
    # symbols. This is a descriptive comparison, not test-period selection.
    # Keep the separately named EMA baseline for stable downstream readers.
    per_hypothesis_shared_books={}
    for hypothesis in hypotheses:
        per_hypothesis_shared_books[hypothesis.name]=simulate_shared_research_book(
            datasets,specs={sym:candidate(sym) for sym in names},
            hypotheses={sym:hypothesis for sym in names},
            assumptions=costs,as_of=as_of,equity_calendars=calendars,
            limits=limits)
    if "generic-ema12x26-v1-predeclared" not in per_hypothesis_shared_books:
        raise ValueError("shared book must include predeclared EMA baseline")
    book=per_hypothesis_shared_books["generic-ema12x26-v1-predeclared"]
    return {
        "kind":"OFFLINE_MULTIASSET_COMPARATIVE_HISTORICAL_RESEARCH_NOT_TRADING",
        "assets":list(names),
        "predeclared_hypotheses":[h.name for h in hypotheses],
        "per_asset_chronological_folds":detail,
        "one_shared_portfolio_baseline":book,
        "all_predeclared_shared_bankroll_research_books":per_hypothesis_shared_books,
        "portfolio_hypothesis_selection_performed":False,
        "research_only_historical":True,
        "untouched_test_used_for_model_selection":False,
        "future_returns_guaranteed":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
