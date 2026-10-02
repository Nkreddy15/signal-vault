"""Frozen Phase 162 research candidate registry.

Only candidates with explicit, reproducible evidence enter this registry. A
registry entry is NOT trading authorization. It records the exact model family,
feature profile, horizon, threshold, evidence receipt and forward-bootstrap
compatibility so later shadow/PAPER code cannot silently mutate a candidate.

The registry intentionally contains no model weights. Model artifacts must be
trained from SHA-bound source evidence and separately fingerprinted before use.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class CandidateState(str, Enum):
    SHADOW = "shadow"
    SECONDARY_SHADOW = "secondary_shadow"
    REJECTED = "rejected"


@dataclass(frozen=True)
class FrozenCandidate:
    candidate_id: str
    market_lane: str
    model_family: str
    horizon_hours: int
    entry_threshold_return: Decimal
    feature_names: tuple[str, ...]
    maximum_feature_lookback_hours: int
    source_receipt_path: str
    source_artifact_sha256: str
    validation_net_pnl_usd: Decimal
    validation_trade_count: int
    validation_win_rate: Decimal
    validation_max_drawdown_usd: Decimal
    descriptive_holdout_base_pnl_usd: Decimal
    descriptive_holdout_base_trade_count: int
    descriptive_holdout_base_win_rate: Decimal
    descriptive_holdout_base_max_drawdown_usd: Decimal
    passive_holdout_base_pnl_usd: Decimal
    state: CandidateState
    paper_order_authorized: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.candidate_id.isascii():
            raise ValueError("versioned candidate id required")
        if self.market_lane not in {"crypto", "us_equity", "kalshi_event_contract"}:
            raise ValueError("unknown market lane")
        if type(self.horizon_hours) is not int or self.horizon_hours <= 0:
            raise ValueError("positive horizon required")
        if (
            type(self.entry_threshold_return) is not Decimal
            or not self.entry_threshold_return.is_finite()
            or self.entry_threshold_return <= 0
        ):
            raise ValueError("positive finite threshold required")
        if not self.feature_names or len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("unique feature profile required")
        if (
            type(self.maximum_feature_lookback_hours) is not int
            or self.maximum_feature_lookback_hours <= 0
        ):
            raise ValueError("positive feature lookback required")
        if (
            not self.source_receipt_path.startswith("research/results/")
            or ".." in self.source_receipt_path
        ):
            raise ValueError("candidate must bind to repository research receipt")
        if (
            len(self.source_artifact_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.source_artifact_sha256)
        ):
            raise ValueError("source artifact SHA256 required")
        for amount in (
            self.validation_net_pnl_usd,
            self.validation_max_drawdown_usd,
            self.descriptive_holdout_base_pnl_usd,
            self.descriptive_holdout_base_max_drawdown_usd,
            self.passive_holdout_base_pnl_usd,
        ):
            if type(amount) is not Decimal or not amount.is_finite():
                raise ValueError("candidate evidence amounts must be finite Decimal")
        if type(self.validation_trade_count) is not int or self.validation_trade_count < 0:
            raise ValueError("invalid validation trade count")
        if (
            type(self.descriptive_holdout_base_trade_count) is not int
            or self.descriptive_holdout_base_trade_count < 0
        ):
            raise ValueError("invalid holdout trade count")
        for rate in (self.validation_win_rate, self.descriptive_holdout_base_win_rate):
            if type(rate) is not Decimal or not Decimal("0") <= rate <= Decimal("1"):
                raise ValueError("win rates must lie in [0,1]")
        if type(self.paper_order_authorized) is not bool:
            raise ValueError("paper authorization flag must be explicit")
        if self.paper_order_authorized:
            raise ValueError("Phase 162 research registry cannot authorize paper orders")


DEPLOYABLE_CRYPTO_FEATURES = (
    "ret_1h",
    "ret_3h",
    "ret_6h",
    "ret_12h",
    "ret_24h",
    "ret_48h",
    "ema12_over_ema26_minus1",
    "ema24_over_ema72_minus1",
    "vol_24h",
    "vol_72h",
    "range_1h",
    "volume_z_24h",
    "cross_section_rank_24h",
)

_SOURCE_SHA = "433a848b87cf269812ed08232ee1a7d5815fbffbd4fe19bd71c15bd3d83e7572"
_RECEIPT = "research/results/phase162_deployable_crypto_ml_receipt.json"

PHASE162_CANDIDATES: tuple[FrozenCandidate, ...] = (
    FrozenCandidate(
        candidate_id="crypto-rf-48h-return15bps-v1-phase162",
        market_lane="crypto",
        model_family="random_forest_regressor",
        horizon_hours=48,
        entry_threshold_return=Decimal("0.015"),
        feature_names=DEPLOYABLE_CRYPTO_FEATURES,
        maximum_feature_lookback_hours=72,
        source_receipt_path=_RECEIPT,
        source_artifact_sha256=_SOURCE_SHA,
        validation_net_pnl_usd=Decimal("1.670922826337673"),
        validation_trade_count=26,
        validation_win_rate=Decimal("0.5769230769230769"),
        validation_max_drawdown_usd=Decimal("3.0750228915170936"),
        descriptive_holdout_base_pnl_usd=Decimal("8.479566255573985"),
        descriptive_holdout_base_trade_count=27,
        descriptive_holdout_base_win_rate=Decimal("0.5925925925925926"),
        descriptive_holdout_base_max_drawdown_usd=Decimal("4.655601747294796"),
        passive_holdout_base_pnl_usd=Decimal("14.629553700557423"),
        state=CandidateState.SHADOW,
    ),
    FrozenCandidate(
        candidate_id="crypto-extra-trees-48h-return125bps-v1-phase162",
        market_lane="crypto",
        model_family="extra_trees_regressor",
        horizon_hours=48,
        entry_threshold_return=Decimal("0.0125"),
        feature_names=DEPLOYABLE_CRYPTO_FEATURES,
        maximum_feature_lookback_hours=72,
        source_receipt_path=_RECEIPT,
        source_artifact_sha256=_SOURCE_SHA,
        validation_net_pnl_usd=Decimal("1.2809149963686366"),
        validation_trade_count=27,
        validation_win_rate=Decimal("0.5185185185185185"),
        validation_max_drawdown_usd=Decimal("3.2535966794021647"),
        descriptive_holdout_base_pnl_usd=Decimal("5.961927676044041"),
        descriptive_holdout_base_trade_count=28,
        descriptive_holdout_base_win_rate=Decimal("0.5"),
        descriptive_holdout_base_max_drawdown_usd=Decimal("6.184039031324247"),
        passive_holdout_base_pnl_usd=Decimal("14.629553700557423"),
        state=CandidateState.SECONDARY_SHADOW,
    ),
)


def candidate_by_id(candidate_id: str) -> FrozenCandidate:
    matches = [item for item in PHASE162_CANDIDATES if item.candidate_id == candidate_id]
    if len(matches) != 1:
        raise ValueError("unknown or duplicate frozen candidate")
    return matches[0]


def active_shadow_candidates(market_lane: str) -> tuple[FrozenCandidate, ...]:
    if market_lane not in {"crypto", "us_equity", "kalshi_event_contract"}:
        raise ValueError("unknown market lane")
    return tuple(
        item
        for item in PHASE162_CANDIDATES
        if item.market_lane == market_lane
        and item.state in {CandidateState.SHADOW, CandidateState.SECONDARY_SHADOW}
    )
