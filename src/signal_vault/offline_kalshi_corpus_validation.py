"""Aggregate many resolved Kalshi evidence bundles without selecting a strategy.

Each child market must first pass the Phase 52 hash-bound, no-lookahead scorer.
This module then reports fixed-horizon calibration coverage/error across unique
binary settled contracts. It is a descriptive historical baseline, not alpha,
fill simulation, or permission to trade.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .offline_kalshi_resolved_validation import (
    DEFAULT_HORIZONS_SECONDS,
    score_resolved_market_evidence,
)

MAX_MARKETS=500


def _mean(values:Sequence[Decimal])->Decimal|None:
    if not values:
        return None
    return sum(values,Decimal(0))/Decimal(len(values))


def aggregate_resolved_market_scores(
    scores:Sequence[Mapping[str,object]],
    *,
    horizons_seconds:Sequence[int]=DEFAULT_HORIZONS_SECONDS,
)->dict[str,object]:
    items=tuple(scores)
    if not 1<=len(items)<=MAX_MARKETS:
        raise ValueError("bounded nonempty Kalshi resolved-market corpus required")
    horizons=tuple(horizons_seconds)
    if (
        not horizons or len(horizons)>20
        or any(type(x) is not int or x<=0 for x in horizons)
        or len(set(horizons))!=len(horizons)
    ):
        raise ValueError("fixed positive unique Kalshi corpus horizons required")

    tickers=[]
    manifests=[]
    yes_count=0
    no_count=0
    horizon_values={h:[] for h in horizons}
    horizon_probabilities={h:[] for h in horizons}
    for item in items:
        if item.get("kind")!="OFFLINE_KALSHI_RESOLVED_MARKET_CALIBRATION_SCORE":
            raise ValueError("unexpected Kalshi child score kind")
        if (
            item.get("historical_data_is_not_prospective_validation") is not True
            or item.get("score_is_market_price_calibration_not_strategy_alpha") is not True
            or item.get("strategy_selection_performed") is not False
            or item.get("demo_order_submission")!="DISABLED"
            or item.get("live_order_submission")!="DISABLED"
        ):
            raise ValueError("Kalshi child score escaped research-only contract")
        ticker=item.get("ticker")
        digest=item.get("source_manifest_sha256")
        result=item.get("resolved_result")
        if not isinstance(ticker,str) or not ticker or ticker in tickers:
            raise ValueError("Kalshi corpus requires unique nonempty market tickers")
        if not isinstance(digest,str) or len(digest)!=64 or digest in manifests:
            raise ValueError("Kalshi corpus requires unique source manifests")
        if result=="yes":
            yes_count+=1
        elif result=="no":
            no_count+=1
        else:
            raise ValueError("Kalshi corpus requires binary settled outcomes")
        rows=item.get("fixed_horizon_scores")
        if not isinstance(rows,list):
            raise ValueError("Kalshi child score missing fixed horizons")
        by_horizon={}
        for row in rows:
            if not isinstance(row,Mapping):
                raise ValueError("malformed Kalshi fixed-horizon score")
            h=row.get("horizon_seconds_before_settlement")
            if h in by_horizon:
                raise ValueError("duplicate Kalshi fixed horizon")
            by_horizon[h]=row
        if set(by_horizon)!=set(horizons):
            raise ValueError("Kalshi child horizons do not match corpus contract")
        for h in horizons:
            row=by_horizon[h]
            available=row.get("observation_available")
            if type(available) is not bool:
                raise ValueError("Kalshi horizon availability must be boolean")
            if not available:
                if any(row.get(k) is not None for k in (
                    "yes_probability","brier_error","candle_end_ts"
                )):
                    raise ValueError("unavailable Kalshi horizon contains fabricated score")
                continue
            try:
                brier=Decimal(str(row["brier_error"]))
                probability=Decimal(str(row["yes_probability"]))
            except Exception as exc:
                raise ValueError("invalid Kalshi corpus numeric score") from exc
            if (
                not brier.is_finite() or brier<0 or brier>1
                or not probability.is_finite() or probability<0 or probability>1
            ):
                raise ValueError("Kalshi corpus score outside probability bounds")
            horizon_values[h].append(brier)
            horizon_probabilities[h].append(probability)
        tickers.append(ticker)
        manifests.append(digest)

    total=len(items)
    horizon_summary={}
    for h in horizons:
        values=horizon_values[h]
        probabilities=horizon_probabilities[h]
        mean_brier=_mean(values)
        mean_probability=_mean(probabilities)
        horizon_summary[str(h)]={
            "horizon_seconds_before_settlement":h,
            "available_market_count":len(values),
            "missing_market_count":total-len(values),
            "coverage_fraction":str(Decimal(len(values))/Decimal(total)),
            "mean_brier_error":None if mean_brier is None else str(mean_brier),
            "mean_yes_probability":None if mean_probability is None else str(mean_probability),
        }

    return {
        "kind":"OFFLINE_KALSHI_RESOLVED_CORPUS_CALIBRATION_REPORT",
        "resolved_market_count":total,
        "yes_outcome_count":yes_count,
        "no_outcome_count":no_count,
        "unique_market_tickers":sorted(tickers),
        "source_manifest_sha256":sorted(manifests),
        "fixed_horizon_summary":horizon_summary,
        "historical_corpus_complete":True,
        "historical_corpus_is_not_prospective_validation":True,
        "market_price_calibration_is_not_strategy_alpha":True,
        "historical_orderbook_depth_reconstructed":False,
        "strategy_ranking_performed":False,
        "strategy_selection_performed":False,
        "automatic_strategy_promotion":"DISABLED",
        "credentials_accessed":"NONE",
        "network_requests":"NONE",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def validate_kalshi_resolved_corpus(
    evidence_roots:Sequence[str|Path],
    *,
    horizons_seconds:Sequence[int]=DEFAULT_HORIZONS_SECONDS,
)->dict[str,object]:
    roots=tuple(Path(x) for x in evidence_roots)
    if not 1<=len(roots)<=MAX_MARKETS:
        raise ValueError("bounded nonempty Kalshi evidence roots required")
    if len({str(x.resolve(strict=False)) for x in roots})!=len(roots):
        raise ValueError("duplicate Kalshi evidence root")
    scores=[
        score_resolved_market_evidence(root,horizons_seconds=horizons_seconds)
        for root in roots
    ]
    return aggregate_resolved_market_scores(
        scores,horizons_seconds=horizons_seconds
    )
