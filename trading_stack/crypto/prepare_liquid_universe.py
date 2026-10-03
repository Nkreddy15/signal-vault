"""Select USD assets using January 1–7 liquidity, then export research candles.

Selection cannot inspect subsequent returns or require later-quarter survival.
Reads cached public archives; never calls an authenticated/trading endpoint.
"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
import pandas as pd
import multi_strategy_lab as m
import kraken_quarterly_ohlcv as archive_helper

ALIASES = {"XBT":"BTC", "XXBT":"BTC", "XETH":"ETH", "XXRP":"XRP",
    "XDG":"DOGE", "XXDG":"DOGE", "XLTC":"LTC", "XXLM":"XLM",
    "XZEC":"ZEC", "XETC":"ETC", "XREP":"REP", "XXMR":"XMR"}
EXCLUDED = {"USD", "USDT", "USDC", "DAI", "TUSD", "FDUSD", "USDD", "PYUSD",
    "USDG", "USDE", "USDS", "EURT", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD",
    "NZD", "BRL", "XAU", "XAG", "PAXG", "RLUSD", "GUSD", "FRAX", "EURC"}


def members(zf):
    found = {}
    for name in sorted(zf.namelist(), key=lambda n:(len(Path(n).parts), len(n), n)):
        if not name.lower().endswith(".csv"):
            continue
        match = re.fullmatch(r"([A-Z0-9]+?)(?:Z?USD)[_-]15", Path(name).stem.upper())
        if not match:
            continue
        base = ALIASES.get(match[1], match[1])
        if base in EXCLUDED or re.search(r"(?:[23][LS]|BULL|BEAR)$", base):
            continue
        found.setdefault(base+"/USD", name)
    return found


def read_member(zf, name):
    with zf.open(name) as fh:
        f = pd.read_csv(fh, header=None,
            names=["ts", "open", "high", "low", "close", "volume", "trades"])
    for c in f.columns:
        f[c] = pd.to_numeric(f[c], errors="coerce")
    # Kraken archives use seconds or milliseconds; reject ambiguous units.
    f["ts"] = f.ts.where(f.ts.abs() >= 10_000_000_000, f.ts*1000)
    return f


def rank_formation(zf, formation_start, formation_end, count=24, min_daily_usd=100_000):
    selected, excluded = [], []
    expected = (formation_end-formation_start)//m.BAR
    for pair, name in members(zf).items():
        raw = read_member(zf, name)
        # Only formation rows are validated or ranked. Invalid/failing future
        # data must not decide which assets would have been selected earlier.
        raw = raw[(raw.ts >= formation_start) & (raw.ts < formation_end)]
        try:
            f = m.normalized(raw)
            active = int((f.volume > 0).sum())
            coverage = len(f)/expected
            day = f.ts//m.DAY
            dollar_volume = (f.close*f.volume).groupby(day).sum()
            score = float(dollar_volume.median())
            if coverage < .90 or active < .70*expected or score < min_daily_usd:
                excluded.append(dict(pair=pair, reason="Formation coverage/activity/liquidity below requirement"))
                continue
            selected.append(dict(pair=pair, member=name, median_daily_usd_volume=score,
                formation_bars=len(f), active_bars=active, coverage=coverage))
        except (ValueError, TypeError) as exc:
            excluded.append(dict(pair=pair, reason="Formation data invalid: "+str(exc)))
    selected.sort(key=lambda r:(-r["median_daily_usd_volume"], r["pair"]))
    return selected[:count], excluded


def prepare(archives, output, count=24, min_daily_usd=100_000):
    if not 1 <= count <= 100 or min_daily_usd < 0:
        raise ValueError("Invalid universe constraints")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    formation_start = int(pd.Timestamp("2026-01-01", tz="UTC").value//1_000_000)
    formation_end = formation_start+7*m.DAY
    with zipfile.ZipFile(archives[0]) as zf:
        selected, excluded = rank_formation(zf, formation_start, formation_end, count, min_daily_usd)
    if not selected:
        raise ValueError("No assets passed the formation requirements")
    print(f"Selected {len(selected)} USD assets using Jan 1–7 liquidity only.", flush=True)
    parts = {r["pair"]:[] for r in selected}
    manifest, missing = [], []
    boundaries = [(formation_start, int(pd.Timestamp("2026-04-01", tz="UTC").value//1_000_000)),
        (int(pd.Timestamp("2026-04-01", tz="UTC").value//1_000_000), int(pd.Timestamp("2026-07-01", tz="UTC").value//1_000_000))]
    for index, archive in enumerate(archives):
        archive = Path(archive)
        with archive.open("rb") as fh:
            digest = hashlib.file_digest(fh, "sha256").hexdigest()
        manifest.append(dict(path=str(archive), sha256=digest))
        with zipfile.ZipFile(archive) as zf:
            available = members(zf)
            lo, hi = boundaries[index]
            for row in selected:
                pair = row["pair"]
                if pair not in available:
                    missing.append(dict(pair=pair, archive=str(archive)))
                    continue
                raw = read_member(zf, available[pair])
                if raw.ts.isna().any():
                    raise ValueError(f"{pair}: invalid source timestamps in {archive}")
                f = m.normalized(raw[(raw.ts >= lo) & (raw.ts < hi)])
                parts[pair].append(f)
    for pair, segments in parts.items():
        f = m.normalized(pd.concat(segments, ignore_index=True))
        f.to_feather(output/(pair.replace("/", "_")+"-15m.feather"))
        print(f"  {pair}: {len(f):,} candles", flush=True)
    receipt = dict(kind="FORMATION_LIQUIDITY_UNIVERSE", formation_start_ms=formation_start,
        formation_end_ms=formation_end, selected=selected, excluded=excluded, archives=manifest,
        missing_later_members=missing, min_daily_usd=min_daily_usd,
        limitation="Selection uses formation data only; published-archive omissions can still introduce survivorship bias. Later missing members do not remove an asset.")
    (output/"universe.json").write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
    return receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--q1-archive", required=True)
    p.add_argument("--q2-archive", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--count", type=int, default=24)
    p.add_argument("--min-daily-usd", type=float, default=100_000)
    a = p.parse_args()
    for quarter, path in (("2026Q1", a.q1_archive), ("2026Q2", a.q2_archive)):
        archive_helper._download(archive_helper._candidate_urls(quarter), Path(path))
    prepare([a.q1_archive, a.q2_archive], a.output_dir, a.count, a.min_daily_usd)


if __name__ == "__main__":
    main()
