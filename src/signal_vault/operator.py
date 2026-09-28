"""Local audited control-plane CLI. No brokerage or network capability."""
from __future__ import annotations

import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from typing import Sequence

from .paper_store import PersistentPaperOrderStore


def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Control only local Signal Vault paper submission state")
    parser.add_argument("--db",required=True,help="EXISTING local Signal Vault SQLite path")
    cmd=parser.add_subparsers(dest="action",required=True)
    cmd.add_parser("status",help="Show persistent local paper-only halt and unresolved order count")
    halt=cmd.add_parser("halt",help="Immediately block NEW paper submissions (not a cancellation)")
    halt.add_argument("--reason",required=True)
    resume=cmd.add_parser("resume",help="Clear manual halt only after all orders reconcile")
    resume.add_argument("--reason",required=True)
    args=parser.parse_args(argv)
    db=Path(args.db)
    if not db.is_file():
        parser.error("existing local .sqlite database required; refusing to create a new database")
    with PersistentPaperOrderStore(db) as store:
        if args.action=="halt":
            store.set_operator_halt(True,reason=args.reason,at=datetime.now(timezone.utc))
        elif args.action=="resume":
            if not store.is_operator_halted():
                raise ValueError("cannot resume: manual halt was never engaged")
            store.set_operator_halt(False,reason=args.reason,at=datetime.now(timezone.utc))
        info={"mode":"PAPER_ONLY", "operator_halt":store.is_operator_halted(),
              "unresolved_order":store.has_unresolved_provider_order()}
        print(json.dumps(info,sort_keys=True))
    return 0

if __name__=="__main__":raise SystemExit(main())
