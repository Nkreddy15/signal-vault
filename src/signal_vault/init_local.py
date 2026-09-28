"""Explicit owner-invoked initialization of a NEW offline SQLite state file."""
from __future__ import annotations

import argparse
from pathlib import Path
from .paper_store import PersistentPaperOrderStore


def main() -> None:
    parser=argparse.ArgumentParser(description="Initialize private local development state, NO broker connection")
    parser.add_argument('--db',default='.data/offline-paper.sqlite3')
    args=parser.parse_args()
    path=Path(args.db)
    if path.exists():
        parser.error('target already exists; refusing to overwrite a journal or credentials')
    path.parent.mkdir(parents=True,exist_ok=True)
    with PersistentPaperOrderStore(path) as store:
        if store.is_operator_halted():
            raise ValueError('unexpected initial state')
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print(f'Created LOCAL DEVELOPMENT SQLite journal: {path}')
    print('No broker connected, no orders created, no balances or profits claimed.')

if __name__=='__main__':main()
