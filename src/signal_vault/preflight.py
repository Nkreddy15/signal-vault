"""Offline/local persistence startup gates for Signal Vault PAPER runtime.

These checks never load broker credentials, never perform provider reads and
never enable order submission. They verify only the local journal and expose a
read-only operator-oriented summary where requested.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from .operator_view import OperatorSnapshotError, read_local_paper_snapshot

MIN_FREE_BYTES = 128 * 1024 * 1024


class PreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreflightReport:
    database_exists: bool
    database_owner_only: bool
    sqlite_integrity_ok: bool
    sqlite_foreign_keys_on: bool
    sqlite_journal_mode: str
    free_bytes: int

    @property
    def ready(self) -> bool:
        return (self.database_exists and self.database_owner_only and
                self.sqlite_integrity_ok and self.sqlite_foreign_keys_on and
                self.sqlite_journal_mode.lower() == "wal" and self.free_bytes > 0)


def _validated_path(db_path: str | Path) -> Path:
    path = Path(db_path).expanduser()
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise PreflightError("paper database unavailable, missing or symbolic link")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise PreflightError("paper database must be a regular file")
    if hasattr(os, "geteuid") and st.st_uid != os.geteuid():
        raise PreflightError("paper journal owner differs from process")
    return path


def check_sqlite_runtime(db_path: str | Path, *, min_free_bytes: int = 100 * 1024 * 1024) -> PreflightReport:
    """Strict persistence gate used before the unattended paper worker runs."""
    if not isinstance(min_free_bytes, int) or min_free_bytes < 0:
        raise ValueError("minimum free space cannot be negative")
    try:
        path = _validated_path(db_path)
    except PreflightError as exc:
        raise ValueError(str(exc)) from exc
    mode = stat.S_IMODE(path.stat().st_mode)
    owner_only = (mode & 0o077) == 0
    usage = shutil.disk_usage(path.parent)
    if usage.free < min_free_bytes:
        raise RuntimeError("insufficient free disk space for paper runtime")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        # foreign_keys is connection-local. Verify SQLite supports/enables it;
        # each write connection independently enables it on construction.
        conn.execute("PRAGMA foreign_keys=ON")
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
        integrity_rows = tuple(row[0] for row in conn.execute("PRAGMA quick_check"))
        integrity = integrity_rows == ("ok",)
    finally:
        conn.close()
    report = PreflightReport(True, owner_only, integrity, fk, journal, usage.free)
    if not owner_only:
        raise PermissionError("paper database must not be group/world accessible")
    if not integrity:
        raise RuntimeError("SQLite quick_check failed")
    if not fk:
        raise RuntimeError("SQLite foreign-key support unavailable")
    if journal.lower() != "wal":
        raise RuntimeError("SQLite WAL mode required for paper runtime")
    return report


def inspect_paper_runtime(db_path: str | Path, *, minimum_free_bytes: int = MIN_FREE_BYTES) -> dict[str, object]:
    """Read-only human/operator preflight; an unresolved order never authorizes retry."""
    if not isinstance(minimum_free_bytes, int) or minimum_free_bytes < 0:
        raise ValueError("invalid disk-space threshold")
    path = _validated_path(db_path)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PreflightError("paper journal must not be group/world-accessible")
    if shutil.disk_usage(path.parent).free < minimum_free_bytes:
        raise PreflightError("insufficient disk space for safe paper persistence")
    try:
        report = check_sqlite_runtime(path, min_free_bytes=minimum_free_bytes)
        snapshot = read_local_paper_snapshot(path)
    except (sqlite3.Error, OperatorSnapshotError, ValueError, RuntimeError, PermissionError) as exc:
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
        "sqlite_wal": report.sqlite_journal_mode.lower() == "wal",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Signal Vault read-only local PAPER startup preflight")
    parser.add_argument("--db", default=os.environ.get(
        "SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3"))
    parser.add_argument("--minimum-free-mib", type=int, default=128)
    args = parser.parse_args(argv)
    try:
        result = inspect_paper_runtime(
            args.db, minimum_free_bytes=args.minimum_free_mib * 1024 * 1024)
    except (PreflightError, ValueError) as exc:
        print(json.dumps({"status": "PREFLIGHT_BLOCKED", "reason": str(exc),
                          "order_submission": "DISABLED"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
