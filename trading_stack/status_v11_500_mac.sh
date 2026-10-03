#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
docker compose --env-file .env --profile v11 ps crypto_v11 dashboard
docker compose --env-file .env --profile v11 exec -T dashboard python - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8090/api/paper-v11',timeout=10) as r:s=json.load(r)
c=s['crypto']
print('Version:',s['version'],'| Status:',s['status'])
print('Starting paper balance:',c.get('starting_balance'),'| Equity:',c.get('marked_equity'))
print('Realized P&L:',c.get('closed_pnl_usd'),'| Open P&L:',c.get('open_pnl_usd'),'| Running allowance:',c.get('operating_cost_usd'))
print('Open:',c['open_trade_count'],'| Closed:',c['closed_trade_count'],'| Entries:',s.get('entries'))
print('Next UTC daily decision:',s.get('next_evaluation_at'),'| Trial ends:',s.get('ends_at'))
print('Market cycles:',s.get('cycles'),'| Evaluated days:',s.get('intervals_evaluated'))
for row in s.get('diagnostics',[]):print(row['pair'],row.get('side',''),row['reason'],'|',row.get('execution',''))
for error in c.get('errors',[]):print('ERROR:',error)
print(s.get('note',''))
PY
