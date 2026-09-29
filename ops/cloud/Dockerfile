# Standalone, code-only Python image; no Mac files, DATA keys or PAPER executor run.
# Image tag is an operator-reviewed template; pin a digest before deployment.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir --no-compile . \
    && groupadd --gid 10001 signalvault \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent signalvault \
    && mkdir -p /var/lib/signal-vault/forward \
    && chmod 0700 /var/lib/signal-vault/forward \
    && chown -R 10001:10001 /var/lib/signal-vault

USER 10001:10001
ENTRYPOINT ["python", "-m", "signal_vault.cloud_forward_service"]
CMD ["--serve"]
