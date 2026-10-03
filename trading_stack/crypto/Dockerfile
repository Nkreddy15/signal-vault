FROM freqtradeorg/freqtrade:stable

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
COPY --chown=ftuser:ftuser binance_q4_holdout.py /freqtrade/user_data/binance_q4_holdout.py
COPY --chown=ftuser:ftuser start.sh /freqtrade/start-open-source-stack.sh
RUN chmod 0755 /freqtrade/start-open-source-stack.sh
USER ftuser

EXPOSE 8080
ENTRYPOINT ["/bin/bash", "/freqtrade/start-open-source-stack.sh"]
