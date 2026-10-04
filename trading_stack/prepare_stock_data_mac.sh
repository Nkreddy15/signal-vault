#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile edge "$@"; }
echo 'GET-only historical stock research export using the existing Alpaca paper key.'
dc build crypto_edge_lab
mkdir -p "$HOME/Downloads"
DEST="$HOME/Downloads/signal-vault-stock-data.zip"
TEMP="$(mktemp "$HOME/Downloads/.signal-vault-stock-data.XXXXXX")"
trap 'rm -f "$TEMP"' EXIT
dc run --rm -T --no-deps --user "$(id -u):$(id -g)" \
  -v "$ROOT/.env:/run/signal-vault.env:ro" --entrypoint python crypto_edge_lab \
  /freqtrade/user_data/equity_data_bundle.py --env-file /run/signal-vault.env --stdout "$@" > "$TEMP"
mv "$TEMP" "$DEST"
echo 'Completed. Upload Downloads/signal-vault-stock-data.zip with the chat attachment button.'
open -R "$DEST"
