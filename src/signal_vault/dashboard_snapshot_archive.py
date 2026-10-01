"""Private atomic dashboard snapshot archive on the existing shared volume."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from .dashboard_namespace import (
    DASHBOARD_BASENAME,
    DASHBOARD_MAX_BYTES,
    DASHBOARD_SNAPSHOT_NAME,
)


def dashboard_root(base:Path, *, create:bool=False)->Path:
    if base.is_symlink() or not base.is_dir() or base.stat().st_mode&0o077:
        raise ValueError("shared evidence root must be private real directory")
    root=base/DASHBOARD_BASENAME
    if root.exists() or root.is_symlink():
        if root.is_symlink() or not root.is_dir():
            raise ValueError("dashboard namespace must be a real directory")
    elif create:
        root.mkdir(mode=0o700)
    if root.exists():
        root.chmod(0o700)
        if root.stat().st_mode&0o077:
            raise PermissionError("dashboard namespace must remain private")
    return root


def archive_dashboard_snapshot(
    snapshot:Mapping[str,object],
    *,
    base:Path,
)->Path:
    if not isinstance(snapshot,Mapping):
        raise ValueError("dashboard snapshot must be a mapping")
    root=dashboard_root(base,create=True)
    raw=(json.dumps(dict(snapshot),sort_keys=True,separators=(",",":"))+"\n").encode()
    if not 0<len(raw)<=DASHBOARD_MAX_BYTES:
        raise ValueError("dashboard snapshot outside bounded size")
    target=root/DASHBOARD_SNAPSHOT_NAME
    temp=root/(DASHBOARD_SNAPSHOT_NAME+".tmp")
    if target.is_symlink() or temp.is_symlink():
        raise ValueError("dashboard snapshot path cannot be symlink")
    flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(temp,flags,0o600)
    try:
        with os.fdopen(fd,"wb") as handle:
            os.fchmod(handle.fileno(),0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp,target)
        target.chmod(0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return target


def read_dashboard_snapshot(*,base:Path)->dict[str,object]:
    root=dashboard_root(base,create=False)
    path=root/DASHBOARD_SNAPSHOT_NAME
    if (
        not path.exists() or path.is_symlink() or not path.is_file()
        or path.stat().st_mode&0o077 or not 0<path.stat().st_size<=DASHBOARD_MAX_BYTES
    ):
        raise ValueError("safe dashboard snapshot unavailable")
    value=json.loads(path.read_text())
    if not isinstance(value,dict):
        raise ValueError("dashboard snapshot must be JSON object")
    return value
