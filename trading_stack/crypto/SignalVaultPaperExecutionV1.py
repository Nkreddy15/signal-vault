"""Multi-signal PAPER execution harness for Signal Vault.

This is an execution/observation harness, not a profitability claim. It runs
several independent long-only setup families on 5-minute bars so the local
paper stack can demonstrate entries, exits, persistence, P&L and risk behavior
without waiting for one rare crossover condition.

PAPER/dry-run only.
"""

from __future__ import annotations

from pathlib import Path
import os
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SignalVaultPaperExecutionV1(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 50

    minimal_roi = {"0": 0.004}
    stoploss = -0.02
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        # Persistent handoff: old trades keep V1 exits across container restarts.
        root = Path(os.getenv("PERSIST_DIR", "/freqtrade/data"))
        return not any((root / folder / "activated").exists()
                       for folder in ("paper-final-v9", "paper-v10"))

    @property
    def protections(self):
        """Fail-safe PAPER protections around a deliberately active harness."""
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 3,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,
                "trade_limit": 3,
                "stop_duration_candles": 12,
                "required_profit": 0.0,
                "only_per_pair": False,
                "only_per_side": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 288,
                "trade_limit": 6,
                "stop_duration_candles": 24,
                "max_allowed_drawdown": 0.05,
                "calculation_mode": "equity",
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        dataframe["sv_ema_5"] = close.ewm(span=5, adjust=False).mean()
        dataframe["sv_ema_13"] = close.ewm(span=13, adjust=False).mean()
        dataframe["sv_ema_34"] = close.ewm(span=34, adjust=False).mean()
        dataframe["sv_roc_3"] = close.pct_change(3)
        dataframe["sv_roc_12"] = close.pct_change(12)
        dataframe["sv_mean_20"] = close.rolling(20).mean()
        dataframe["sv_std_20"] = close.rolling(20).std()
        dataframe["sv_z_20"] = (
            (close - dataframe["sv_mean_20"]) /
            dataframe["sv_std_20"].replace(0, float("nan"))
        )
        dataframe["sv_prior_high_20"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["sv_vol_mean_20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe["sv_ema_5"]
        slow = dataframe["sv_ema_13"]
        long = dataframe["sv_ema_34"]
        close = dataframe["close"]
        volume_ok = dataframe["volume"] > 0

        trend = (
            (fast > slow)
            & (slow > long)
            & (close > fast)
            & (dataframe["sv_roc_3"] > 0)
            & volume_ok
        )

        momentum = (
            (fast > slow)
            & (dataframe["sv_roc_3"] > 0.003)
            & (dataframe["sv_roc_12"] > 0)
            & volume_ok
        )

        breakout = (
            (close > dataframe["sv_prior_high_20"])
            & (dataframe["volume"] >= dataframe["sv_vol_mean_20"])
            & volume_ok
        )

        mean_reversion_bounce = (
            (dataframe["sv_z_20"] < -1.25)
            & (close > close.shift(1))
            & (fast > fast.shift(1))
            & volume_ok
        )

        any_setup = trend | momentum | breakout | mean_reversion_bounce
        dataframe.loc[any_setup, "enter_long"] = 1
        dataframe.loc[trend, "enter_tag"] = "trend"
        dataframe.loc[momentum, "enter_tag"] = "momentum"
        dataframe.loc[breakout, "enter_tag"] = "breakout"
        dataframe.loc[mean_reversion_bounce, "enter_tag"] = "mean_reversion_bounce"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe["sv_ema_5"]
        slow = dataframe["sv_ema_13"]
        close = dataframe["close"]

        trend_failure = (fast < slow) & (close < fast)
        downside_momentum = dataframe["sv_roc_3"] < -0.004
        stretched_reversion = dataframe["sv_z_20"] > 1.5

        exit_setup = (
            (trend_failure | downside_momentum | stretched_reversion)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[exit_setup, "exit_long"] = 1
        dataframe.loc[trend_failure, "exit_tag"] = "trend_failure"
        dataframe.loc[downside_momentum, "exit_tag"] = "downside_momentum"
        dataframe.loc[stretched_reversion, "exit_tag"] = "reversion_exit"
        return dataframe
