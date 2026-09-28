"""Single-process lock for the paper runtime.

The SQLite journal uses database transactions, but that alone is not a scheduler
leadership mechanism. This lock prevents two Signal Vault paper daemons from
intentionally operating the same database at once on Unix hosts.
"""
from __future__ import annotations

from pathlib import Path
import errno
import fcntl
import os


class RuntimeAlreadyLocked(RuntimeError):
    pass


class RuntimeFileLock:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._fd: int | None = None

    def acquire(self) -> "RuntimeFileLock":
        if self._fd is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EMLINK}:
                raise ValueError("runtime lock path must not be a symlink") from exc
            raise
        try:
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeAlreadyLocked("another Signal Vault paper runtime holds the lock") from exc
            os.ftruncate(fd, 0)
            os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
            os.fsync(fd)
            self._fd = fd
            return self
        except BaseException:
            os.close(fd)
            raise

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> "RuntimeFileLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
