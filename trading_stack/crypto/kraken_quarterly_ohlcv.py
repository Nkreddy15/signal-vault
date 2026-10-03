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


def _find_member(names: list[str], aliases: tuple[str, ...]) -> str | None:
    candidates: list[tuple[int, str]] = []
    for name in names:
        if not name.lower().endswith(".csv"):
            continue
        stem = _normalized_stem(name)
        for alias in aliases:
            # Expected archive names are typically PAIR_15.csv. Normalizing
            # makes this robust to separators and nested directories.
            if stem == f"{alias}15":
                return name
            if alias in stem and stem.endswith("15"):
                candidates.append((len(stem), name))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


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
            member = _find_member(names, aliases)
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
