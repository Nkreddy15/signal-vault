#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile edge "$@"; }
echo 'Daily leaders, channel swings and shared-account blend; no profit ceiling.'
echo 'Uses the existing frozen universe. Paper entries stay paused.'
dc build crypto_edge_lab
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab /freqtrade/user_data/regime_swing_lab.py \
  --data-dir /freqtrade/data/edge-universe-v1 --output-dir /freqtrade/data/regime-swing-v2 "$@"
mkdir -p ../.data/regime-swing-v2 "$HOME/Downloads"
for name in regime-summary.json regime-results.md; do
  dc run --rm -T --no-deps --entrypoint python crypto_edge_lab - "$name" <<'PY' > "../.data/regime-swing-v2/$name"
import sys
from pathlib import Path
print((Path('/freqtrade/data/regime-swing-v2')/sys.argv[1]).read_text(),end='')
PY
done
cp ../.data/regime-swing-v2/regime-summary.json "$HOME/Downloads/regime-summary.txt"
echo 'Completed. Upload Downloads/regime-summary.txt using the chat attachment button.'
open -R "$HOME/Downloads/regime-summary.txt"
