"""Paper-only and UNARMED, independent one-shot/hourly research runner.

`--csv` can replay a locally supplied historical dataset. `--public-data`
requires an explicit confirmation flag, then makes read-only market-data GETs.
This module imports NO broker writer and can never submit an order.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator,Sequence

from .config import RuntimeConfig
from .market_data import AlpacaPublicCryptoBars, load_csv
from .operations import LocalResearchSupervisor
from .paper_store import PersistentPaperOrderStore


def _stamp(value: str) -> datetime:
    try: stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (TypeError,ValueError) as exc: raise ValueError('invalid aware --as-of') from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('UTC-aware --as-of required')
    return stamp.astimezone(timezone.utc)


@contextmanager
def _single_writer(path:Path) -> Iterator[None]:
    """Fail fast when another worker holds the OS-level advisory run lock."""
    import fcntl  # macOS/Linux only (deployment target)
    lock=path.with_name(path.name+'.worker.lock')
    with lock.open('a+') as fd:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PermissionError('another local Signal Vault research worker is already running') from exc
        try: yield
        finally: fcntl.flock(fd,fcntl.LOCK_UN)


def one_cycle(database:Path,*,as_of:datetime,csv_path:Path|None=None,
              source:AlpacaPublicCryptoBars|None=None) -> dict[str,object]:
    """Returns only persisted decision facts; no claim of verified profit."""
    if not database.is_file():
        raise FileNotFoundError('existing local database required; run make init-local separately')
    if (csv_path is None)==(source is None):
        raise ValueError('select exactly one offline CSV or approved public market-data feed')
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError('aware as-of timestamp is required')
    end=as_of.astimezone(timezone.utc).replace(minute=0,second=0,microsecond=0)
    if csv_path is not None:
        candles=load_csv(csv_path,as_of=as_of,min_count=28)
        origin='UNVERIFIED_OPERATOR_SUPPLIED_CSV'
    else:
        # Only a historical market-data endpoint; source does not receive any
        # paper trading secrets or broker credential arguments.
        candles=source.fetch(start=end-timedelta(hours=72),end=end,as_of=as_of)
        origin='ALPACA_PUBLIC_CRYPTO_US_READ_ONLY_DATA'
    with PersistentPaperOrderStore(database) as store:
        supervisor=LocalResearchSupervisor(store)
        uncertain=supervisor.startup(at=as_of)
        result=supervisor.run_once(candles,at=as_of)
        return {'mode':'UNARMED_PAPER_RESEARCH','external_orders_submitted':0,
                'real_money_orders_submitted':0,'source':origin,
                'restart_unknown_orders':list(uncertain),
                'status':result.status,'bar_close_utc':result.bar_close_utc,
                'evidence_id':result.evidence_id,'explanation':result.explanation,
                'repeat_cycle':result.repeated,'manual_halt':store.is_operator_halted(),
                'unresolved_paper_record':store.has_unresolved_provider_order()}


def main(argv:Sequence[str]|None=None, *, env=None) -> int:
    parser=argparse.ArgumentParser(description='Unarmed hourly Signal Vault research; NEVER sends orders')
    parser.add_argument('--db',default='.data/offline-paper.sqlite3')
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--csv',help='Operator supplied UTC hourly historical CSV (unverified source)')
    group.add_argument('--public-data',action='store_true',help='Use read-only public Alpaca crypto bars')
    parser.add_argument('--confirm-read-only-market-data',action='store_true',
                        help='Explicitly permit network GETs for public market bars')
    parser.add_argument('--as-of',help='UTC timestamp, defaults to current UTC')
    parser.add_argument('--continuous',action='store_true',
                        help='Run once each hourly close. Requires --public-data and explicit GET opt-in.')
    args=parser.parse_args(argv)
    RuntimeConfig.from_environment(os.environ if env is None else env)
    if args.public_data and not args.confirm_read_only_market_data:
        parser.error('public network GET requires --confirm-read-only-market-data')
    if args.continuous and (not args.public_data or args.as_of):
        parser.error('continuous scheduling requires current-clock, public read-only data source')
    db=Path(args.db)
    if not db.is_file():
        parser.error('existing local SQLite journal required; run make init-local separately')
    with _single_writer(db):
        while True:
            at=_stamp(args.as_of) if args.as_of else datetime.now(timezone.utc)
            if args.continuous:
                close=at.replace(minute=0,second=0,microsecond=0)
                wake=close+timedelta(hours=1,seconds=3)
                time.sleep(max(0,(wake-at).total_seconds()))
                at=datetime.now(timezone.utc)
            try:
                result=one_cycle(db,as_of=at,
                        csv_path=Path(args.csv) if args.csv else None,
                        source=AlpacaPublicCryptoBars() if args.public_data else None)
                print(json.dumps(result,sort_keys=True),flush=True)
            except Exception as exc:
                # No secrets in logs or provider raw responses. The persistent
                # operator HALT remains independently enforced for any POST.
                print(json.dumps({'mode':'UNARMED_PAPER_RESEARCH',
                    'status':'ERROR_NO_TRADE', 'error_type':type(exc).__name__,
                    'external_orders_submitted':0}),flush=True)
                if not args.continuous:
                    return 2
            if not args.continuous:
                return 0

if __name__=='__main__':raise SystemExit(main())
