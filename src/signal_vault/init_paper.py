"""Explicit local-only creation of a private $100 PAPER journal; no broker calls."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from .paper_store import PersistentPaperOrderStore
from .preflight import inspect_paper_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize LOCAL PAPER-only journal")
    parser.add_argument("--db", default=os.environ.get("SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3"))
    args = parser.parse_args(argv)
    target = Path(args.db).expanduser()
    if target.is_symlink():
        raise ValueError("refusing symbolic link journal path")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = target.parent
    if parent.is_symlink() or stat.S_IMODE(parent.stat().st_mode) & 0o022:
        raise ValueError("paper journal directory must not be a symlink or group/world-writable")
    with PersistentPaperOrderStore(target) as store:
        store.logical_account()
    print(json.dumps(inspect_paper_runtime(target), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
