"""Signal Vault PAPER strategy V4.

V4 is a selective, long-only research candidate created after V3 failed its
frozen Q2 gate. It adds a BTC market-regime guard and only trades a pullback
that has already begun to re-accelerate.

The design goal is to avoid temporary bullish-looking setups inside a broader
crypto drawdown. Research/PAPER only. No profitability claim.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SignalVaultPaperExecutionV4(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 240

    minimal_roi = {"0": 100.0}
    stoploss = -0.012
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    ASSUMED_ROUND_TRIP_FRICTION = 0.0074
    MIN_MOVE_CAPACITY = 0.025
    MIN_PROFIT_TARGET = 0.035
    MAX_PROFIT_TARGET = 0.060
    PROFIT_PROTECT_FLOOR = 0.022
    REGIME_FAIL_EXIT_FLOOR = -0.006
    BTC_RISK_EXIT_FLOOR = -0.004

    def informative_pairs(self):
        return [("BTC/USD", self.timeframe)]

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 3},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 48,
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
                "max_allowed_drawdown": 0.04,
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

    @staticmethod
    def _add_btc_indicators(btc: DataFrame) -> DataFrame:
        btc = btc.copy()
        close = btc["close"]
        btc["btc_close"] = close
        btc["btc_ema50"] = close.ewm(span=50, adjust=False).mean()
        btc["btc_ema200"] = close.ewm(span=200, adjust=False).mean()
        btc["btc_ema200_slope24"] = btc["btc_ema200"].pct_change(24)
        btc["btc_ret24"] = close.pct_change(24)
        btc["btc_ret168"] = close.pct_change(168)
        return btc[
            [
                "date",
                "btc_close",
                "btc_ema50",
                "btc_ema200",
                "btc_ema200_slope24",
                "btc_ret24",
                "btc_ret168",
            ]
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        low = dataframe["low"]
        volume = dataframe["volume"]

        dataframe["v4_ema20"] = close.ewm(span=20, adjust=False).mean()
        dataframe["v4_ema50"] = close.ewm(span=50, adjust=False).mean()
        dataframe["v4_ema200"] = close.ewm(span=200, adjust=False).mean()

        dataframe["v4_ema50_slope12"] = dataframe["v4_ema50"].pct_change(12)
        dataframe["v4_ema200_slope24"] = dataframe["v4_ema200"].pct_change(24)
        dataframe["v4_ret3"] = close.pct_change(3)
        dataframe["v4_ret24"] = close.pct_change(24)
        dataframe["v4_ret72"] = close.pct_change(72)
        dataframe["v4_ret168"] = close.pct_change(168)

        dataframe["v4_rsi14"] = self._rsi(close, 14)
        dataframe["v4_atr14"] = self._atr(dataframe, 14)
        dataframe["v4_atr_pct"] = dataframe["v4_atr14"] / close
        dataframe["v4_move_capacity"] = dataframe["v4_atr_pct"] * 4.0

        dataframe["v4_vol_mean20"] = volume.rolling(20).mean()
        dataframe["v4_vol_ratio"] = (
            volume / dataframe["v4_vol_mean20"].replace(0.0, float("nan"))
        )

        dataframe["v4_recent_pullback"] = (
            low.rolling(6).min() <= dataframe["v4_ema20"] * 1.004
        )
        dataframe["v4_prior_high3"] = dataframe["high"].rolling(3).max().shift(1)

        below50 = close < dataframe["v4_ema50"]
        dataframe["v4_below50_2"] = (
            below50 & below50.shift(1).fillna(False)
        )

        # Market regime guard. DataProvider is available in backtest and
        # dry-run. Exact-date merging on the same completed 1h timeframe avoids
        # using any future BTC candle.
        dataframe["v4_btc_risk_on"] = False
        if self.dp is not None:
            btc = self.dp.get_pair_dataframe(pair="BTC/USD", timeframe=self.timeframe)
            if btc is not None and not btc.empty:
                btc = self._add_btc_indicators(btc)
                dataframe = dataframe.merge(btc, on="date", how="left")
                dataframe[
                    [
                        "btc_close",
                        "btc_ema50",
                        "btc_ema200",
                        "btc_ema200_slope24",
                        "btc_ret24",
                        "btc_ret168",
                    ]
                ] = dataframe[
                    [
                        "btc_close",
                        "btc_ema50",
                        "btc_ema200",
                        "btc_ema200_slope24",
                        "btc_ret24",
                        "btc_ret168",
                    ]
                ].ffill()

                dataframe["v4_btc_risk_on"] = (
                    (dataframe["btc_close"] > dataframe["btc_ema200"])
                    & (dataframe["btc_ema50"] > dataframe["btc_ema200"])
                    & (dataframe["btc_ema200_slope24"] > 0.0005)
                    & (dataframe["btc_ret168"] > 0.015)
                    & (dataframe["btc_ret24"] > -0.015)
                )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]

        pair_regime = (
            (close > dataframe["v4_ema200"] * 1.01)
            & (dataframe["v4_ema20"] > dataframe["v4_ema50"])
            & (dataframe["v4_ema50"] > dataframe["v4_ema200"])
            & (dataframe["v4_ema50_slope12"] > 0.002)
            & (dataframe["v4_ema200_slope24"] > 0.0)
            & (dataframe["v4_ret168"] > 0.02)
            & (dataframe["v4_ret72"] > 0.005)
        )

        pullback_reaccel = (
            dataframe["v4_recent_pullback"]
            & (close > dataframe["v4_ema20"])
            & (close > dataframe["v4_prior_high3"])
            & (dataframe["v4_ret3"] > 0.002)
            & (dataframe["v4_ret24"] > 0.01)
            & dataframe["v4_rsi14"].between(52, 68)
            & (dataframe["v4_vol_ratio"] >= 0.85)
            & (close <= dataframe["v4_ema20"] * 1.025)
        )

        enter = (
            dataframe["v4_btc_risk_on"]
            & pair_regime
            & pullback_reaccel
            & (dataframe["v4_move_capacity"] >= self.MIN_MOVE_CAPACITY)
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[enter, ["enter_long", "enter_tag"]] = (
            1,
            "v4_btc_guarded_pullback_reaccel",
        )
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
        atr_pct = float(last.get("v4_atr_pct") or 0.0)

        adaptive_target = max(
            self.MIN_PROFIT_TARGET,
            atr_pct * 4.5,
            self.ASSUMED_ROUND_TRIP_FRICTION * 4.5,
        )
        adaptive_target = min(adaptive_target, self.MAX_PROFIT_TARGET)
        if current_profit >= adaptive_target:
            return "v4_volatility_target"

        protect_floor = max(
            self.PROFIT_PROTECT_FLOOR,
            self.ASSUMED_ROUND_TRIP_FRICTION * 3.0,
        )
        trend_softening = (
            float(last.get("close") or 0.0) < float(last.get("v4_ema20") or 0.0)
            and float(last.get("v4_ret3") or 0.0) < 0.0
        )
        if current_profit >= protect_floor and trend_softening:
            return "v4_profit_protect"

        btc_risk_on = bool(last.get("v4_btc_risk_on"))
        if (not btc_risk_on) and current_profit <= self.BTC_RISK_EXIT_FLOOR:
            return "v4_btc_risk_off"

        regime_failed = (
            bool(last.get("v4_below50_2"))
            and float(last.get("v4_ema20") or 0.0)
            < float(last.get("v4_ema50") or 0.0)
            and float(last.get("v4_ret24") or 0.0) <= 0.0
        )
        if regime_failed and current_profit <= self.REGIME_FAIL_EXIT_FLOOR:
            return "v4_pair_regime_failure"

        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if age_hours >= 72.0:
            if current_profit >= protect_floor:
                return "v4_72h_profit_exit"
            if current_profit > -self.ASSUMED_ROUND_TRIP_FRICTION and trend_softening:
                return "v4_72h_stale_exit"

        return None
