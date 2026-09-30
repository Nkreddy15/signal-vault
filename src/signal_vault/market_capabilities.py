"""Unified capability contract for Signal Vault market lanes.

This module is deliberately descriptive. It cannot submit orders.  It gives
the future operator UI one machine-readable place to show which markets have
historical research, prospective collection, paper execution, and live
execution enabled.

Live execution remains unavailable in every lane until a separately reviewed
adapter and owner authorization are added.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

MarketName = Literal["crypto","us_equity","kalshi_event_contract"]

@dataclass(frozen=True)
class MarketCapability:
    market: MarketName
    historical_research: bool
    prospective_collection: bool
    paper_execution: bool
    live_execution: bool
    order_submission: str
    notes: str

    def __post_init__(self) -> None:
        if self.live_execution:
            raise ValueError("Phase 29 capability map forbids live execution")
        if self.order_submission not in {"DISABLED","PAPER_ONLY_NOT_ACTIVATED"}:
            raise ValueError("unexpected order capability")

def current_market_capabilities() -> dict[str, object]:
    lanes = (
        MarketCapability(
            market="crypto",
            historical_research=True,
            prospective_collection=True,
            paper_execution=False,
            live_execution=False,
            order_submission="DISABLED",
            notes="BTC plus six-crypto cloud forward research is active; no order POST.",
        ),
        MarketCapability(
            market="us_equity",
            historical_research=True,
            prospective_collection=False,
            paper_execution=False,
            live_execution=False,
            order_submission="DISABLED",
            notes="Audited historical IEX/XNYS research exists; forward equity lane not activated.",
        ),
        MarketCapability(
            market="kalshi_event_contract",
            historical_research=True,
            prospective_collection=False,
            paper_execution=False,
            live_execution=False,
            order_submission="DISABLED",
            notes="Public historical/read-only adapter foundation only; demo/order execution not activated.",
        ),
    )
    return {
        "kind":"SIGNAL_VAULT_MULTIMARKET_CAPABILITY_MAP",
        "markets":[asdict(x) for x in lanes],
        "shared_risk_layer":"PLANNED_NOT_LIVE",
        "unified_operator_interface":"FOUNDATION_IN_PROGRESS",
        "automatic_live_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
