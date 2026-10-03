"""Signal Vault PAPER strategy V2.

Goal: reduce churn and avoid taking setups whose plausible move is too small
relative to trading friction. This is a PAPER/research candidate, not a
profitability claim.

Design:
- 15-minute bars (less noise than the V1 5-minute harness)
- long-only spot execution
- trend regime is mandatory
- momentum, breakout, or pullback-continuation confirmation is required
- entries are blocked when recent volatility/range cannot comfortably clear
  the assumed round-trip friction budget
- exits use an adaptive volatility target, profit protection after costs are
  plausibly cleared, regime-failure exits, and a hard stop
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SignalVaultPaperExecutionV2(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 210

    # Disable fixed ROI exits. V2 uses custom_exit() so the target can scale
    # with current volatility while keeping an explicit minimum target.
    minimal_roi = {"0": 100.0}

    # Hard PAPER risk limit. Regime-failure exits can close sooner.
    stoploss = -0.018
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Research assumptions. 74 bps came from the existing Signal Vault base
    # friction model. V2 requires materially more room than that before entry.
    ASSUMED_ROUND_TRIP_FRICTION = 0.0074
    ENTRY_FRICTION_MULTIPLE = 2.25
    MIN_MOVE_CAPACITY = 0.018
    MIN_PROFIT_TARGET = 0.022
    MAX_PROFIT_TARGET = 0.050
    PROFIT_PROTECT_FLOOR = 0.016

    @property
    def protections(self):
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 4,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 96,
                "trade_limit": 2,
                "stop_duration_candles": 16,
                "required_profit": 0.0,
                "only_per_pair": False,
                "only_per_side": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 384,
                "trade_limit": 6,
                "stop_duration_candles": 32,
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
        true_range = pd.concat(
            [
                dataframe["high"] - dataframe["low"],
                (dataframe["high"] - prev_close).abs(),
                (dataframe["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return true_range.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        high = dataframe["high"]
        low = dataframe["low"]
        volume = dataframe["volume"]

        dataframe["sv2_ema20"] = close.ewm(span=20, adjust=False).mean()
        dataframe["sv2_ema50"] = close.ewm(span=50, adjust=False).mean()
        dataframe["sv2_ema200"] = close.ewm(span=200, adjust=False).mean()

        dataframe["sv2_ema50_slope_8"] = dataframe["sv2_ema50"].pct_change(8)
        dataframe["sv2_roc4"] = close.pct_change(4)
        dataframe["sv2_roc12"] = close.pct_change(12)
        dataframe["sv2_roc96"] = close.pct_change(96)

        dataframe["sv2_rsi14"] = self._rsi(close, 14)
        dataframe["sv2_atr14"] = self._atr(dataframe, 14)
        dataframe["sv2_atr_pct"] = dataframe["sv2_atr14"] / close

        dataframe["sv2_prior_high24"] = high.rolling(24).max().shift(1)
        dataframe["sv2_range24_pct"] = (
            high.rolling(24).max() - low.rolling(24).min()
        ) / close

        dataframe["sv2_vol_mean20"] = volume.rolling(20).mean()
        dataframe["sv2_vol_ratio"] = (
            volume / dataframe["sv2_vol_mean20"].replace(0.0, float("nan"))
        )

        # This is a volatility-capacity filter, NOT a forecast. It prevents V2
        # from entering when recent movement is too small to justify friction.
        dataframe["sv2_move_capacity"] = pd.concat(
            [
                dataframe["sv2_atr_pct"] * 3.0,
                dataframe["sv2_range24_pct"] * 0.65,
            ],
            axis=1,
        ).max(axis=1)

        dataframe["sv2_recent_pullback"] = (
            low.rolling(4).min() <= dataframe["sv2_ema20"]
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        volume_ok = dataframe["volume"] > 0

        # Do not require every trend test to be true at the same time.
        # V1/V2 early iterations could look "stuck" after a restart simply
        # because one narrow gate stayed false for many candles. V2 now uses
        # a scored regime: broad structure still has to be bullish, but one
        # soft condition may temporarily disagree without suppressing every
        # otherwise valid setup.
        regime_score = (
            (dataframe["sv2_ema20"] > dataframe["sv2_ema50"]).astype(int)
            + (dataframe["sv2_ema50"] > dataframe["sv2_ema200"]).astype(int)
            + (close > dataframe["sv2_ema20"]).astype(int)
            + (dataframe["sv2_ema50_slope_8"] > 0.0005).astype(int)
            + (dataframe["sv2_roc96"] > -0.005).astype(int)
        )
        trend_regime = (
            (regime_score >= 4)
            & (close > dataframe["sv2_ema200"])
            & (dataframe["sv2_ema20"] > dataframe["sv2_ema50"])
        )

        required_capacity = max(
            self.MIN_MOVE_CAPACITY,
            self.ASSUMED_ROUND_TRIP_FRICTION * self.ENTRY_FRICTION_MULTIPLE,
        )
        cost_gate = dataframe["sv2_move_capacity"] >= required_capacity

        momentum = (
            (dataframe["sv2_roc4"] > 0.0025)
            & (dataframe["sv2_roc12"] > 0.005)
            & dataframe["sv2_rsi14"].between(52, 74)
            & (dataframe["sv2_vol_ratio"] >= 0.80)
        )

        breakout = (
            (close > dataframe["sv2_prior_high24"])
            & (dataframe["sv2_vol_ratio"] >= 1.05)
            & (dataframe["sv2_rsi14"] < 78)
        )

        pullback_continuation = (
            dataframe["sv2_recent_pullback"]
            & (close > dataframe["sv2_ema20"])
            & (dataframe["sv2_roc4"] > 0)
            & dataframe["sv2_rsi14"].between(48, 70)
        )

        trend_continuation = (
            (close > dataframe["sv2_ema20"])
            & (dataframe["sv2_roc12"] > 0.004)
            & dataframe["sv2_rsi14"].between(50, 72)
            & (dataframe["sv2_vol_ratio"] >= 0.75)
        )

        confirmed_setup = (
            momentum | breakout | pullback_continuation | trend_continuation
        )
        enter = trend_regime & cost_gate & confirmed_setup & volume_ok

        dataframe.loc[enter, "enter_long"] = 1
        dataframe.loc[
            enter & momentum & ~breakout & ~pullback_continuation,
            "enter_tag",
        ] = "v2_trend_momentum"
        dataframe.loc[
            enter & breakout & ~momentum & ~pullback_continuation,
            "enter_tag",
        ] = "v2_trend_breakout"
        dataframe.loc[
            enter
            & pullback_continuation
            & ~momentum
            & ~breakout
            & ~trend_continuation,
            "enter_tag",
        ] = "v2_trend_pullback"
        dataframe.loc[
            enter
            & trend_continuation
            & ~momentum
            & ~breakout
            & ~pullback_continuation,
            "enter_tag",
        ] = "v2_trend_continuation"
        dataframe.loc[
            enter
            & (
                (
                    momentum.astype(int)
                    + breakout.astype(int)
                    + pullback_continuation.astype(int)
                    + trend_continuation.astype(int)
                )
                >= 2
            ),
            "enter_tag",
        ] = "v2_multi_confirmed"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Only a decisive regime break emits a dataframe exit signal. Profit
        # taking is handled in custom_exit() so tiny sub-friction exits are not
        # the default behavior.
        severe_regime_failure = (
            (dataframe["close"] < dataframe["sv2_ema50"])
            & (dataframe["sv2_ema20"] < dataframe["sv2_ema50"])
            & (dataframe["sv2_roc4"] < -0.005)
        ) | (dataframe["close"] < dataframe["sv2_ema200"])

        dataframe.loc[
            severe_regime_failure & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "v2_regime_failure")

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
        atr_pct = float(last.get("sv2_atr_pct") or 0.0)

        adaptive_target = max(
            self.MIN_PROFIT_TARGET,
            atr_pct * 3.0,
            self.ASSUMED_ROUND_TRIP_FRICTION * 2.5,
        )
        adaptive_target = min(adaptive_target, self.MAX_PROFIT_TARGET)

        if current_profit >= adaptive_target:
            return "v2_volatility_target"

        protect_floor = max(
            self.PROFIT_PROTECT_FLOOR,
            self.ASSUMED_ROUND_TRIP_FRICTION * 2.0,
        )
        trend_softening = (
            float(last.get("close") or 0.0) < float(last.get("sv2_ema20") or 0.0)
            and float(last.get("sv2_roc4") or 0.0) < 0.0
        )
        if current_profit >= protect_floor and trend_softening:
            return "v2_cost_cleared_profit_protect"

        regime_failed = (
            float(last.get("close") or 0.0) < float(last.get("sv2_ema50") or 0.0)
            and float(last.get("sv2_ema20") or 0.0)
            < float(last.get("sv2_ema50") or 0.0)
        )
        if current_profit < 0.0 and regime_failed:
            return "v2_regime_failure"

        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if (
            age_hours >= 36.0
            and current_profit >= protect_floor
            and trend_softening
        ):
            return "v2_stale_profit_exit"

        return None
