"""Bounded read-only strategy research diagnostics for operator dashboard."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Mapping

MAX_BYTES=250_000
ALLOWED_KINDS={
    "CRYPTO_90DAY_LOW_CHURN_CROSS_SECTIONAL_RESEARCH_RECEIPT",
    "CRYPTO_90DAY_CROSS_SECTIONAL_RESEARCH_RECEIPT",
    "CRYPTO_LONG_HORIZON_CANDIDATE_RESEARCH_BLOCKED",
}


def read_crypto_research_diagnostics(path:Path|None)->dict[str,object]:
    if path is None:
        return {"status":"NOT_IMPORTED","candidate_family":None,"selected_strategy":None}
    p=Path(path)
    if (not p.exists() or p.is_symlink() or not p.is_file() or
            p.stat().st_mode & 0o077 or not 0<p.stat().st_size<=MAX_BYTES):
        raise ValueError("research receipt must be a private bounded regular file")
    value=json.loads(p.read_text())
    if not isinstance(value,Mapping) or value.get("kind") not in ALLOWED_KINDS:
        raise ValueError("unsupported research receipt kind")
    if value.get("broker_order_submission")!="DISABLED" or value.get("live_trading")!="UNAVAILABLE":
        raise ValueError("research receipt safety contract mismatch")
    results=value.get("results")
    rows=[]
    if isinstance(results,Mapping):
        for candidate,scenario_map in results.items():
            if not isinstance(scenario_map,Mapping):
                continue
            base=scenario_map.get("illustrative_base_friction")
            if not isinstance(base,Mapping):
                continue
            for fold in ("development","validation","historical_holdout_descriptive_only","untouched_test"):
                item=base.get(fold)
                if not isinstance(item,Mapping):
                    continue
                try:
                    pnl=Decimal(str(item["net_marked_pnl_usd"]))
                    passive=Decimal(str(item["passive_equal_weight_marked_pnl_usd"]))
                    dd=Decimal(str(item["max_marked_drawdown_usd"]))
                    fills=int(item["fill_count"])
                except Exception:
                    continue
                rows.append({
                    "candidate":str(candidate),
                    "fold":fold,
                    "pnl_usd":str(pnl),
                    "passive_pnl_usd":str(passive),
                    "alpha_vs_passive_usd":str(pnl-passive),
                    "fills":fills,
                    "max_drawdown_usd":str(dd),
                })
    return {
        "status":str(value.get("status","UNKNOWN")),
        "candidate_family":str(value.get("kind")),
        "selected_strategy":value.get("selected_strategy") or value.get("strategy"),
        "paper_activation_permitted":value.get("paper_activation_permitted") is True,
        "new_prospective_confirmation_required":value.get("new_prospective_confirmation_required") is True,
        "base_friction_rows":rows[:24],
    }
