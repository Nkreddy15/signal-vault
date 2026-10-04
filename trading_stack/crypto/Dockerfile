FROM freqtradeorg/freqtrade:stable@sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199

USER root
RUN mkdir -p /freqtrade/data /freqtrade/user_data/strategies \
    && chown -R ftuser:ftuser /freqtrade/data /freqtrade/user_data
COPY --chown=ftuser:ftuser config.json /freqtrade/user_data/config.json
COPY --chown=ftuser:ftuser SignalVaultPaperEMA12x26V1.py /freqtrade/user_data/strategies/SignalVaultPaperEMA12x26V1.py
COPY --chown=ftuser:ftuser SignalVaultPaperExecutionV1.py /freqtrade/user_data/strategies/SignalVaultPaperExecutionV1.py
COPY --chown=ftuser:ftuser SignalVaultPaperExecutionV2.py /freqtrade/user_data/strategies/SignalVaultPaperExecutionV2.py
COPY --chown=ftuser:ftuser SignalVaultPaperExecutionV3.py /freqtrade/user_data/strategies/SignalVaultPaperExecutionV3.py
COPY --chown=ftuser:ftuser SignalVaultPaperExecutionV4.py /freqtrade/user_data/strategies/SignalVaultPaperExecutionV4.py
COPY --chown=ftuser:ftuser kraken_quarterly_ohlcv.py /freqtrade/user_data/kraken_quarterly_ohlcv.py
COPY --chown=ftuser:ftuser research_v5_bidirectional.py /freqtrade/user_data/research_v5_bidirectional.py
COPY --chown=ftuser:ftuser binance_quarter_holdout.py /freqtrade/user_data/binance_quarter_holdout.py
COPY --chown=ftuser:ftuser research_v6_tournament.py /freqtrade/user_data/research_v6_tournament.py
COPY --chown=ftuser:ftuser research_v7_low_turnover.py /freqtrade/user_data/research_v7_low_turnover.py
COPY --chown=ftuser:ftuser research_v8_short_only.py /freqtrade/user_data/research_v8_short_only.py
COPY --chown=ftuser:ftuser v8_overnight_paper.py /freqtrade/user_data/v8_overnight_paper.py
COPY --chown=ftuser:ftuser v8_forward_lab.py /freqtrade/user_data/v8_forward_lab.py
COPY --chown=ftuser:ftuser paper_final.py /freqtrade/user_data/paper_final.py
COPY --chown=ftuser:ftuser paper_v10.py /freqtrade/user_data/paper_v10.py
COPY --chown=ftuser:ftuser backtest_v10.py /freqtrade/user_data/backtest_v10.py
COPY --chown=ftuser:ftuser multi_strategy_lab.py /freqtrade/user_data/multi_strategy_lab.py
COPY --chown=ftuser:ftuser regime_swing_lab.py durable_trend_lab.py financing_edge_lab.py bear_regime_lab.py paper_v11.py /freqtrade/user_data/
COPY --chown=ftuser:ftuser binance_q4_holdout.py /freqtrade/user_data/binance_q4_holdout.py
COPY --chown=ftuser:ftuser start.sh /freqtrade/start-open-source-stack.sh
RUN chmod 0755 /freqtrade/start-open-source-stack.sh
USER ftuser

EXPOSE 8080
ENTRYPOINT ["/bin/bash", "/freqtrade/start-open-source-stack.sh"]
