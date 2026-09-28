"""Consistent, private SQLite snapshot backup for the PAPER ledger.

No broker integration. The backup is for forensic/recovery review and MUST NOT
be restored as an automatically trade-enabled journal: provider orders placed
since a snapshot may still exist and require reconciliation before new orders.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile

from .preflight import inspect_paper_runtime, MIN_FREE_BYTES


@dataclass(frozen=True)
class BackupResult:
    path: str
    sha256: str
    bytes: int
    mode: str = "ALPACA_PAPER_ONLY"
    automatic_trading_resume_allowed: bool = False


def private_paper_backup(db: str | Path, destination: str | Path) -> BackupResult:
    """Take one SQLite online-backup snapshot without replacing an existing path.

    The SQLite backup API preserves a consistent view of the main DB plus WAL
    while another process is writing; unlike copying the .db file alone.
    """
    source = Path(db).expanduser()
    target = Path(destination).expanduser()
    if not target.name or target.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("destination must have .db, .sqlite or .sqlite3 extension")
    if target.exists() or target.is_symlink():
        raise FileExistsError("refusing to overwrite an existing backup")
    if source.resolve(strict=False) == target.resolve(strict=False):
        raise ValueError("cannot back up database onto itself")
    # Performs owner/mode, integrity and logical-state checks without provider calls.
    inspect_paper_runtime(source)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.parent.is_symlink() or stat.S_IMODE(target.parent.stat().st_mode) & 0o077:
        raise ValueError("backup directory must be private and not a symlink")
    required = max(MIN_FREE_BYTES, source.stat().st_size * 2 + (16 * 1024 * 1024))
    if shutil.disk_usage(target.parent).free < required:
        raise OSError("insufficient free space for a safe consistent backup")

    fd, temporary_name = tempfile.mkstemp(dir=target.parent, prefix=".signal-vault-backup-", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        os.close(fd)
        fd = -1
        origin = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True,
                                 timeout=10)
        try:
            origin.execute("PRAGMA query_only=ON")
            copy = sqlite3.connect(str(temporary), timeout=10)
            try:
                origin.backup(copy, pages=64, sleep=0.1)
                row = copy.execute("PRAGMA quick_check").fetchone()
                if row is None or row[0] != "ok":
                    raise ValueError("backup database failed SQLite integrity check")
                copy.commit()
            finally:
                copy.close()
        finally:
            origin.close()
        with temporary.open("rb") as handle:
            digest = sha256()
            length = 0
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
                length += len(block)
            os.fsync(handle.fileno())
        # Atomic exclusive publication. os.replace would silently clobber backups.
        os.link(temporary, target, follow_symlinks=False)
        directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return BackupResult(path=str(target), sha256=digest.hexdigest(), bytes=length)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consistent private PAPER-only SQLite backup")
    parser.add_argument("--db", default=os.environ.get("SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3"))
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    try:
        result = private_paper_backup(args.db, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"status": "BACKUP_BLOCKED", "reason": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
