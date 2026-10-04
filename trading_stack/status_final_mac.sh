#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
docker compose --env-file .env --profile final ps crypto crypto_final dashboard
docker compose --env-file .env --profile final exec -T dashboard python - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8090/api/paper-final', timeout=10) as r:
    s=json.load(r)
c=s['crypto']
print('Version:', s.get('version'), '| Status:', s['status'])
print('Successful market cycles:', s.get('cycles'), '| Evaluated hours:', s.get('hours_evaluated'))
print('Session end:', s.get('ends_at'))
print('Realized P&L:', c.get('closed_pnl_usd'), '| Open P&L:', c.get('open_pnl_usd'), '| Equity:', c.get('marked_equity'))
print('Open:', c.get('open_trade_count'), '| Closed:', c.get('closed_trade_count'))
for row in s.get('diagnostics', []): print(row['pair'], ':', row['reason'])
for err in c.get('errors', []): print('ERROR:', err)
print(s.get('note', ''))
PY
