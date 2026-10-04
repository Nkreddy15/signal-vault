#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile edge "$@"; }
echo 'Explain forecast calibration rejections using the already prepared candles.'
dc build crypto_edge_lab
dc run --rm -T --no-deps crypto_edge_lab \
  --data-dir /freqtrade/data/edge-universe-v1 \
  --output-dir /freqtrade/data/edge-research-diagnostics-v1 --diagnostics-only
mkdir -p ../.data/edge-research-v1
for name in forecast-diagnostics.json forecast-diagnostics.md; do
  dc run --rm -T --no-deps --entrypoint python crypto_edge_lab - "$name" <<'PY' > "../.data/edge-research-v1/$name"
import sys
from pathlib import Path
print((Path('/freqtrade/data/edge-research-diagnostics-v1')/sys.argv[1]).read_text(),end='')
PY
done
# Downloads avoids Finder's hidden .data folder and iCloud Desktop syncing.
mkdir -p "$HOME/Downloads"
cp ../.data/edge-research-v1/forecast-diagnostics.json "$HOME/Downloads/forecast-diagnostics.txt"
echo 'Upload Downloads/forecast-diagnostics.txt using the chat attachment button.'
open -R "$HOME/Downloads/forecast-diagnostics.txt"
