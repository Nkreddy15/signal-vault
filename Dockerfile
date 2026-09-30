# Railway-only cron image. NO live/PAPER order worker; no exposed HTTP port.
# Railway currently mounts attached volumes as root; the service is deliberately
# configured with RAILWAY_RUN_UID=0 so it can enforce 0700 on *only* its own
# isolated persistent mount. Never mount the Mac's account/trading/forward data.
# Review/pin base image by digest prior to sustained production operation.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-compile '.[equity-research]' \
    && mkdir -p /var/lib/signal-vault/forward \
    && chmod 0700 /var/lib/signal-vault/forward

# Railway's separate cron scheduler starts this command at UTC HH:07 and
# expects it to exit each time. An absent persistent-volume mount fails closed;
# it NEVER uses the empty directory baked into this image as live evidence.
CMD ["python", "-m", "signal_vault.railway_forward_cron", "--once"]
