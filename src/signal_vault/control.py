"""Local-only operator controls. This module has no broker/network imports."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from .paper_store import PersistentPaperOrderStore


def _db_path(env: dict[str, str] | os._Environ[str] | None = None) -> Path:
    values = os.environ if env is None else env
    raw = values.get("SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3").strip()
    if not raw or "\x00" in raw:
        raise ValueError("invalid paper database path")
    return Path(raw).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signal Vault local paper-runtime control")
    sub = parser.add_subparsers(dest="command", required=True)
    halt = sub.add_parser("halt", help="persistently block all new Signal Vault paper orders")
    halt.add_argument("--reason", required=True)
    sub.add_parser("resume", help="clear the local operator halt")
    sub.add_parser("status", help="print local halt status")
    args = parser.parse_args(argv)

    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with PersistentPaperOrderStore(path) as store:
        if args.command == "halt":
            store.set_operator_halt(True, reason=args.reason, at=datetime.now(timezone.utc))
        elif args.command == "resume":
            store.set_operator_halt(False, reason="", at=datetime.now(timezone.utc))
        halted, reason = store.operator_halt()
    print("HALTED" if halted else "RUNNING", reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
