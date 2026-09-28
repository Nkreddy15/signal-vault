"""Offline startup gate for local Signal Vault PAPER journal; never loads broker keys."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat

from .operator_view import OperatorSnapshotError, read_local_paper_snapshot

MIN_FREE_BYTES = 128 * 1024 * 1024


class PreflightError(RuntimeError):
    pass


def inspect_paper_runtime(db_path: str | Path, *, minimum_free_bytes: int = MIN_FREE_BYTES) -> dict[str, object]:
    """Read-only validation; never creates or fixes the DB on startup.

    An unresolved paper order is *reported* rather than treated as authorization
    for a retry; the order-recovery state machine must lookup the same client ID.
    """
    if not isinstance(minimum_free_bytes, int) or minimum_free_bytes < 0:
        raise ValueError("invalid disk-space threshold")
    source = Path(db_path).expanduser()
    if source.is_symlink() or not source.exists() or not source.is_file():
        raise PreflightError("paper database unavailable, missing or symbolic link")
    st = source.stat()
    if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) & 0o077:
        raise PreflightError("paper journal must not be group/world-accessible")
    if hasattr(os, "geteuid") and st.st_uid != os.geteuid():
        raise PreflightError("paper journal owner differs from process")
    if shutil.disk_usage(source.parent).free < minimum_free_bytes:
        raise PreflightError("insufficient disk space for safe paper persistence")
    try:
        con = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0)
        try:
            con.execute("PRAGMA query_only=ON")
            result = con.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise PreflightError("SQLite quick_check did not succeed")
        finally:
            con.close()
        snapshot = read_local_paper_snapshot(source)
    except (sqlite3.Error, OperatorSnapshotError) as exc:
        raise PreflightError("paper database failed integrity/read-only state checks") from exc
    return {
        "status": "READ_ONLY_PREFLIGHT_OK",
        "mode": "ALPACA_PAPER_ONLY",
        "operator_halted": snapshot["operator_halted"],
        "provider_lookup_required": snapshot["paper_orders"]["unresolved"] > 0,
        "unresolved_paper_orders": snapshot["paper_orders"]["unresolved"],
        "paper_order_post_enabled": False,
        "authenticated_provider_read_performed": False,
        "live_trading_available": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signal Vault read-only local PAPER startup preflight")
    parser.add_argument("--db", default=os.environ.get("SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3"))
    parser.add_argument("--minimum-free-mib", type=int, default=128)
    args = parser.parse_args(argv)
    try:
        result = inspect_paper_runtime(args.db, minimum_free_bytes=args.minimum_free_mib * 1024 * 1024)
    except (PreflightError, ValueError) as exc:
        print(json.dumps({"status": "PREFLIGHT_BLOCKED", "reason": str(exc),
                          "order_submission": "DISABLED"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
