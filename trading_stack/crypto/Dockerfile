FROM freqtradeorg/freqtrade:stable

USER root
RUN mkdir -p /freqtrade/data /freqtrade/user_data/strategies \
    && chown -R ftuser:ftuser /freqtrade/data /freqtrade/user_data
COPY --chown=ftuser:ftuser config.json /freqtrade/user_data/config.json
COPY --chown=ftuser:ftuser start.sh /freqtrade/start-open-source-stack.sh
RUN chmod 0755 /freqtrade/start-open-source-stack.sh
USER ftuser

EXPOSE 8080
ENTRYPOINT ["/bin/bash", "/freqtrade/start-open-source-stack.sh"]
