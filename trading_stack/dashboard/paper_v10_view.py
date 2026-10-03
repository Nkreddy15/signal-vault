"""Read-only dashboard access to the separate V10 ledger and archived charts."""
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path("/paper-data/paper-v10")


def active():
    return (ROOT/"activated").exists()


def summary():
    try:
        data = json.loads((ROOT/"summary.json").read_text())
        if data.get("version") != "V10-PAPER-1":
            raise ValueError("Unexpected V10 release")
        if time.time()*1000-(data.get("last_success_ms") or 0) > 120_000:
            data["status"] = "STALE"
            data["crypto"]["bot_state"] = "STALE"
            data["crypto"]["errors"] = list(data["crypto"].get("errors", []))+["No successful V10 cycle within two minutes; marks may be stale."]
        return data
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return dict(version="V10-PAPER-1", status="UNAVAILABLE", note="V10 status unavailable.",
            crypto=dict(bot_state="UNAVAILABLE", config=dict(timeframe="15m"),
                open_trades=[], closed_trades=[], open_trade_count=0, closed_trade_count=0,
                open_pnl_usd=None, closed_pnl_usd=None, open_exposure_usd=None, profit={},
                errors=[f"V10 status unavailable: {type(exc).__name__}"]), safety={})


def candles(pair, limit, trade_id=None):
    if trade_id:
        try:
            with sqlite3.connect(f"file:{ROOT/'ledger.sqlite3'}?mode=ro", uri=True) as db:
                row = db.execute("SELECT payload FROM charts WHERE trade_id=?", (trade_id,)).fetchone()
            if row:
                return json.loads(row[0])[-limit:], None
        except (OSError, ValueError, sqlite3.Error):
            return [], "Archived V10 chart is unavailable."
    try:
        data = json.loads((ROOT/"candles.json").read_text())
        return data.get("pairs", {}).get(pair, [])[-limit:], None
    except (OSError, ValueError):
        return [], "V10 closed candle cache is not ready."
