"""Signal Vault PAPER strategy V3.

V3 is a lower-frequency, long-only research candidate built after V2 failed its
predeclared Q2 screening gate. The objective is entry selectivity, not activity.

Key changes from V2:
- 1h bars instead of 15m
- strict long-term bullish regime; otherwise stay in cash
- momentum24 and trend-pullback setups only
- no breakout-only or generic continuation entries
- cost-aware volatility-capacity gate
- profit-aware exits and a smaller hard risk budget

Research/PAPER only. No profitability claim.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SignalVaultPaperExecutionV3(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 240

    minimal_roi = {"0": 100.0}
    stoploss = -0.015
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    ASSUMED_ROUND_TRIP_FRICTION = 0.0074
    MIN_MOVE_CAPACITY = 0.020
    MIN_PROFIT_TARGET = 0.030
    MAX_PROFIT_TARGET = 0.060
    PROFIT_PROTECT_FLOOR = 0.020
    REGIME_FAIL_EXIT_FLOOR = -0.009

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,
                "trade_limit": 2,
                "stop_duration_candles": 12,
                "required_profit": 0.0,
                "only_per_pair": False,
                "only_per_side": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 240,
                "trade_limit": 6,
                "stop_duration_candles": 24,
                "max_allowed_drawdown": 0.05,
                "calculation_mode": "equity",
            },
        ]

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0.0, float("nan"))
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _atr(dataframe: DataFrame, period: int = 14) -> pd.Series:
        prev_close = dataframe["close"].shift(1)
        tr = pd.concat(
            [
                dataframe["high"] - dataframe["low"],
                (dataframe["high"] - prev_close).abs(),
                (dataframe["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        low = dataframe["low"]
        volume = dataframe["volume"]

        dataframe["v3_ema20"] = close.ewm(span=20, adjust=False).mean()
        dataframe["v3_ema50"] = close.ewm(span=50, adjust=False).mean()
        dataframe["v3_ema200"] = close.ewm(span=200, adjust=False).mean()

        dataframe["v3_ema50_slope12"] = dataframe["v3_ema50"].pct_change(12)
        dataframe["v3_ema200_slope24"] = dataframe["v3_ema200"].pct_change(24)
        dataframe["v3_ret6"] = close.pct_change(6)
        dataframe["v3_ret24"] = close.pct_change(24)
        dataframe["v3_ret72"] = close.pct_change(72)

        dataframe["v3_rsi14"] = self._rsi(close, 14)
        dataframe["v3_atr14"] = self._atr(dataframe, 14)
        dataframe["v3_atr_pct"] = dataframe["v3_atr14"] / close

        dataframe["v3_vol_mean20"] = volume.rolling(20).mean()
        dataframe["v3_vol_ratio"] = (
            volume / dataframe["v3_vol_mean20"].replace(0.0, float("nan"))
        )

        dataframe["v3_recent_pullback"] = (
            low.rolling(4).min() <= dataframe["v3_ema20"] * 1.003
        )
        dataframe["v3_move_capacity"] = dataframe["v3_atr_pct"] * 4.0

        below50 = close < dataframe["v3_ema50"]
        dataframe["v3_below50_2"] = (
            below50 & below50.shift(1).fillna(False)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        volume_ok = dataframe["volume"] > 0

        # V3 is allowed to do nothing for long stretches. On spot, cash is a
        # valid position when the long-term regime is not favorable.
        regime = (
            (close > dataframe["v3_ema200"])
            & (dataframe["v3_ema20"] > dataframe["v3_ema50"])
            & (dataframe["v3_ema50"] > dataframe["v3_ema200"])
            & (dataframe["v3_ema50_slope12"] > 0.002)
            & (dataframe["v3_ema200_slope24"] > 0.0)
            & (dataframe["v3_ret72"] > 0.0)
        )

        cost_gate = dataframe["v3_move_capacity"] >= self.MIN_MOVE_CAPACITY

        momentum24 = (
            (dataframe["v3_ret24"] >= 0.030)
            & (dataframe["v3_ret6"] > 0.005)
            & dataframe["v3_rsi14"].between(54, 72)
            & (dataframe["v3_vol_ratio"] >= 0.85)
            & (close <= dataframe["v3_ema20"] * 1.035)
        )

        trend_pullback = (
            dataframe["v3_recent_pullback"]
            & (close > dataframe["v3_ema20"])
            & (dataframe["v3_ret24"] > 0.010)
            & (dataframe["v3_ret6"] > 0.0)
            & dataframe["v3_rsi14"].between(50, 66)
            & (dataframe["v3_vol_ratio"] >= 0.75)
        )

        enter = regime & cost_gate & (momentum24 | trend_pullback) & volume_ok
        dataframe.loc[enter, "enter_long"] = 1
        dataframe.loc[
            enter & momentum24 & ~trend_pullback,
            "enter_tag",
        ] = "v3_momentum24"
        dataframe.loc[
            enter & trend_pullback & ~momentum24,
            "enter_tag",
        ] = "v3_trend_pullback"
        dataframe.loc[
            enter & momentum24 & trend_pullback,
            "enter_tag",
        ] = "v3_multi_confirmed"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        if self.dp is None:
            return None

        dataframe, _ = self.dp.get_analyzed_dataframe(
            pair=pair,
            timeframe=self.timeframe,
        )
        if dataframe is None or dataframe.empty:
            return None

        last = dataframe.iloc[-1]
        atr_pct = float(last.get("v3_atr_pct") or 0.0)

        adaptive_target = max(
            self.MIN_PROFIT_TARGET,
            atr_pct * 4.0,
            self.ASSUMED_ROUND_TRIP_FRICTION * 3.5,
        )
        adaptive_target = min(adaptive_target, self.MAX_PROFIT_TARGET)
        if current_profit >= adaptive_target:
            return "v3_volatility_target"

        protect_floor = max(
            self.PROFIT_PROTECT_FLOOR,
            self.ASSUMED_ROUND_TRIP_FRICTION * 2.5,
        )
        trend_softening = (
            float(last.get("close") or 0.0) < float(last.get("v3_ema20") or 0.0)
            and float(last.get("v3_ret6") or 0.0) < 0.0
        )
        if current_profit >= protect_floor and trend_softening:
            return "v3_profit_protect"

        regime_failed = (
            bool(last.get("v3_below50_2"))
            and float(last.get("v3_ema20") or 0.0)
            < float(last.get("v3_ema50") or 0.0)
            and float(last.get("v3_ret24") or 0.0) <= 0.0
        )
        if regime_failed and current_profit <= self.REGIME_FAIL_EXIT_FLOOR:
            return "v3_regime_failure"

        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if age_hours >= 72.0:
            if current_profit >= protect_floor:
                return "v3_72h_profit_exit"
            if current_profit > -self.ASSUMED_ROUND_TRIP_FRICTION and trend_softening:
                return "v3_72h_stale_exit"

        return None
