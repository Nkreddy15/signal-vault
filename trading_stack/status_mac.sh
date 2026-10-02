#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "=== Containers ==="
docker compose ps

echo
echo "=== Unified dashboard ==="
curl -fsS http://127.0.0.1:8090/healthz || echo "Unified dashboard not ready"

echo
echo "=== Crypto API ==="
curl -fsS http://127.0.0.1:8080/api/v1/ping || echo "Freqtrade API not ready"

echo
echo "=== Recent stock logs ==="
docker compose logs --tail=30 stocks || true

echo
echo "=== Recent crypto logs ==="
docker compose logs --tail=30 crypto || true

echo
echo "=== Recent dashboard logs ==="
docker compose logs --tail=20 dashboard || true
