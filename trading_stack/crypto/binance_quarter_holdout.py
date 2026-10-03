"""Prepare a quarter of Binance public spot 1h klines for cross-venue holdout use.

The logical output pair names remain *_USD-1h.feather so Signal Vault research
code can compare the same six assets across venues. Source candles are Binance
USDT spot and are NOT Kraken-native execution evidence.
"""

from __future__ import annotations

import argparse
import calendar
import io
import re
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

BASE = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = {
    "BTC/USD": "BTCUSDT",
    "ETH/USD": "ETHUSDT",
    "SOL/USD": "SOLUSDT",
    "XRP/USD": "XRPUSDT",
    "DOGE/USD": "DOGEUSDT",
    "ADA/USD": "ADAUSDT",
}


def _download_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SignalVaultResearch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Download failed for {url}: {exc.reason}") from exc

    if not data:
        raise RuntimeError(f"Empty response for {url}")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise RuntimeError(f"Response is not a valid ZIP: {url}")
    return data


def _read_month(symbol: str, month: str) -> pd.DataFrame:
    filename = f"{symbol}-1h-{month}.zip"
    url = f"{BASE}/{symbol}/1h/{filename}"
    print(f"{symbol} {month}: {url}")
    raw = _download_bytes(url)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(f"{filename}: expected one CSV, found {len(csv_names)}")
        with zf.open(csv_names[0]) as fh:
            frame = pd.read_csv(
                fh,
                header=None,
                names=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "trades", "taker_base",
                    "taker_quote", "ignore",
                ],
            )

    # Binance spot timestamps from 2025 onward are microseconds.
    frame["date"] = pd.to_datetime(
        pd.to_numeric(frame["open_time"], errors="coerce"), unit="us", utc=True
    )
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame[["date", "open", "high", "low", "close", "volume"]].dropna()


def _quarter_bounds(quarter: str) -> tuple[pd.Timestamp, pd.Timestamp, list[str]]:
    m = re.fullmatch(r"(20\d{2})Q([1-4])", quarter.upper())
    if not m:
        raise SystemExit("--quarter must look like 2025Q3")
    year = int(m.group(1))
    q = int(m.group(2))
    start_month = (q - 1) * 3 + 1
    months = [f"{year}-{month:02d}" for month in range(start_month, start_month + 3)]
    start = pd.Timestamp(year=year, month=start_month, day=1, tz="UTC")
    if q == 4:
        end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
    else:
        end = pd.Timestamp(year=year, month=start_month + 3, day=1, tz="UTC")
    return start, end, months


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarter", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    quarter = args.quarter.upper()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    start, end, months = _quarter_bounds(quarter)

    expected_hours = int((end - start).total_seconds() // 3600)
    minimum_hours = expected_hours - 12

    for logical_pair, symbol in SYMBOLS.items():
        parts = [_read_month(symbol, month) for month in months]
        frame = (
            pd.concat(parts, ignore_index=True)
            .sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
        )
        frame = frame[(frame["date"] >= start) & (frame["date"] < end)].copy()

        if len(frame) < minimum_hours:
            raise RuntimeError(
                f"{symbol}: only {len(frame)} hourly rows for {quarter}; "
                f"expected about {expected_hours}. Refusing incomplete holdout."
            )

        target = outdir / (logical_pair.replace("/", "_") + "-1h.feather")
        frame.reset_index(drop=True).to_feather(target)
        print(
            f"{logical_pair} <- {symbol}: {len(frame):,} x 1h | "
            f"{frame['date'].iloc[0]} -> {frame['date'].iloc[-1]} | {target.name}"
        )

    (outdir / "SOURCE.txt").write_text(
        "Signal Vault cross-venue holdout\n"
        f"Source: Binance public SPOT monthly klines\n"
        f"Quote asset: USDT\nQuarter: {quarter}\n"
        "Use: unseen robustness check only; not Kraken-native execution evidence\n"
    )
    print(f"{quarter} Binance cross-venue holdout prepared successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
