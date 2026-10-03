"""Prepare Signal Vault V2 research candles from Kraken's official quarterly OHLCVT archive.

This intentionally avoids Kraken's slow sequential historical-trades API.
It downloads the official 2026 Q2 OHLCVT archive once, extracts only the
six configured USD spot pairs at 15-minute resolution, and writes Freqtrade
feather files into the persistent research volume.

Research/PAPER use only.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd


DEFAULT_URL = (
    "https://assets.kraken.com/marketing/institutions/"
    "Kraken_OHLCVT_2026Q2.zip"
)

PAIR_ALIASES = {
    "BTC/USD": ("BTCUSD", "XBTUSD", "XXBTZUSD"),
    "ETH/USD": ("ETHUSD", "XETHZUSD"),
    "SOL/USD": ("SOLUSD",),
    "XRP/USD": ("XRPUSD", "XXRPZUSD"),
    "DOGE/USD": ("DOGEUSD", "XDGUSD", "XXDGZUSD"),
    "ADA/USD": ("ADAUSD",),
}


def _normalized_stem(name: str) -> str:
    stem = Path(name).stem.upper()
    return re.sub(r"[^A-Z0-9]", "", stem)


def _sample_interval_seconds(zf: zipfile.ZipFile, member: str) -> float | None:
    """Infer candle spacing from timestamps instead of trusting filename syntax."""
    try:
        with zf.open(member) as fh:
            sample = pd.read_csv(fh, header=None, nrows=32)
    except Exception:
        return None

    if sample.empty or sample.shape[1] < 1:
        return None

    ts = pd.to_numeric(sample.iloc[:, 0], errors="coerce").dropna()
    if len(ts) < 3:
        return None

    # Kraken archives may encode timestamps in seconds or milliseconds.
    values = ts.astype(float)
    if float(values.max()) > 10_000_000_000:
        values = values / 1000.0

    diffs = values.diff().dropna()
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return None
    return float(diffs.median())


def _find_member(
    zf: zipfile.ZipFile,
    names: list[str],
    aliases: tuple[str, ...],
    target_interval_seconds: int = 900,
) -> str | None:
    """Find the actual 15m member by inspecting candle spacing.

    Kraken archive filenames can contain separators that make naive normalized
    matching ambiguous (for example, a 1-minute/5-minute-looking name can
    collapse to the same normalized suffix as "15"). We therefore shortlist
    by pair alias and verify the median timestamp spacing is exactly 15 minutes.
    """
    candidates: list[str] = []
    for name in names:
        if not name.lower().endswith(".csv"):
            continue
        stem = _normalized_stem(name)
        if any(alias in stem for alias in aliases):
            candidates.append(name)

    scored: list[tuple[float, int, str]] = []
    for name in candidates:
        interval = _sample_interval_seconds(zf, name)
        if interval is None:
            continue
        distance = abs(interval - target_interval_seconds)
        scored.append((distance, len(name), name))

    if not scored:
        return None

    scored.sort()
    distance, _, member = scored[0]
    # Refuse an accidental nearest-match if it is not actually ~15m.
    if distance > 5:
        return None
    return member


def _download(url: str, target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        print(f"Using cached archive: {target} ({target.stat().st_size / 1024**2:.1f} MiB)")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    if partial.exists():
        partial.unlink()

    print(f"Downloading official Kraken quarterly OHLCVT archive:")
    print(f"  {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "SignalVaultResearch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        next_report = 25 * 1024 * 1024
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if done >= next_report:
                if total:
                    pct = 100.0 * done / total
                    print(f"  {done / 1024**2:.0f}/{total / 1024**2:.0f} MiB ({pct:.1f}%)")
                else:
                    print(f"  {done / 1024**2:.0f} MiB")
                next_report += 25 * 1024 * 1024

    partial.replace(target)
    print(f"Archive saved: {target} ({target.stat().st_size / 1024**2:.1f} MiB)")


def _convert_member(zf: zipfile.ZipFile, member: str, pair: str, outdir: Path) -> None:
    with zf.open(member) as fh:
        frame = pd.read_csv(
            fh,
            header=None,
            names=["timestamp", "open", "high", "low", "close", "volume", "trades"],
        )

    if frame.empty:
        raise RuntimeError(f"{pair}: archive CSV is empty: {member}")

    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])

    max_ts = float(frame["timestamp"].max())
    unit = "ms" if max_ts > 10_000_000_000 else "s"
    frame["date"] = pd.to_datetime(frame["timestamp"], unit=unit, utc=True)

    frame = (
        frame[["date", "open", "high", "low", "close", "volume"]]
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )

    # Q2 archive can contain boundary rows; keep the declared research quarter.
    start = pd.Timestamp("2026-04-01T00:00:00Z")
    end = pd.Timestamp("2026-07-01T00:00:00Z")
    frame = frame[(frame["date"] >= start) & (frame["date"] < end)].copy()

    if len(frame) < 1000:
        raise RuntimeError(
            f"{pair}: only {len(frame)} 15m rows found for Q2; refusing weak dataset"
        )

    filename = pair.replace("/", "_") + "-15m.feather"
    target = outdir / filename
    frame.to_feather(target)

    print(
        f"{pair}: {len(frame):,} candles | "
        f"{frame['date'].iloc[0]} -> {frame['date'].iloc[-1]} | "
        f"{target.name}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--outdir", default="/freqtrade/data/v2-quarterly-ohlcv")
    parser.add_argument(
        "--archive",
        default="/freqtrade/data/v2-quarterly-ohlcv/Kraken_OHLCVT_2026Q2.zip",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    archive = Path(args.archive)
    outdir.mkdir(parents=True, exist_ok=True)

    _download(args.url, archive)

    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise SystemExit(f"Downloaded file is not a valid ZIP: {archive}: {exc}")

    with zf:
        names = zf.namelist()
        print(f"Archive entries: {len(names):,}")
        missing: list[str] = []
        selected: dict[str, str] = {}

        for pair, aliases in PAIR_ALIASES.items():
            member = _find_member(zf, names, aliases)
            if member is None:
                missing.append(pair)
            else:
                selected[pair] = member

        if missing:
            print("Could not locate 15m CSVs for:", ", ".join(missing), file=sys.stderr)
            print("Relevant 15-minute CSV names in archive:", file=sys.stderr)
            for name in names:
                if name.lower().endswith(".csv") and _normalized_stem(name).endswith("15"):
                    print(f"  {name}", file=sys.stderr)
            return 2

        for pair, member in selected.items():
            print(f"{pair}: archive member -> {member}")
            _convert_member(zf, member, pair, outdir)

    print("Kraken Q2 2026 15m research dataset prepared successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
