"""Unified market capability contract for Signal Vault.

This module is deliberately descriptive: it tells the UI/orchestrator what
each market lane can currently do. It never opens a network connection and
cannot submit an order.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Market = Literal["crypto", "us_equity", "kalshi"]


@dataclass(frozen=True)
class MarketCapability:
    market: Market
    provider: str
    historical_research: bool
    prospective_shadow: bool
    paper_environment: bool
    paper_order_submission: bool
    live_order_submission: bool
    live_money_available: bool
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


_CAPABILITIES: dict[Market, MarketCapability] = {
    "crypto": MarketCapability(
        market="crypto",
        provider="alpaca",
        historical_research=True,
        prospective_shadow=True,
        paper_environment=True,
        paper_order_submission=False,
        live_order_submission=False,
        live_money_available=False,
        notes=(
            "BTC-first and six-crypto forward evidence are active.",
            "Paper and live POST remain disabled pending separate gates.",
        ),
    ),
    "us_equity": MarketCapability(
        market="us_equity",
        provider="alpaca",
        historical_research=True,
        prospective_shadow=False,
        paper_environment=True,
        paper_order_submission=False,
        live_order_submission=False,
        live_money_available=False,
        notes=(
            "Historical IEX/XNYS audit tooling exists.",
            "Forward equity collector and paper execution validation remain gated.",
        ),
    ),
    "kalshi": MarketCapability(
        market="kalshi",
        provider="kalshi",
        historical_research=True,
        prospective_shadow=False,
        paper_environment=True,
        paper_order_submission=False,
        live_order_submission=False,
        live_money_available=False,
        notes=(
            "Public/demo market-data adapter foundation only.",
            "No authenticated order signing or live trading is enabled.",
        ),
    ),
}


def market_capability(market: Market) -> dict[str, object]:
    try:
        return _CAPABILITIES[market].as_dict()
    except KeyError as exc:
        raise ValueError("unsupported Signal Vault market") from exc


def multimarket_capability_snapshot() -> dict[str, object]:
    lanes = {name: item.as_dict() for name, item in _CAPABILITIES.items()}
    return {
        "kind": "SIGNAL_VAULT_MULTIMARKET_CAPABILITY_SNAPSHOT",
        "markets": lanes,
        "all_live_money_disabled": all(
            not item.live_order_submission and not item.live_money_available
            for item in _CAPABILITIES.values()
        ),
        "all_paper_order_submission_disabled": all(
            not item.paper_order_submission for item in _CAPABILITIES.values()
        ),
        "shared_risk_layer_required_before_live": True,
    }
