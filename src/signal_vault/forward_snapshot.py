"""Operator-only, OFFLINE snapshot and isolated verification of forward evidence.

Copies one consistent SQLite observation-journal snapshot plus the exact original
CSV/manifest files referenced by that snapshot. No broker/client/network,
scheduling, overwrite of active evidence, strategy decision or real restoration.

A backup SHA manifest is local/unsigned: consistency evidence, not independently
authenticated or an encrypted/off-machine disaster-recovery copy.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from .forward_evidence_audit import (
    _archive_path, _closed_utc, _private_regular, audit_forward_evidence,
)
from .runtime_lock import RuntimeFileLock

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
MANIFEST_FILE = "snapshot.manifest.json"
SNAPSHOT_DB = "observations.sqlite3"


def _sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _snapshot_location(root: str | Path, name: str) -> tuple[Path, Path]:
    base = Path(root).expanduser()
    if base.is_symlink() or not base.is_dir():
        raise ValueError("local forward evidence root must be a real directory")
    if not NAME_RE.fullmatch(name):
        raise ValueError("snapshot name must be simple, bounded, and contain no paths")
    backups = base / "backups"
    if backups.is_symlink() or (backups.exists() and not backups.is_dir()):
        raise ValueError("backup parent must be a real directory, not a symlink")
    return backups, backups / name


def _copy_private(source: Path, target: Path) -> str:
    _private_regular(source, "forward evidence input")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # No shared inode/hard links: the evidence snapshot must be independent.
    with source.open("rb") as reader:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as writer:
                os.fchmod(writer.fileno(), 0o600)
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return _sha_file(target)


def _referenced_csvs(snapshot_db: Path, folder: Path) -> tuple[Path, ...]:
    """Snapshot DB, not a potentially advancing ORIGINAL DB, owns file selection."""
    conn = sqlite3.connect(snapshot_db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        first = conn.execute(
            "SELECT first_start FROM forward_state WHERE singleton=1").fetchone()
        if first is None:
            raise ValueError("snapshot journal has no bootstrap anchor")
        first_close = _closed_utc(first[0], name="bootstrap start") + timedelta(hours=72)
        other = tuple(_closed_utc(x[0], name="prospective close")
                      for x in conn.execute(
                          "SELECT close_utc FROM forward_observations ORDER BY start_utc"))
    finally:
        conn.close()
    dates = (first_close,) + other
    if len(set(dates)) != len(dates):
        raise ValueError("duplicate archived capture boundary")
    return tuple(_archive_path(folder, stamp) for stamp in dates)


def _verify_folder(folder: Path) -> dict:
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("snapshot must be an existing nonsymlink directory")
    if folder.stat().st_mode & 0o077:
        raise PermissionError("snapshot directory must be owner-only (0700)")
    manifest_file = folder / MANIFEST_FILE
    _private_regular(manifest_file, "snapshot manifest")
    meta = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (not isinstance(meta, dict) or set(meta) != {
        "kind", "schema_version", "created_utc", "file_sha256",
        "prospective_observations_verified",
    } or meta["kind"] != "OFFLINE_FORWARD_EVIDENCE_SNAPSHOT"
            or type(meta["schema_version"]) is not int or meta["schema_version"] != 1
            or not isinstance(meta["file_sha256"], dict)
            or type(meta["prospective_observations_verified"]) is not int):
        raise ValueError("invalid snapshot metadata")
    created = datetime.fromisoformat(meta["created_utc"])
    if created.tzinfo is None or created.utcoffset() != timedelta(0):
        raise ValueError("snapshot timestamp must be UTC")
    expected_paths = set(meta["file_sha256"])
    expected_paths.add(MANIFEST_FILE)
    actual_paths = {str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file()}
    dirs = {str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_dir()}
    if dirs != {"captures"} or expected_paths != actual_paths:
        raise ValueError("snapshot contains missing, unexpected or misnamed evidence")
    for relative, digest in meta["file_sha256"].items():
        if (not isinstance(relative, str) or
                relative != SNAPSHOT_DB and not re.fullmatch(
                    r"captures/btcusd_72h_end_\d{8}T\d{4}Z\.csv(?:\.manifest\.json)?",
                    relative)
                or not isinstance(digest, str) or
                not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid snapshot file manifest entry")
        target = folder / relative
        _private_regular(target, "snapshot file " + relative)
        if _sha_file(target) != digest:
            raise ValueError("snapshot file SHA-256 mismatch: " + relative)
    report = audit_forward_evidence(root=folder, db=folder/SNAPSHOT_DB)
    if report["prospective_observations_verified"] != meta["prospective_observations_verified"]:
        raise ValueError("snapshot manifest observation count disagrees with reconstructed chain")
    required_csv = _referenced_csvs(folder/SNAPSHOT_DB, folder)
    expected_evidence = {SNAPSHOT_DB}
    for csv in required_csv:
        expected_evidence.add(str(csv.relative_to(folder)))
        expected_evidence.add(str(csv.with_suffix(csv.suffix + ".manifest.json").relative_to(folder)))
    if set(meta["file_sha256"]) != expected_evidence:
        raise ValueError("snapshot does not contain exactly the referenced journal evidence")
    return {
        "kind": "OFFLINE_ISOLATED_FORWARD_SNAPSHOT_VERIFICATION",
        "result": "PASS_INTERNAL_CONSISTENCY_ONLY",
        "prospective_observations_verified": report["prospective_observations_verified"],
        "csv_manifest_pairs_verified": report["archived_csv_manifest_pairs_verified"],
        "file_hashes_verified": len(meta["file_sha256"]),
        "active_journal_modified": False,
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
        "warning": "Local, unsigned, unencrypted copy; this is an isolated verification drill, NOT production restoration.",
    }


def verify_forward_snapshot(*, name: str, root: str | Path = "data/forward") -> dict:
    _, target = _snapshot_location(root, name)
    report = _verify_folder(target)
    report["snapshot_path"] = str(target)
    return report


def create_forward_snapshot(*, root: str | Path = "data/forward",
                            db: str | Path | None = None,
                            name: str | None = None) -> dict:
    """Operator-invoked backup: validate source; SQLite online snapshot; copy; audit; publish.

    The current forward journal remains in place. A concurrent new observation
    can never be claimed as part of this snapshot unless it appears in the
    consistent snapshotted SQLite database.
    """
    base = Path(root).expanduser()
    if name is None:
        name = datetime.now(timezone.utc).strftime("forward_%Y%m%dT%H%M%S_%fZ")
    backups, target = _snapshot_location(base, name)
    source_db = base/SNAPSHOT_DB if db is None else Path(db).expanduser()
    if source_db.is_symlink() or not source_db.resolve().is_relative_to(base.resolve()):
        raise ValueError("forward journal must be under its own data/forward root")
    _private_regular(source_db, "source forward journal")
    backups.mkdir(mode=0o700, exist_ok=True)
    if backups.stat().st_mode & 0o077:
        raise PermissionError("forward backups directory must be owner-only (0700)")
    with RuntimeFileLock(backups/".snapshot.lock"):
        if target.exists() or target.is_symlink():
            raise FileExistsError("refusing to overwrite an existing forward snapshot")
        # First verify real raw evidence, before exporting anything.
        audit_forward_evidence(root=base, db=source_db)
        stage = Path(tempfile.mkdtemp(prefix=".pending-forward-", dir=backups))
        os.chmod(stage, 0o700)
        try:
            dest_db = stage/SNAPSHOT_DB
            source = sqlite3.connect(source_db.resolve().as_uri()+"?mode=ro",
                                     uri=True, isolation_level=None, timeout=10)
            try:
                source.execute("PRAGMA query_only=ON")
                destination = sqlite3.connect(dest_db, timeout=10)
                try:
                    source.backup(destination, pages=64, sleep=0.1)
                    if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        raise ValueError("consistent SQLite backup failed integrity check")
                finally:
                    destination.close()
            finally:
                source.close()
            os.chmod(dest_db, 0o600)
            # Select immutable CSV pairs referenced by the CONSISTENT snapshot.
            digests = {SNAPSHOT_DB: _sha_file(dest_db)}
            for archived_csv in _referenced_csvs(dest_db, base):
                for src in (archived_csv, archived_csv.with_suffix(
                        archived_csv.suffix + ".manifest.json")):
                    rel = src.relative_to(base)
                    digests[str(rel)] = _copy_private(src, stage/rel)
            offline = audit_forward_evidence(root=stage, db=dest_db)
            meta = {
                "kind": "OFFLINE_FORWARD_EVIDENCE_SNAPSHOT",
                "schema_version": 1,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "file_sha256": dict(sorted(digests.items())),
                "prospective_observations_verified":
                    offline["prospective_observations_verified"],
            }
            meta_file = stage/MANIFEST_FILE
            with meta_file.open("x", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(meta, stream, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            proof = _verify_folder(stage)
            if target.exists() or target.is_symlink():
                raise FileExistsError("snapshot destination appeared; refusing replacement")
            os.rename(stage, target)
            directory_fd = os.open(backups, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    proof.update({
        "kind": "OFFLINE_FORWARD_SNAPSHOT_CREATED_AND_ISOLATED_VERIFIED",
        "snapshot_path": str(target),
        "original_journal_path": str(source_db),
        "original_journal_modified": False,
        "snapshot_overwrite": "DISABLED",
    })
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local owner-only forward-evidence backup + isolated read-only verification")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create", action="store_true",
                       help="Create one immutable-name local snapshot; never replace originals")
    group.add_argument("--verify", metavar="SNAPSHOT_NAME",
                       help="Verify a previously saved local snapshot without writing")
    parser.add_argument("--db", default=None, help="Optional already-bootstrapped source segment for --create")
    args = parser.parse_args()
    if args.verify is not None:
        if args.db is not None:
            parser.error("--db applies only to --create")
        result = verify_forward_snapshot(name=args.verify)
    else:
        result = create_forward_snapshot(db=args.db)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
