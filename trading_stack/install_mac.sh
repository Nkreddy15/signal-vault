#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop is not installed."
  echo "Install Docker Desktop for Mac, open it once, then rerun:"
  echo "  bash trading_stack/install_mac.sh"
  open "https://www.docker.com/products/docker-desktop/" >/dev/null 2>&1 || true
  exit 2
fi

if ! docker info >/dev/null 2>&1; then
  open -a Docker >/dev/null 2>&1 || true
  echo "Docker Desktop is installed but the daemon is not ready. Open Docker Desktop, then rerun this script."
  exit 2
fi

ENV_FILE="$ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -z "${ALPACA_API_KEY:-}" ]]; then
  read -r -s -p "Alpaca PAPER key ID: " ALPACA_API_KEY
  echo
fi
if [[ -z "${ALPACA_API_SECRET:-}" ]]; then
  read -r -s -p "Alpaca PAPER secret key: " ALPACA_API_SECRET
  echo
fi

if [[ -z "$ALPACA_API_KEY" || -z "$ALPACA_API_SECRET" ]]; then
  echo "Both Alpaca PAPER credentials are required." >&2
  exit 2
fi

FREQTRADE__API_SERVER__USERNAME="${FREQTRADE__API_SERVER__USERNAME:-nikhil}"
STOCK_DAILY_BUY_CAP="${STOCK_DAILY_BUY_CAP:-16}"

if [[ -z "${FREQTRADE__API_SERVER__PASSWORD:-}" ]]; then
  FREQTRADE__API_SERVER__PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)"
fi
if [[ -z "${FREQTRADE__API_SERVER__JWT_SECRET_KEY:-}" ]]; then
  FREQTRADE__API_SERVER__JWT_SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
fi
if [[ -z "${FREQTRADE__API_SERVER__WS_TOKEN:-}" ]]; then
  FREQTRADE__API_SERVER__WS_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
fi

umask 077
cat > "$ENV_FILE" <<EOF
ALPACA_API_KEY=$ALPACA_API_KEY
ALPACA_API_SECRET=$ALPACA_API_SECRET
ALPACA_IS_PAPER=true
STOCK_LOGICAL_BUDGET_USD=100
STOCK_DAILY_BUY_CAP=$STOCK_DAILY_BUY_CAP
FREQTRADE__API_SERVER__USERNAME=$FREQTRADE__API_SERVER__USERNAME
FREQTRADE__API_SERVER__PASSWORD=$FREQTRADE__API_SERVER__PASSWORD
FREQTRADE__API_SERVER__JWT_SECRET_KEY=$FREQTRADE__API_SERVER__JWT_SECRET_KEY
FREQTRADE__API_SERVER__WS_TOKEN=$FREQTRADE__API_SERVER__WS_TOKEN
EOF
chmod 600 "$ENV_FILE"

docker compose --env-file "$ENV_FILE" up -d --build

echo
echo "Signal Vault PAPER stack started."
echo "Unified dashboard: http://127.0.0.1:8090"
echo "Crypto FreqUI:     http://127.0.0.1:8080"
echo "FreqUI username:   $FREQTRADE__API_SERVER__USERNAME"
echo "FreqUI password:   $FREQTRADE__API_SERVER__PASSWORD"
echo "Stocks also remain visible in Alpaca PAPER."
echo
echo "Check containers with:"
echo "  cd $ROOT && docker compose ps"
echo "Follow logs with:"
echo "  cd $ROOT && docker compose logs -f"
