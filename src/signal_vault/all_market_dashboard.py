"""Private read-only all-market dashboard snapshot and HTML renderer.

Consumes persisted forward evidence only. No provider requests, credentials, or
order submission. This is the observation layer for six-crypto, US equities,
and Kalshi while execution remains separately gated.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Mapping

from .all_market_forward_status import all_market_forward_status
from .paper_runway_status import paper_runway_from_forward_status


KIND="SIGNAL_VAULT_ALL_MARKET_OPERATOR_DASHBOARD_READ_ONLY"


def build_dashboard_snapshot(
    *,
    root:Path,
    environ:Mapping[str,str]|None=None,
)->dict[str,object]:
    status=all_market_forward_status(environ=environ,root=root)
    runway=paper_runway_from_forward_status(status)
    crypto=status["btc_and_six_crypto"]
    equity=status["us_equity"]
    kalshi=status["kalshi"]
    return {
        "kind":KIND,
        "checked_at_utc":status["checked_at_utc"],
        "lanes":{
            "six_crypto":{
                "prospective_source_hours":crypto.get(
                    "sidecar_current_segment_independent_prospective_hours",0
                ),
                "fully_scored_outcomes":crypto.get(
                    "sidecar_fully_observed_precommitted_decision_intervals",0
                ),
                "source_hours_remaining":crypto.get(
                    "sidecar_review_gate_source_hours_remaining_to_169"
                ),
                "scored_outcomes_remaining":crypto.get(
                    "sidecar_review_gate_scored_outcomes_remaining_to_168"
                ),
                "next_action":status["lane_next_actions"]["six_crypto"],
            },
            "us_equity":{
                "session_plans":equity.get("session_plan_files",0),
                "core_hour_receipts":equity.get(
                    "prospective_core_hour_receipts",0
                ),
                "session_plans_remaining":equity.get(
                    "raw_session_plans_remaining_to_10",10
                ),
                "core_hour_receipts_remaining":equity.get(
                    "raw_core_hour_receipts_remaining_to_60",60
                ),
                "capture_windows_open":equity.get(
                    "decision_hours_capture_window_open",0
                ),
                "next_action":status["lane_next_actions"]["us_equity"],
            },
            "kalshi":{
                "plan_present":kalshi.get("plan_present") is True,
                "planned_markets":kalshi.get("planned_market_count"),
                "decision_snapshots":kalshi.get(
                    "prospective_decision_snapshots",0
                ),
                "settlements":kalshi.get("settlement_receipts",0),
                "decision_snapshots_remaining":kalshi.get(
                    "raw_decision_snapshots_remaining",40
                ),
                "settlements_remaining":kalshi.get(
                    "raw_settlement_receipts_remaining",20
                ),
                "next_action":status["lane_next_actions"]["kalshi"],
            },
        },
        "paper_runway_blockers":list(
            runway["current_forward_evidence_blockers"]
        ),
        "all_forward_stages_complete":
            runway["all_market_forward_source_and_review_stages_complete"],
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
        "network_requests":"NONE",
        "credential_access":"NONE",
    }


def render_dashboard_html(snapshot:Mapping[str,object])->bytes:
    if snapshot.get("kind")!=KIND:
        raise ValueError("invalid dashboard snapshot")
    lanes=snapshot.get("lanes")
    if not isinstance(lanes,Mapping):
        raise ValueError("dashboard snapshot lacks lanes")
    esc=lambda value:html.escape(str(value),quote=True)

    crypto=lanes["six_crypto"]
    equity=lanes["us_equity"]
    kalshi=lanes["kalshi"]
    blockers=snapshot.get("paper_runway_blockers",[])
    blocker_text="None" if not blockers else ", ".join(str(x) for x in blockers)

    def card(title:str,rows:list[tuple[str,object]])->str:
        body="".join(
            f"<div><span>{esc(k)}</span><strong>{esc(v)}</strong></div>"
            for k,v in rows
        )
        return f"<article><h2>{esc(title)}</h2>{body}</article>"

    cards="".join((
        card("Six Crypto",[
            ("Prospective hours",crypto["prospective_source_hours"]),
            ("Scored outcomes",crypto["fully_scored_outcomes"]),
            ("Hours remaining",crypto["source_hours_remaining"]),
            ("Outcomes remaining",crypto["scored_outcomes_remaining"]),
            ("Next",crypto["next_action"]),
        ]),
        card("US Equities",[
            ("Session plans",equity["session_plans"]),
            ("Core-hour receipts",equity["core_hour_receipts"]),
            ("Sessions remaining",equity["session_plans_remaining"]),
            ("Core hours remaining",equity["core_hour_receipts_remaining"]),
            ("Capture windows open",equity["capture_windows_open"]),
            ("Next",equity["next_action"]),
        ]),
        card("Kalshi",[
            ("Plan present",kalshi["plan_present"]),
            ("Planned markets",kalshi["planned_markets"]),
            ("Decision snapshots",kalshi["decision_snapshots"]),
            ("Settlements",kalshi["settlements"]),
            ("Snapshots remaining",kalshi["decision_snapshots_remaining"]),
            ("Settlements remaining",kalshi["settlements_remaining"]),
            ("Next",kalshi["next_action"]),
        ]),
    ))
    markup=f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Signal Vault | All-Market Monitor</title>
<style>
:root{{font-family:system-ui,-apple-system,sans-serif;color:#e8eef2;background:#0b0f14}}
body{{max-width:1180px;margin:0 auto;padding:32px}}
header{{display:flex;justify-content:space-between;gap:24px;align-items:end}}
h1{{margin:0;font-size:2rem}}p{{color:#9fb0bf}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:24px}}
article{{background:#121923;border:1px solid #263546;border-radius:14px;padding:20px}}
article h2{{margin-top:0}}article div{{display:flex;justify-content:space-between;gap:16px;padding:8px 0;border-bottom:1px solid #1f2b38}}
article div:last-child{{border:0}}span{{color:#9fb0bf}}strong{{text-align:right;overflow-wrap:anywhere}}
.banner{{margin-top:20px;padding:16px;border:1px solid #634f27;background:#211d13;border-radius:12px}}
footer{{margin-top:24px;color:#748595;font-size:.9rem}}
</style></head><body>
<header><div><h1>Signal Vault</h1><p>Read-only all-market forward monitor</p></div>
<div><strong>PAPER: DISABLED</strong><br><strong>LIVE: UNAVAILABLE</strong></div></header>
<div class="banner"><strong>Current forward blockers:</strong> {esc(blocker_text)}</div>
<section class="grid">{cards}</section>
<footer>Checked {esc(snapshot["checked_at_utc"])} · No provider requests · No credentials · Refreshes every 60 seconds</footer>
</body></html>"""
    return markup.encode("utf-8")


def snapshot_json(snapshot:Mapping[str,object])->bytes:
    if snapshot.get("kind")!=KIND:
        raise ValueError("invalid dashboard snapshot")
    return (json.dumps(dict(snapshot),sort_keys=True,separators=(",",":"))+"\n").encode()
