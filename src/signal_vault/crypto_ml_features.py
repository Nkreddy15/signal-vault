"""Shared causal crypto feature construction for Phase 162 ML research/forward use.

This removes train/forward feature drift. The same feature formulas used by the
historical 48h ML tournament can now be applied to any verified, aligned
six-crypto window with at least 73 completed hourly bars.

No model loading, broker access, credentials, network calls, or orders.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .research_universe import ResearchBar

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

MINIMUM_CLOSED_BARS = 73


def build_crypto_feature_frames(
    datasets: Mapping[str, Sequence[ResearchBar]],
) -> dict[str, pd.DataFrame]:
    """Build one causal frame per symbol from aligned completed hourly bars."""
    if not isinstance(datasets, Mapping) or len(datasets) < 2:
        raise ValueError("at least two aligned crypto datasets required")
    symbols = tuple(sorted(datasets))
    lengths = {len(tuple(datasets[symbol])) for symbol in symbols}
    if len(lengths) != 1:
        raise ValueError("crypto feature datasets must have equal length")
    count = next(iter(lengths))
    if count < MINIMUM_CLOSED_BARS:
        raise ValueError("73 completed hourly bars required for full feature vector")

    reference = None
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        rows = tuple(datasets[symbol])
        if any(not isinstance(row, ResearchBar) or row.symbol != symbol for row in rows):
            raise ValueError("malformed or mixed-symbol crypto feature input")
        stamps = tuple(row.start_utc for row in rows)
        if reference is None:
            reference = stamps
        elif stamps != reference:
            raise ValueError("crypto feature datasets must share exact hourly clock")

        frame = pd.DataFrame({
            "ts": pd.to_datetime(stamps, utc=True),
            "open": [float(row.open) for row in rows],
            "high": [float(row.high) for row in rows],
            "low": [float(row.low) for row in rows],
            "close": [float(row.close) for row in rows],
            "volume": [float(row.volume) for row in rows],
        })
        for horizon in (1, 3, 6, 12, 24, 48):
            frame[f"ret_{horizon}h"] = frame.close.pct_change(horizon)
        frame["ema12"] = frame.close.ewm(span=12, adjust=False).mean()
        frame["ema26"] = frame.close.ewm(span=26, adjust=False).mean()
        frame["ema24"] = frame.close.ewm(span=24, adjust=False).mean()
        frame["ema72"] = frame.close.ewm(span=72, adjust=False).mean()
        frame["ema12_over_ema26_minus1"] = frame.ema12 / frame.ema26 - 1.0
        frame["ema24_over_ema72_minus1"] = frame.ema24 / frame.ema72 - 1.0
        one_hour = frame.close.pct_change()
        frame["vol_24h"] = one_hour.rolling(24).std()
        frame["vol_72h"] = one_hour.rolling(72).std()
        frame["range_1h"] = (frame.high - frame.low) / frame.close
        frame["volume_z_24h"] = (
            (frame.volume - frame.volume.rolling(24).mean())
            / frame.volume.rolling(24).std()
        )
        frames[symbol] = frame

    # Cross-sectional rank is computed only from values at the same completed
    # timestamp. It cannot use a future symbol/bar.
    for index in range(count):
        values = {
            symbol: frames[symbol].loc[index, "ret_24h"]
            for symbol in symbols
        }
        if any(pd.isna(value) for value in values.values()):
            for symbol in symbols:
                frames[symbol].loc[index, "cross_section_rank_24h"] = np.nan
            continue
        ordered = sorted(symbols, key=lambda symbol: (values[symbol], symbol))
        denominator = max(1, len(symbols) - 1)
        for symbol in symbols:
            frames[symbol].loc[index, "cross_section_rank_24h"] = (
                ordered.index(symbol) / denominator * 2.0 - 1.0
            )

    return frames


def latest_crypto_feature_matrix(
    datasets: Mapping[str, Sequence[ResearchBar]],
) -> tuple[tuple[str, ...], np.ndarray, str]:
    """Return latest complete feature vector per symbol plus common close time."""
    frames = build_crypto_feature_frames(datasets)
    symbols = tuple(sorted(frames))
    matrix = []
    timestamps = set()
    for symbol in symbols:
        row = frames[symbol].iloc[-1]
        values = row[list(DEPLOYABLE_CRYPTO_FEATURES)].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("latest crypto feature row is incomplete/nonfinite")
        matrix.append(values)
        timestamps.add(row["ts"].isoformat())
    if len(timestamps) != 1:
        raise ValueError("latest crypto features are not clock aligned")
    return symbols, np.asarray(matrix, dtype=float), next(iter(timestamps))
