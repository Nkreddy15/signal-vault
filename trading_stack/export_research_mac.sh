#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile edge "$@"; }
echo 'Exporting existing candles and replay ledgers; no replay or trading restart.'
dc build crypto_edge_lab
mkdir -p "$HOME/Downloads"
DEST="$HOME/Downloads/signal-vault-research.zip"
TEMP="$(mktemp "$HOME/Downloads/.signal-vault-research.XXXXXX")"
trap 'rm -f "$TEMP"' EXIT
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab \
  /freqtrade/user_data/export_research_bundle.py \
  --data-dir /freqtrade/data/edge-universe-v1 \
  --evidence-dir "/freqtrade/data/${1:-regime-swing-v2}" --stdout > "$TEMP"
mv "$TEMP" "$DEST"
echo 'Completed. Upload Downloads/signal-vault-research.zip with the chat attachment button.'
open -R "$DEST"
