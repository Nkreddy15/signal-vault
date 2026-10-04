"""Prepare a 2025 Q4 cross-venue holdout from Binance public spot klines.

This is used only as an unseen robustness check for Signal Vault V5 because the
current Kraken incremental archive page does not expose a standalone 2025 Q4
OHLCVT ZIP. Binance publishes monthly public kline ZIPs without authentication.

The output intentionally uses the existing *_USD-1h.feather filenames so the
offline V5 research engine can consume the same six logical assets. The source
market is USDT spot, not Kraken USD spot; that distinction is part of the
research metadata and must not be presented as Kraken-native evidence.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd


BASE = "https://data.binance.vision/data/spot/monthly/klines"
MONTHS = ("2025-10", "2025-11", "2025-12")
SYMBOLS = {
    "BTC/USD": "BTCUSDT",
    "ETH/USD": "ETHUSDT",
    "SOL/USD": "SOLUSDT",
    "XRP/USD": "XRPUSDT",
    "DOGE/USD": "DOGEUSDT",
    "ADA/USD": "ADAUSDT",
}


def _download_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SignalVaultResearch/1.0"},
    )
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
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(
                f"{filename}: expected one CSV, found {len(csv_names)}"
            )
        with zf.open(csv_names[0]) as fh:
            frame = pd.read_csv(
                fh,
                header=None,
                names=[
                    "open_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades",
                    "taker_base",
                    "taker_quote",
                    "ignore",
                ],
            )

    if frame.empty:
        raise RuntimeError(f"{filename}: no kline rows")

    # Binance Spot timestamps from 2025-01-01 onward are microseconds.
    frame["date"] = pd.to_datetime(
        pd.to_numeric(frame["open_time"], errors="coerce"),
        unit="us",
        utc=True,
    )
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    frame = frame[
        ["date", "open", "high", "low", "close", "volume"]
    ].dropna()
    return frame


def main() -> int:
    outdir = Path("/freqtrade/data/v5-2025q4-crossvenue")
    outdir.mkdir(parents=True, exist_ok=True)

    start = pd.Timestamp("2025-10-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T00:00:00Z")

    for logical_pair, symbol in SYMBOLS.items():
        parts = [_read_month(symbol, month) for month in MONTHS]
        frame = (
            pd.concat(parts, ignore_index=True)
            .sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
        )
        frame = frame[(frame["date"] >= start) & (frame["date"] < end)].copy()

        # Q4 has 2208 hourly slots. Binance monthly files should be effectively
        # complete for these liquid pairs; reject weak/incomplete holdout data.
        if len(frame) < 2150:
            raise RuntimeError(
                f"{symbol}: only {len(frame)} hourly rows for 2025 Q4; "
                "refusing incomplete holdout"
            )

        target = outdir / (logical_pair.replace("/", "_") + "-1h.feather")
        frame.reset_index(drop=True).to_feather(target)
        print(
            f"{logical_pair} <- {symbol}: {len(frame):,} x 1h | "
            f"{frame['date'].iloc[0]} -> {frame['date'].iloc[-1]} | "
            f"{target.name}"
        )

    meta = outdir / "SOURCE.txt"
    meta.write_text(
        "Signal Vault V5 cross-venue holdout\n"
        "Source: Binance public SPOT monthly klines\n"
        "Quote asset: USDT\n"
        "Period: 2025-10-01 through 2025-12-31 UTC\n"
        "Use: unseen robustness check only; not Kraken-native execution evidence\n"
    )
    print("2025 Q4 Binance cross-venue holdout prepared successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
