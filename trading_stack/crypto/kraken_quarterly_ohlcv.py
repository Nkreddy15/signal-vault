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
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd


ASSET_BASE = "https://assets.kraken.com/marketing/institutions"

# Older Kraken incremental archives used a different filename convention.
# Current official documentation exposes YYYYQn names for 2026, while older
# mirrors/documentation reference Qn_YYYY names. Try both before using any
# explicit fallback mirror.
Q4_2025_MIRROR = (
    "https://drive.usercontent.google.com/download"
    "?id=1QbPHLP0TTGo-lqwKn8M-_Xo_oexXlEnB&export=download&confirm=t"
)


def _candidate_urls(quarter: str) -> list[str]:
    year = quarter[:4]
    qnum = quarter[-1]
    urls = [
        f"{ASSET_BASE}/Kraken_OHLCVT_{quarter}.zip",
        f"{ASSET_BASE}/Kraken_OHLCVT_Q{qnum}_{year}.zip",
    ]
    if quarter == "2025Q4":
        urls.append(Q4_2025_MIRROR)
    return urls

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


def _find_member(
    zf: zipfile.ZipFile,
    names: list[str],
    aliases: tuple[str, ...],
    target_minutes: int = 15,
) -> str | None:
    """Find an exact pair/timeframe archive member.

    Do not use substring matching (SOLUSD must not match MSOLUSD) and do not
    infer timeframe from sparse trade timestamps. Kraken archive filenames use
    pair + timeframe forms such as XBTUSD_15.csv.
    """
    wanted = set()
    for alias in aliases:
        a = alias.upper()
        wanted.update(
            {
                f"{a}_{target_minutes}",
                f"{a}-{target_minutes}",
                f"{a}{target_minutes}",
            }
        )

    matches: list[str] = []
    for name in names:
        if not name.lower().endswith(".csv"):
            continue
        stem = Path(name).stem.upper()
        if stem in wanted:
            matches.append(name)

    if not matches:
        return None
    matches.sort(key=lambda x: (len(Path(x).parts), len(x), x))
    return matches[0]


def _download(urls: list[str], target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        if zipfile.is_zipfile(target):
            print(
                f"Using cached archive: {target} "
                f"({target.stat().st_size / 1024**2:.1f} MiB)"
            )
            return
        print(f"Cached file is not a valid ZIP; removing: {target}")
        target.unlink()

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")

    last_error: Exception | None = None
    for index, url in enumerate(urls, start=1):
        if partial.exists():
            partial.unlink()

        print("Downloading historical Kraken OHLCVT archive:")
        print(f"  attempt {index}/{len(urls)}: {url}")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SignalVaultResearch/1.0"},
        )

        try:
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
                            print(
                                f"  {done / 1024**2:.0f}/"
                                f"{total / 1024**2:.0f} MiB ({pct:.1f}%)"
                            )
                        else:
                            print(f"  {done / 1024**2:.0f} MiB")
                        next_report += 25 * 1024 * 1024
        except urllib.error.HTTPError as exc:
            last_error = exc
            print(f"  source unavailable: HTTP {exc.code}")
            continue
        except urllib.error.URLError as exc:
            last_error = exc
            print(f"  source unavailable: {exc.reason}")
            continue

        if not partial.exists() or partial.stat().st_size == 0:
            last_error = RuntimeError("download returned no bytes")
            print("  source returned no data")
            continue

        if not zipfile.is_zipfile(partial):
            last_error = RuntimeError("downloaded response was not a valid ZIP")
            print("  downloaded response was not a valid ZIP; trying next source")
            partial.unlink(missing_ok=True)
            continue

        partial.replace(target)
        print(
            f"Archive saved: {target} "
            f"({target.stat().st_size / 1024**2:.1f} MiB)"
        )
        return

    raise RuntimeError(
        f"Could not download a valid archive to {target}. Last error: {last_error}"
    )

def _convert_member(
    zf: zipfile.ZipFile,
    member: str,
    pair: str,
    outdir: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
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

    # Quarterly archives can contain boundary rows; keep only the declared
    # research quarter.
    frame = frame[(frame["date"] >= start) & (frame["date"] < end)].copy()

    if len(frame) < 1000:
        raise RuntimeError(
            f"{pair}: only {len(frame)} 15m rows found in requested quarter; refusing weak dataset"
        )

    filename = pair.replace("/", "_") + "-15m.feather"
    target = outdir / filename
    frame.to_feather(target)

    hourly = (
        frame.set_index("date")
        .resample("1h", label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    hourly_target = outdir / (pair.replace("/", "_") + "-1h.feather")
    hourly.to_feather(hourly_target)

    print(
        f"{pair}: {len(frame):,} x 15m | "
        f"{frame['date'].iloc[0]} -> {frame['date'].iloc[-1]} | "
        f"{target.name}"
    )
    print(
        f"{pair}: {len(hourly):,} x 1h | "
        f"{hourly['date'].iloc[0]} -> {hourly['date'].iloc[-1]} | "
        f"{hourly_target.name}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarter", default="2026Q2")
    parser.add_argument("--url", default=None)
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--archive", default=None)
    args = parser.parse_args()

    match = re.fullmatch(r"(20\d{2})Q([1-4])", args.quarter.upper())
    if not match:
        raise SystemExit("--quarter must look like 2026Q1")

    year = int(match.group(1))
    quarter_number = int(match.group(2))
    start_month = (quarter_number - 1) * 3 + 1
    start = pd.Timestamp(
        year=year, month=start_month, day=1, tz="UTC"
    )
    end = start + pd.DateOffset(months=3)

    quarter = args.quarter.upper()
    outdir = Path(
        args.outdir or f"/freqtrade/data/kraken-{quarter.lower()}-ohlcv"
    )
    archive = Path(
        args.archive or outdir / f"Kraken_OHLCVT_{quarter}.zip"
    )
    urls = [args.url] if args.url else _candidate_urls(quarter)
    outdir.mkdir(parents=True, exist_ok=True)

    _download(urls, archive)

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
            member = _find_member(zf, names, aliases, target_minutes=15)
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
            _convert_member(zf, member, pair, outdir, start, end)

    print(f"Kraken {quarter} 15m + 1h research dataset prepared successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
