"""Experimental PAPER-only Freqtrade adapter for Signal Vault's generic EMA 12x26 hypothesis.

This strategy is intentionally limited to PAPER/dry-run use. It translates the
closed-bar EMA crossover research hypothesis into Freqtrade so the local stack
can collect real paper execution evidence. It does not claim the six-crypto
prospective review gate has passed or that future profitability is established.
"""

from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SignalVaultPaperEMA12x26V1(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 30

    # The research hypothesis exits on a bearish EMA cross. Keep ROI from
    # forcing unrelated exits; retain a conservative PAPER safety stop.
    minimal_roi = {"0": 100.0}
    stoploss = -0.10
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sv_ema_fast_12"] = dataframe["close"].ewm(
            span=12, adjust=False
        ).mean()
        dataframe["sv_ema_slow_26"] = dataframe["close"].ewm(
            span=26, adjust=False
        ).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe["sv_ema_fast_12"]
        slow = dataframe["sv_ema_slow_26"]

        dataframe.loc[
            (
                (fast.shift(1) <= slow.shift(1))
                & (fast > slow)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "sv_ema12x26_bull_cross")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe["sv_ema_fast_12"]
        slow = dataframe["sv_ema_slow_26"]

        dataframe.loc[
            (
                (fast.shift(1) >= slow.shift(1))
                & (fast < slow)
                & (dataframe["volume"] > 0)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "sv_ema12x26_bear_cross")

        return dataframe
