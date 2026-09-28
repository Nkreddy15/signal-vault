"""Crash-safe local SQLite backups for the single-host paper pilot.

Backups do not replace provider reconciliation or off-host disaster recovery.
They provide a verified local recovery point before/while the prototype remains
single-process SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
import tempfile


@dataclass(frozen=True)
class BackupResult:
    database_path: Path
    manifest_path: Path
    sha256: str
    created_utc: str


def create_sqlite_backup(source: str | Path, backup_dir: str | Path, *, at: datetime,
                         label: str = "daily") -> BackupResult:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware backup time required")
    if not label or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in label.lower()):
        raise ValueError("unsafe backup label")
    src = Path(source).expanduser()
    root = Path(backup_dir).expanduser()
    if not src.exists() or not src.is_file() or src.is_symlink():
        raise ValueError("backup source must be a regular non-symlink database")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("backup directory must not be a symlink")
    stamp = at.astimezone(timezone.utc)
    basename = f"paper-{label}-{stamp:%Y%m%dT%H%M%SZ}.sqlite3"
    target = root / basename
    if target.exists():
        raise FileExistsError("refusing to overwrite existing database backup")
    fd, temporary_raw = tempfile.mkstemp(prefix=".backup-", suffix=".sqlite3", dir=root)
    os.close(fd)
    temporary = Path(temporary_raw)
    try:
        source_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=10)
        dest_conn = sqlite3.connect(str(temporary), isolation_level=None, timeout=10)
        try:
            source_conn.backup(dest_conn)
            check = tuple(row[0] for row in dest_conn.execute("PRAGMA quick_check"))
            if check != ("ok",):
                raise RuntimeError("backup integrity check failed")
        finally:
            dest_conn.close(); source_conn.close()
        os.chmod(temporary, 0o600)
        digest = sha256(temporary.read_bytes()).hexdigest()
        os.replace(temporary, target); os.chmod(target, 0o600)
        manifest = target.with_suffix(target.suffix + ".manifest.json")
        payload = {
            "schema_version": 1,
            "kind": "SIGNAL_VAULT_SQLITE_BACKUP",
            "database_file": target.name,
            "database_sha256": digest,
            "created_utc": stamp.isoformat(),
        }
        manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(manifest, 0o600)
        return BackupResult(target, manifest, digest, stamp.isoformat())
    except BaseException:
        try: temporary.unlink()
        except FileNotFoundError: pass
        raise


def verify_sqlite_backup(database_path: str | Path, manifest_path: str | Path) -> bool:
    db = Path(database_path); manifest = Path(manifest_path)
    if any(p.is_symlink() or not p.is_file() for p in (db, manifest)):
        raise ValueError("backup verification requires regular files")
    data = json.loads(manifest.read_text())
    expected = data.get("database_sha256")
    if not isinstance(expected, str) or len(expected) != 64 or data.get("database_file") != db.name:
        raise ValueError("malformed backup manifest")
    if sha256(db.read_bytes()).hexdigest() != expected:
        return False
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        return tuple(row[0] for row in conn.execute("PRAGMA quick_check")) == ("ok",)
    finally:
        conn.close()


class DailyBackupManager:
    """At most one successful backup per UTC day per daemon process."""
    def __init__(self, source: str | Path, backup_dir: str | Path) -> None:
        self.source = Path(source).expanduser()
        self.backup_dir = Path(backup_dir).expanduser()
        self._last_date = None

    def maybe_backup(self, *, at: datetime) -> BackupResult | None:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware backup schedule time required")
        today = at.astimezone(timezone.utc).date()
        if self._last_date == today:
            return None
        result = create_sqlite_backup(self.source, self.backup_dir, at=at, label="daily")
        self._last_date = today
        return result
