"""Authenticated READ-ONLY historical BTC/USD dataset capture with fingerprinting.

No trading endpoint is imported. Captured data is immutable evidence for offline
research and is never silently repaired or resampled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Protocol, Sequence
import csv
import json
import os
import tempfile

from .market_data import Bar, validate_bars


class HistoricalBarsProvider(Protocol):
    def fetch(self, *, start: datetime, end: datetime, as_of: datetime) -> Sequence[Bar]: ...


@dataclass(frozen=True)
class DatasetManifest:
    schema_version: int
    symbol: str
    timeframe: str
    source: str
    start_utc: str
    end_utc: str
    row_count: int
    csv_sha256: str
    captured_utc: str

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise ValueError("dataset path must not be a symlink")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path); os.chmod(path, 0o600)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def capture_dataset(provider: HistoricalBarsProvider, *, start: datetime, end: datetime,
                    as_of: datetime, output_csv: str | Path,
                    captured_at: datetime | None = None) -> DatasetManifest:
    for value in (start, end, as_of):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("dataset boundaries must be timezone-aware")
    if not start < end <= as_of:
        raise ValueError("invalid dataset interval")
    bars = validate_bars(provider.fetch(start=start, end=end, as_of=as_of),
                         as_of=as_of, min_count=1)
    if bars[0].start != start.astimezone(timezone.utc) or bars[-1].close_time != end.astimezone(timezone.utc):
        raise ValueError("captured provider interval is incomplete")
    import io
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("timestamp", "open", "high", "low", "close", "volume"))
    for bar in bars:
        writer.writerow((bar.start.isoformat(), str(bar.open), str(bar.high), str(bar.low),
                         str(bar.close), str(bar.volume)))
    data = buffer.getvalue().encode("utf-8")
    digest = sha256(data).hexdigest()
    now = captured_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("capture timestamp must be timezone-aware")
    manifest = DatasetManifest(1, "BTC/USD", "1Hour", bars[0].source,
                               bars[0].start.isoformat(), bars[-1].close_time.isoformat(),
                               len(bars), digest, now.astimezone(timezone.utc).isoformat())
    target = Path(output_csv).expanduser()
    _atomic_write(target, data)
    _atomic_write(target.with_suffix(target.suffix + ".manifest.json"),
                  (json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode())
    return manifest
