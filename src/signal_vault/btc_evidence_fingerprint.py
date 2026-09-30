"""Read-only bounded fingerprint of original BTC evidence, excluding sidecar.

Used immediately AFTER the existing BTC-first collector finishes and again
AFTER the six-crypto sidecar stage. A mismatch proves the sidecar interval
coincided with a mutation outside its dedicated child namespace.

This is an integrity tripwire, not a backup or external signature. It never
reads environment variables, network, broker accounts or order APIs and
never writes, chmods, repairs, deletes or migrates the evidence tree.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

MAX_BTC_FILES=20_000
MAX_BTC_BYTES=384*1024*1024
READ_CHUNK=1024*1024


class BtcEvidencePermissionError(PermissionError):
    """Safe permission diagnostic containing only relative path/type/mode."""
    def __init__(self,*,relative_path:str,kind:str,mode:int):
        self.relative_path=relative_path
        self.kind=kind
        self.mode=mode
        super().__init__(f"owner-private permission required for {kind}: {relative_path}")


def fingerprint_btc_evidence_tree(
    root:Path,
    *,
    excluded_sidecar_name:str,
) -> dict[str,object]:
    base=Path(root)
    if (base.is_symlink() or not base.is_dir() or
            base.stat().st_mode&0o077):
        raise ValueError("BTC evidence root must remain a real owner-private directory")
    if (not isinstance(excluded_sidecar_name,str) or
            excluded_sidecar_name in ("",".","..") or
            "/" in excluded_sidecar_name or "\\" in excluded_sidecar_name):
        raise ValueError("exact single child sidecar name required")
    excluded=base/excluded_sidecar_name
    records=[]
    total=0
    files=0
    directories=0
    for item in sorted(base.rglob("*"),key=lambda p:p.relative_to(base).as_posix()):
        if item==excluded or excluded in item.parents:
            continue
        if item.is_symlink():
            raise ValueError("symlink forbidden in original BTC evidence tree")
        relative=item.relative_to(base).as_posix()
        mode=item.stat().st_mode&0o777
        if item.is_dir():
            if mode&0o077:
                raise BtcEvidencePermissionError(relative_path=relative,kind="directory",mode=mode)
            directories+=1
            records.append({
                "kind":"directory","path":relative,"mode":oct(mode),
            })
            continue
        if not item.is_file():
            raise ValueError("unexpected inode in original BTC evidence tree")
        if mode&0o077:
            raise BtcEvidencePermissionError(relative_path=relative,kind="file",mode=mode)
        size=item.stat().st_size
        if size<0:
            raise ValueError("invalid BTC evidence file size")
        files+=1
        total+=size
        if files>MAX_BTC_FILES or total>MAX_BTC_BYTES:
            raise ValueError("bounded BTC integrity scan limit exceeded")
        digest=hashlib.sha256()
        with item.open("rb") as source:
            while True:
                chunk=source.read(READ_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
        records.append({
            "kind":"file","path":relative,"mode":oct(mode),
            "size":size,"sha256":digest.hexdigest(),
        })
    canonical=(json.dumps(records,sort_keys=True,separators=(",",":"))+"\n").encode()
    return {
        "kind":"OFFLINE_ORIGINAL_BTC_EVIDENCE_TREE_FINGERPRINT",
        "tree_sha256":hashlib.sha256(canonical).hexdigest(),
        "file_count":files,
        "directory_count":directories,
        "total_file_bytes":total,
        "excluded_sidecar_child":excluded_sidecar_name,
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "filesystem_mutation":"NONE",
    }
