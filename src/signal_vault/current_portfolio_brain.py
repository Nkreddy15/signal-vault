"""Current multi-market research brain over persisted forward evidence.

Combines independent crypto and US-stock model signals into the Phase 162
consensus + shared allocator. Kalshi remains represented as a lane but emits no
model signal here until an independently calibrated probability model exists.

This is read-only research. It never calls a provider or broker and cannot
submit PAPER, DEMO, or LIVE orders.
"""
from __future__ import annotations

from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

from .crypto_forward_compact_models import build_compact_crypto_model_signals
from .crypto_universe_forward import _audit_chain,_safe_root
from .decision_cycle import run_decision_cycle
from .equity_cloud_sidecar import CHILD as EQUITY_CHILD
from .equity_forward_archive_audit import load_current_equity_forward_segment
from .equity_model_warmup import load_stock_model_warmup
from .opportunity_engine import AllocatorLimits
from .railway_btc_first_dual_cron import BASENAME as SIX_CRYPTO_BASENAME
from .six_crypto_forward_scorecard import _active_datasets
from .stock_forward_compact_models import (
    MINIMUM_COMPLETED_CORE_HOURS,
    build_stock_cross_source_signals,
)


def _utc(value:datetime)->datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware portfolio brain timestamp required")
    return value.astimezone(timezone.utc)


def build_current_portfolio_brain(
    *,
    root:Path,
    as_of:datetime,
)->dict[str,object]:
    base=Path(root)
    if base.is_symlink() or not base.is_dir() or base.stat().st_mode&0o077:
        raise ValueError("portfolio brain requires private forward evidence root")
    now=_utc(as_of)
    signals=[]
    lanes={}

    crypto_root=base/SIX_CRYPTO_BASENAME
    try:
        source=_safe_root(crypto_root)
        chain=_audit_chain(source)
        if not chain:
            lanes["crypto"]={"status":"NO_VERIFIED_SOURCE_CHAIN"}
        else:
            segment=chain[-1]["segment_index"]
            active=[x for x in chain if x["segment_index"]==segment]
            if len(active)<2:
                lanes["crypto"]={
                    "status":"WAITING_FOR_73RD_COMPLETED_BAR",
                    "source_receipts":len(active),
                }
            else:
                latest=active[-1]
                captured=datetime.fromisoformat(
                    latest["captured_utc"]
                ).astimezone(timezone.utc)
                crypto_signals=build_compact_crypto_model_signals(
                    _active_datasets(active),
                    source_receipt_sha256=latest["receipt_sha256"],
                    captured_utc=captured,
                )
                signals.extend(crypto_signals)
                lanes["crypto"]={
                    "status":"AVAILABLE",
                    "model_signal_count":len(crypto_signals),
                    "source_receipts":len(active),
                    "latest_closed_hour_utc":latest["closed_hour_utc"],
                }
    except Exception as exc:
        lanes["crypto"]={
            "status":"FAILED_SAFE",
            "failure_class":type(exc).__name__,
        }

    stock_root=base/EQUITY_CHILD
    try:
        audit,datasets,timeline=load_current_equity_forward_segment(stock_root)
        prospective_hours=len(timeline)
        inference=datasets
        warmup_used=False
        warmup_hours=0
        if prospective_hours<MINIMUM_COMPLETED_CORE_HOURS:
            record,warmup=load_stock_model_warmup(
                stock_root=stock_root,
                first_forward_open=timeline[0],
            )
            needed=MINIMUM_COMPLETED_CORE_HOURS-prospective_hours
            if any(len(warmup[symbol])<needed for symbol in warmup):
                raise ValueError("stock model warmup shorter than feature requirement")
            inference={
                symbol:tuple(warmup[symbol][-needed:])+tuple(datasets[symbol])
                for symbol in datasets
            }
            warmup_used=True
            warmup_hours=needed
        captures={
            rows[-1].captured_utc.astimezone(timezone.utc)
            for rows in datasets.values()
        }
        if len(captures)!=1:
            raise ValueError("stock latest capture timestamps differ")
        captured=next(iter(captures))
        stock_signals=build_stock_cross_source_signals(
            inference,
            captured_utc=captured,
            allow_historical_warmup=warmup_used,
        )
        signals.extend(stock_signals)
        lanes["us_equity"]={
            "status":"AVAILABLE",
            "model_signal_count":len(stock_signals),
            "prospective_core_hours":prospective_hours,
            "historical_feature_warmup_used":warmup_used,
            "historical_feature_warmup_hours_used":warmup_hours,
            "historical_feature_warmup_counts_as_prospective":False,
            "source_integrity_passed":audit.get("source_integrity_passed"),
        }
    except Exception as exc:
        lanes["us_equity"]={
            "status":"FAILED_SAFE_OR_NOT_READY",
            "failure_class":type(exc).__name__,
        }

    lanes["kalshi_event_contract"]={
        "status":"WAITING_FOR_INDEPENDENT_CALIBRATED_PROBABILITY_MODEL",
        "reference_hypotheses_remain_separate_research_evidence":True,
    }

    limits=AllocatorLimits(
        min_expected_net_return=Decimal("0.001"),
    )
    cycle=run_decision_cycle(
        tuple(signals),
        as_of=now,
        allocator_limits=limits,
        mode="research",
        min_independent_models=2,
        min_consensus=Decimal("0.60"),
        min_model_ensemble_net_return=Decimal("0.001"),
    )
    summary=cycle.summary()
    return {
        "kind":"PHASE162_CURRENT_MULTIMARKET_RESEARCH_BRAIN_NO_ORDER",
        "checked_at_utc":now.isoformat(),
        "lanes":lanes,
        "input_model_signal_count":len(signals),
        "decision_cycle":summary,
        "selected_market_lanes":sorted({
            row["market"]
            for row in summary["selected"]
        }),
        "automatic_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
