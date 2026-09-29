"""Offline Phase 2O recovery/fault drill using only disposable snapshot COPIES.

Never opens, restores, or mutates the active data/forward/observations.sqlite3.
Never modifies a saved backup. Deliberate corruption occurs ONLY in separate
temporary, owner-private directories under data/forward/drills/ which are
automatically deleted, even on error. No API client or trading dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .forward_evidence_audit import audit_forward_evidence
from .forward_snapshot import (
    MANIFEST_FILE, SNAPSHOT_DB, _copy_private, _sha_file,
    _snapshot_location, _verify_folder,
)
from .runtime_lock import RuntimeFileLock

MIN_FREE_BYTES = 128 * 1024 * 1024
FAULT_NAMES = ("altered_csv", "altered_source_manifest",
               "altered_journal_metric", "missing_capture_manifest")


def _copy_isolated_verified_snapshot(source: Path, scratch: Path) -> dict:
    """Copy all snapshot files onto independent inodes; verify the isolated clone."""
    scratch.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(scratch, 0o700)
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            raise ValueError("source snapshot contains a symbolic link")
        if item.is_file():
            target = scratch / item.relative_to(source)
            _copy_private(item, target)
    return _verify_folder(scratch)


def _mutate_disposable_copy(folder: Path, fault: str) -> None:
    captures = folder / "captures"
    if fault == "altered_csv":
        source = sorted(captures.glob("*.csv"))[0]
        with source.open("ab") as stream:
            stream.write(b"\n# deliberately damaged DISPOSABLE drill copy\n")
        return
    if fault == "altered_source_manifest":
        source = sorted(captures.glob("*.csv.manifest.json"))[0]
        value = json.loads(source.read_text(encoding="utf-8"))
        value["source"] = "synthetic_disposable_fault"
        source.write_text(json.dumps(value), encoding="utf-8")
        return
    if fault == "altered_journal_metric":
        with sqlite3.connect(folder / SNAPSHOT_DB) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM forward_observations").fetchone()[0]
            if count:
                connection.execute(
                    "UPDATE forward_observations SET close_usd='1' "
                    "WHERE start_utc=(SELECT MAX(start_utc) FROM forward_observations)")
            else:
                connection.execute("UPDATE forward_state SET bootstrap_sha256=?", ("0"*64,))
        return
    if fault == "missing_capture_manifest":
        source = sorted(captures.glob("*.csv.manifest.json"))[0]
        source.unlink()
        return
    raise ValueError("unsupported disposable fault scenario")


def run_forward_recovery_drill(*, name: str,
                               root: str | Path = "data/forward") -> dict:
    """Prove snapshot -> scratch chain opens AND four independent faults fail closed.

    Does not actually restore an operational journal or any provider state.
    Testing helper is explicitly named "drill", never "restore".
    """
    base = Path(root).expanduser()
    backups, snapshot = _snapshot_location(base, name)
    if backups.is_symlink() or not backups.is_dir() or backups.stat().st_mode & 0o077:
        raise PermissionError("snapshot parent must be a private real directory (0700)")
    initial = _verify_folder(snapshot)  # before copying anything; fail closed
    source_files = tuple(sorted(p for p in snapshot.rglob("*") if p.is_file()))
    if len(source_files) != initial["file_hashes_verified"] + 1:
        raise ValueError("source snapshot file inventory is inconsistent")
    original_hashes = {str(p.relative_to(snapshot)): _sha_file(p) for p in source_files}
    if any(p.is_symlink() for p in source_files):
        raise ValueError("source snapshot is symbolic-linked")
    scratch_root = base / "drills"
    if scratch_root.is_symlink() or (scratch_root.exists() and not scratch_root.is_dir()):
        raise ValueError("local drill directory must not be symlinked")
    scratch_root.mkdir(mode=0o700, exist_ok=True)
    if scratch_root.stat().st_mode & 0o077:
        raise PermissionError("drill parent must be private (0700)")
    # One clean clone and one fault clone are simultaneously present, not five.
    input_bytes = sum(p.stat().st_size for p in source_files)
    required = max(MIN_FREE_BYTES, input_bytes * 3 + 16 * 1024 * 1024)
    if shutil.disk_usage(scratch_root).free < required:
        raise OSError("insufficient disk space for independent recovery/fault drill")

    with RuntimeFileLock(scratch_root / ".recovery-drill.lock"):
        with tempfile.TemporaryDirectory(prefix=".isolated-recovery-", dir=scratch_root) as tmp:
            # TemporaryDirectory already creates the root with 0700 mode;
            # _copy_isolated_verified_snapshot requires a NEW child folder.
            clean = Path(tmp) / "recovered"
            proof = _copy_isolated_verified_snapshot(snapshot, clean)
            # Prove the original journal/manifest and every original capture
            # are NOT hard-linked to scratch and can survive scratch mutations.
            for relative in original_hashes:
                original = snapshot / relative
                copied = clean / relative
                if original.stat().st_ino == copied.stat().st_ino and (
                        original.stat().st_dev == copied.stat().st_dev):
                    raise ValueError("scratch recovery unexpectedly shares original inode")
            rejections: dict[str, str] = {}
            for fault in FAULT_NAMES:
                with tempfile.TemporaryDirectory(prefix=".isolated-fault-",
                                                 dir=scratch_root) as bad_tmp:
                    damaged = Path(bad_tmp) / "snapshot-copy"
                    _copy_isolated_verified_snapshot(snapshot, damaged)
                    _mutate_disposable_copy(damaged, fault)
                    # Both the raw archived-data audit and the outer snapshot
                    # integrity layer MUST reject corruption independently.
                    failures = 0
                    for check in (
                        lambda: audit_forward_evidence(root=damaged,
                                                       db=damaged / SNAPSHOT_DB),
                        lambda: _verify_folder(damaged),
                    ):
                        try:
                            check()
                        except (ValueError, PermissionError, sqlite3.Error, OSError):
                            failures += 1
                    if failures != 2:
                        raise AssertionError(
                            "DISPOSABLE FAULT WAS NOT REJECTED by both verification layers: " + fault)
                    rejections[fault] = "REJECTED_BY_BOTH_INDEPENDENT_CHECKS"
            # Clean recovery must STILL be valid after all separate fault drills.
            _verify_folder(clean)
        # Temp folders are removed; verify the original snapshot was not changed.
        after = {str(p.relative_to(snapshot)): _sha_file(p) for p in source_files}
        if after != original_hashes:
            raise RuntimeError("original snapshot unexpectedly differs after scratch recovery drill")
        if any(scratch_root.glob(".isolated-recovery-*")) or any(
                scratch_root.glob(".isolated-fault-*")):
            raise RuntimeError("temporary drill files unexpectedly remain")
    return {
        "kind": "OFFLINE_DISPOSABLE_FORWARD_RECOVERY_AND_FAULT_DRILL",
        "result": "PASS_ISOLATED_RECONSTRUCTION_AND_FAULT_REJECTION",
        "source_snapshot_name": name,
        "recovered_observations_verified": proof["prospective_observations_verified"],
        "recovered_capture_pairs_verified": proof["csv_manifest_pairs_verified"],
        "original_snapshot_file_hashes_unchanged": True,
        "snapshot_files_checked": len(source_files),
        "injected_faults_rejected": rejections,
        "disposable_evidence_cleanup": "COMPLETE",
        "active_journal_opened_or_modified": False,
        "snapshot_overwritten": False,
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
        "automatic_scheduling": "DISABLED",
        "warning": "Same-device unsigned snapshot, offline scratch simulation only; NOT a production restore or verified provider trading.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manual OFFLINE, scratch-only evidence recovery/fault drill; originals never restored over")
    parser.add_argument("--snapshot", required=True,
                        help="Exact existing snapshot FOLDER BASENAME under data/forward/backups")
    args = parser.parse_args()
    print(json.dumps(run_forward_recovery_drill(name=args.snapshot), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
