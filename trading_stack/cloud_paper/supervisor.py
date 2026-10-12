"""One durable worker, one private web process. Provider restarts failed replicas."""
import os
import fcntl
from pathlib import Path
import signal
import subprocess
import sys
import time
from .engine import load_config
from .store import Store, digest


def settings(env=None):
    e=os.environ if env is None else env
    if e.get("SIGNAL_VAULT_MODE","paper").lower()!="paper": raise ValueError("PAPER ONLY")
    if len(e.get("SV_DASHBOARD_PASSWORD",""))<32: raise ValueError("Set SV_DASHBOARD_PASSWORD (32+ characters)")
    directory=Path(e.get("SV_STATE_DIR","/data/cloud-paper")).resolve()
    if e.get("SV_LOCAL_TEST")!="1":
        mount=Path(e.get("RAILWAY_VOLUME_MOUNT_PATH","/data")).resolve()
        if not os.path.ismount(mount) or directory==mount or not directory.is_relative_to(mount):
            raise ValueError("Dedicated subdirectory on a persistent mounted volume required")
    if not (directory/"campaign.sqlite3").exists() and e.get("SV_ALLOW_NEW_CAMPAIGN")!="1":
        raise ValueError("Set SV_ALLOW_NEW_CAMPAIGN=1 for an isolated new $500 campaign; old V11 is preserved")
    return directory


def initialize_store(directory, config, environ=None, now=None):
    """Revise only under an explicit prior-hash permission and worker lock."""
    environ=os.environ if environ is None else environ
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/"worker.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        store=Store(directory) if (directory/"campaign.sqlite3").exists() else Store(directory,config,now)
        try:
            if store.read()["config_hash"]!=digest(config):
                expected=environ.get("SV_CONFIG_REVISION_FROM")
                if not expected: raise ValueError("Frozen configuration changed; explicit revision permission required")
                store.backup(time.time() if now is None else now)
                if config.get("crypto_exit_policy")=="bounded-v1": store.revise_intraday_exits(config,expected,now)
                else: store.revise_crypto_interval(config,expected,now)
            return store
        except BaseException:
            store.db.close()
            raise


def main():
    directory=settings(); os.umask(0o077)
    cfg=load_config(os.environ.get("SV_CONFIG"))
    store=initialize_store(directory,cfg);store.backup(time.time());store.db.close()
    env=dict(os.environ,SV_STATE_DIR=str(directory))
    children=[];stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        children.append(subprocess.Popen([sys.executable,"-m","trading_stack.cloud_paper.engine"],env=env))
        children.append(subprocess.Popen([sys.executable,"-m","gunicorn","--bind","0.0.0.0:"+env.get("PORT","8090"),
            "--workers","1","--threads","4","--timeout","60","--access-logfile","/dev/null","trading_stack.cloud_paper.wsgi:app"],env=env))
        while not stopping and all(p.poll() is None for p in children): time.sleep(.5)
        return 0 if stopping else 1
    finally:
        for p in children:
            if p.poll() is None: p.terminate()
        for p in children:
            try:p.wait(timeout=30)
            except subprocess.TimeoutExpired:p.kill();p.wait()


if __name__=="__main__": raise SystemExit(main())
