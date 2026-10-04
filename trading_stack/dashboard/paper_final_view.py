"""Read-only projection of the overnight simulator, separate from V1 P&L."""
import json
import time
from pathlib import Path

ROOT = Path("/paper-data/paper-final-v9")


def active():
    return (ROOT / "activated").exists()


def summary():
    try:
        data = json.loads((ROOT / "summary.json").read_text())
        if data.get("version") != "V9-OVERNIGHT-1":
            raise ValueError("Unexpected paper release")
        if time.time()*1000 - data.get("last_success_ms", 0) > 120_000:
            data["status"] = "STALE"
            data["crypto"]["bot_state"] = "STALE"
            data["crypto"]["errors"] = list(data["crypto"].get("errors", [])) + ["No successful paper cycle within two minutes; marks may be stale."]
        return data
    except (OSError, ValueError, TypeError) as exc:
        return dict(status="UNAVAILABLE", note="Final paper runner has no readable status.",
            crypto=dict(bot_state="UNAVAILABLE", config={}, open_trades=[], closed_trades=[],
                open_trade_count=0, closed_trade_count=0, open_pnl_usd=None,
                closed_pnl_usd=None, open_exposure_usd=None, profit={},
                errors=[f"Paper status unavailable: {type(exc).__name__}"]), safety={})


def candles(pair, limit):
    try:
        data = json.loads((ROOT / "candles.json").read_text())
        return data.get("pairs", {}).get(pair, [])[-limit:], None
    except (OSError, ValueError):
        return [], "Paper candle cache is not ready."
