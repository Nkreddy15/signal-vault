"""Manual production-process smoke, isolated local state and no trading entries.

Public data requests only. This verifies local process and restart behavior,
not Railway durable mounting, cloud deployment, brokerage fills or profits.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def main():
    report={"mode":"ISOLATED LOCAL PRODUCTION-PROCESS SMOKE","broker_orders":False}
    with tempfile.TemporaryDirectory(prefix="sv-integrated-smoke-") as tmp:
        root=Path(tmp);cfg=json.loads((Path(__file__).parent/'cloud_paper/campaign.integrated.json').read_text())
        cfg.update(entry_markets=[],dex_enabled=False,stock_symbols=[],cycle_seconds=10)
        config=root/'config.json';config.write_text(json.dumps(cfg))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        password=secrets.token_urlsafe(36)
        env=dict(os.environ,SV_LOCAL_TEST='1',SV_ALLOW_NEW_CAMPAIGN='1',SV_STATE_DIR=str(root/'state'),SV_CONFIG=str(config),
                 SV_DASHBOARD_USER='nikhil',SV_DASHBOARD_PASSWORD=password,PORT=str(port),SIGNAL_VAULT_MODE='paper')
        for name in list(env):
            if name.startswith(('ALPACA_PAPER_','KALSHI_DEMO_')):env.pop(name)
        base=f'http://127.0.0.1:{port}'
        auth='Basic '+base64.b64encode(('nikhil:'+password).encode()).decode()
        log=(root/'process.log').open('w+')
        children=[]
        def start():
            p=subprocess.Popen([sys.executable,'-m','trading_stack.cloud_paper.supervisor'],env=env,stdout=log,stderr=log)
            children.append(p);return p
        def stop(p):
            p.terminate()
            try:p.wait(timeout=40)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        def wait_cycle(p, minimum):
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                if p.poll() is not None:raise RuntimeError('Supervisor exited; isolated process log retained only during smoke')
                try:
                    with urlopen(Request(base+'/api/snapshot',headers={'Authorization':auth}),timeout=3) as r:s=json.load(r)
                    if s['cloud']['cycles']>=minimum:return s
                except (URLError,TimeoutError):pass
                time.sleep(.5)
            raise TimeoutError('No completed worker cycle within smoke budget')
        try:
            first=start();before=wait_cycle(first,1)
            try:urlopen(base+'/api/snapshot',timeout=3)
            except HTTPError as e:report['unauthenticated_status']=e.code
            else:raise AssertionError('Private API did not reject unauthenticated access')
            if report['unauthenticated_status']!=401:raise AssertionError('Unexpected private API rejection')
            with urlopen(base+'/healthz',timeout=3) as r:report['health_status']=r.status
            report['providers']={k:{f:v.get(f) for f in ['status','reason','mode']} for k,v in before['cloud']['providers'].items()}
            stop(first);env.pop('SV_ALLOW_NEW_CAMPAIGN')
            second=start();after=wait_cycle(second,before['cloud']['cycles']+1);stop(second)
            for key in ('campaign_id','config_hash','started_at','deadline'):
                if before['cloud'][key]!=after['cloud'][key]:raise AssertionError('Restart changed '+key)
            if after['cloud']['portfolio']['cash']!=500 or after['cloud']['open_trades'] or after['cloud']['closed_trades']:
                raise AssertionError('Read-only smoke altered account capital')
            report.update(restart_preserved_identity_and_deadline=True,completed_cycles=after['cloud']['cycles'],paper_cash=500,recorded_trades=0)
            with sqlite3.connect(root/'state/campaign.sqlite3') as db:
                report['sqlite_integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
                report['stored_candles']=db.execute('SELECT COUNT(*) FROM candles').fetchone()[0]
                report['order_count']=len(json.loads(db.execute('SELECT payload FROM state').fetchone()[0])['orders'])
            report['result']='PASS'
        except Exception:
            log.flush();log.seek(0)
            print(log.read()[-12000:].replace(password,'[REDACTED]'),file=sys.stderr)
            raise
        finally:
            for p in children:
                if p.poll() is None:stop(p)
            log.close()
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
