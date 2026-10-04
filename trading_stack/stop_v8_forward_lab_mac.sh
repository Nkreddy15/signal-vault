#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

docker compose --env-file .env --profile forwardlab stop crypto_v8_forward_lab
echo "V8 forward lab stopped. Persisted state and ledgers remain in the crypto data volume."
