#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
docker compose --env-file .env --profile v11 ps crypto_v11 dashboard
docker compose --env-file .env --profile v11 exec -T dashboard python - <<'PY'
import json,urllib.request,urllib.error
try:
    with urllib.request.urlopen('http://127.0.0.1:8090/api/paper-v11',timeout=10) as r:s=json.load(r)
except urllib.error.HTTPError as exc:
    if exc.code==404:
        raise SystemExit('V11 is not selected: the dashboard still runs an older image. Pull the latest phase-162-multimarket-reset branch and rerun start_v11_500_mac.sh. No V11 account status can be reported yet.')
    raise
c=s['crypto']
print('Version:',s['version'],'| Status:',s['status'])
print('Starting paper balance:',c.get('starting_balance'),'| Equity:',c.get('marked_equity'))
print('Realized P&L:',c.get('closed_pnl_usd'),'| Open P&L:',c.get('open_pnl_usd'),'| Running allowance:',c.get('operating_cost_usd'))
print('Open:',c['open_trade_count'],'| Closed:',c['closed_trade_count'],'| Entries:',s.get('entries'))
print('Entry mode:',(s.get('entry_policy') or {}).get('name','ORIGINAL_DAILY_WINDOW'),'| Immediate checks:',s.get('entry_checks',0))
print('Next entry check:',s.get('next_evaluation_at'),'| Trial ends:',s.get('ends_at'))
print('Market cycles:',s.get('cycles'),'| Evaluated days:',s.get('intervals_evaluated'))
for row in s.get('diagnostics',[]):print(row['pair'],row.get('side',''),row['reason'],'|',row.get('execution',''))
for error in c.get('errors',[]):print('ERROR:',error)
print(s.get('note',''))
PY
