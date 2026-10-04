"""One cloud replica supervising the unchanged V11 simulator and owner dashboard."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
TERMINAL = {'SESSION_COMPLETE', 'SESSION_LOSS_LIMIT', 'USER_STOP'}


def check_settings(environ=None):
    env = os.environ if environ is None else environ
    if len(env.get('V11_DASHBOARD_PASSWORD', '')) < 32:
        raise ValueError('Set a private V11_DASHBOARD_PASSWORD of at least 32 characters.')
    mount = Path(env.get('RAILWAY_VOLUME_MOUNT_PATH', '/data')).resolve()
    directory = Path(env.get('PAPER_V11_STATE_DIR', str(mount / 'paper-v11-500'))).resolve()
    if not os.path.ismount(mount) or not directory.is_relative_to(mount) or directory == mount:
        raise ValueError('V11 requires its own persistent mounted volume; ephemeral storage is refused.')
    existing = (directory / 'ledger.sqlite3').exists()
    if not existing and env.get('V11_ALLOW_NEW_ACCOUNT') != '1':
        raise ValueError('No cloud account exists. A fresh $500 trial requires V11_ALLOW_NEW_ACCOUNT=1.')
    return directory, existing


def terminal_summary(directory):
    try:
        s = json.loads((directory / 'summary.json').read_text())
        return s if s.get('version') == 'V11-PAPER-500-1' and s.get('status') in TERMINAL and s['crypto']['open_trade_count'] == 0 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_results(directory):
    """Canonical state/events backup after the worker exits; no secrets."""
    import zipfile
    path = directory / 'cloud-results.zip'
    with sqlite3.connect(f"file:{directory / 'ledger.sqlite3'}?mode=ro", uri=True) as db:
        db.execute('BEGIN')
        state = json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
        events = [json.loads(row[0]) for row in db.execute('SELECT payload FROM events ORDER BY id')]
    temp = path.with_suffix('.tmp')
    with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('account.json', json.dumps(state, allow_nan=False))
        z.writestr('events.json', json.dumps(events, allow_nan=False))
        for name in ('summary.json', 'candles.json'):
            if (directory / name).exists():
                z.write(directory / name, name)
    os.replace(temp, path)


def main():
    try:
        directory, existing = check_settings()
    except ValueError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 2
    env = os.environ.copy()
    env['PAPER_V11_STATE_DIR'] = str(directory)
    crypto = ROOT / 'crypto' / 'paper_v11.py'
    if not existing:
        # Verify public history/quotes before the original worker creates its ledger.
        subprocess.run([sys.executable, str(crypto), '--preflight'], env=env, check=True)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'activated').write_text('Isolated V11 cloud account. Synthetic paper only.\n')
    worker = subprocess.Popen([sys.executable, str(crypto)], env=env)
    try:
        web = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--bind', '0.0.0.0:' + env.get('PORT', '8090'),
                                '--workers', '1', '--threads', '4', 'cloud_v11_web:app'], cwd=ROOT, env=env)
    except Exception:
        worker.terminate()
        try:
            worker.wait(timeout=35)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
        raise
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    result = 1
    try:
        while not stopping:
            if web.poll() is not None:
                print('Owner dashboard exited; shutting down this replica.', flush=True)
                break
            if worker.poll() is not None:
                final = terminal_summary(directory)
                if worker.returncode == 0 and final:
                    save_results(directory)
                    print('CLOUD_TRIAL_ENDED ' + json.dumps(dict(status=final['status'],
                        equity=final['crypto']['marked_equity'], entries=final['entries'],
                        closed=final['crypto']['closed_trade_count'], results=str(directory / 'cloud-results.zip'))), flush=True)
                    result = 0
                else:
                    print('V11 worker stopped unexpectedly; ledger retained for restart.', flush=True)
                break
            time.sleep(1)
        if stopping:
            result = 0
    finally:
        for child in (worker, web):
            if child.poll() is None:
                child.terminate()
        for child in (worker, web):
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
