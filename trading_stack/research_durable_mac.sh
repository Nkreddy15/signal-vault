#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile edge "$@"; }
echo 'Fixed daily trend, weekly leader and slower channel research; paper entries stay paused.'
dc build crypto_edge_lab
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab /freqtrade/user_data/durable_trend_lab.py \
  --data-dir /freqtrade/data/edge-universe-v1 --output-dir /freqtrade/data/durable-trend-v1 --stress "$@"
mkdir -p ../.data/durable-trend-v1 "$HOME/Downloads"
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab - <<'PY' > ../.data/durable-trend-v1/durable-summary.json
from pathlib import Path
print(Path('/freqtrade/data/durable-trend-v1/regime-summary.json').read_text(),end='')
PY
cp ../.data/durable-trend-v1/durable-summary.json "$HOME/Downloads/durable-summary.txt"
echo 'Completed. Full research and stress ledgers are saved in the Docker data volume.'
open -R "$HOME/Downloads/durable-summary.txt"
