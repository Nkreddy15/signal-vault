"""High-activity PAPER execution harness for Signal Vault.

Purpose: exercise the full local paper-trading pipeline (signals -> simulated
orders -> positions -> exits -> P&L -> persistence -> dashboard) frequently
enough to validate plumbing. This is deliberately NOT the researched hourly
strategy and MUST NOT be interpreted as evidence of profitability.

PAPER/dry-run only. Long-only spot. Six-pair universe comes from config.json.
"""

from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class SignalVaultPaperExecutionV1(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 30

    # Execution-harness exits: take small simulated wins, cut plumbing-test
    # losses quickly, and also exit when the short trend turns down.
    minimal_roi = {"0": 0.003}
    stoploss = -0.02
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sv_exec_ema_fast_5"] = dataframe["close"].ewm(
            span=5, adjust=False
        ).mean()
        dataframe["sv_exec_ema_slow_13"] = dataframe["close"].ewm(
            span=13, adjust=False
        ).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe["sv_exec_ema_fast_5"]
        slow = dataframe["sv_exec_ema_slow_13"]

        # State-based entry rather than exact crossover so the harness does not
        # sit idle simply because it started after a crossover already happened.
        dataframe.loc[
            (
                (fast > slow)
                & (dataframe["close"] >= fast)
                & (dataframe["close"] > dataframe["close"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "paper_exec_positive_5m_state")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast = dataframe["sv_exec_ema_fast_5"]
        slow = dataframe["sv_exec_ema_slow_13"]

        dataframe.loc[
            (
                (
                    (fast < slow)
                    | (dataframe["close"] < fast)
                )
                & (dataframe["volume"] > 0)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "paper_exec_state_exit")

        return dataframe
