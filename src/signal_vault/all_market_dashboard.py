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
from .research_dashboard_diagnostics import read_crypto_research_diagnostics


KIND="SIGNAL_VAULT_ALL_MARKET_OPERATOR_DASHBOARD_READ_ONLY"


def _pct(value:object,target:int)->int:
    try:
        number=int(value)
    except (TypeError,ValueError):
        number=0
    if target<=0:
        return 0
    return max(0,min(100,round(number*100/target)))


def build_dashboard_snapshot(
    *,
    root:Path,
    environ:Mapping[str,str]|None=None,
    crypto_research_receipt:Path|None=None,
)->dict[str,object]:
    status=all_market_forward_status(environ=environ,root=root)
    runway=paper_runway_from_forward_status(status)
    crypto=status["btc_and_six_crypto"]
    equity=status["us_equity"]
    kalshi=status["kalshi"]
    research=read_crypto_research_diagnostics(crypto_research_receipt)
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
                "source_progress_pct":_pct(
                    crypto.get("sidecar_current_segment_independent_prospective_hours",0),169
                ),
                "score_progress_pct":_pct(
                    crypto.get("sidecar_fully_observed_precommitted_decision_intervals",0),168
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
                "session_progress_pct":_pct(equity.get("session_plan_files",0),10),
                "core_hour_progress_pct":_pct(
                    equity.get("prospective_core_hour_receipts",0),60
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
                "decision_progress_pct":_pct(
                    kalshi.get("prospective_decision_snapshots",0),40
                ),
                "settlement_progress_pct":_pct(
                    kalshi.get("settlement_receipts",0),20
                ),
                "next_action":status["lane_next_actions"]["kalshi"],
            },
        },
        "strategy_research":research,
        "paper_runway_blockers":list(
            runway["current_forward_evidence_blockers"]
        ),
        "all_forward_stages_complete":
            runway["all_market_forward_source_and_review_stages_complete"],
        "execution_engineering":{
            "shared_cross_market_risk_governor":"AVAILABLE",
            "multimarket_paper_route_preview":"AVAILABLE_NO_NETWORK",
            "crypto_research_to_paper_intent":"AVAILABLE_NO_ORDER",
            "crypto_end_to_end_paper_dry_run":"AVAILABLE_NO_EXECUTION",
            "alpaca_paper_executor":"SEPARATE_GATED_COMPONENT_AVAILABLE",
            "kalshi_demo_executor":"SEPARATE_GATED_COMPONENT_AVAILABLE",
            "autonomous_paper_activation":
                "DISABLED_PENDING_FORWARD_EVIDENCE_AND_OWNER_REVIEW",
            "live_execution":"UNAVAILABLE",
        },
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
    research=snapshot.get("strategy_research",{
        "status":"NOT_IMPORTED","candidate_family":None,"selected_strategy":None,
        "base_friction_rows":[],
    })
    if not isinstance(research,Mapping):
        raise ValueError("dashboard research diagnostics must be a mapping")
    blocker_text="None" if not blockers else ", ".join(str(x) for x in blockers)
    latest_kalshi=snapshot.get("latest_kalshi_tick",{})
    if not isinstance(latest_kalshi,Mapping):
        latest_kalshi={}
    execution=snapshot.get("execution_engineering")
    if execution is None:
        execution={
            "shared_cross_market_risk_governor":"NOT_RECORDED_IN_THIS_SNAPSHOT",
            "multimarket_paper_route_preview":"NOT_RECORDED_IN_THIS_SNAPSHOT",
            "crypto_research_to_paper_intent":"NOT_RECORDED_IN_THIS_SNAPSHOT",
            "crypto_end_to_end_paper_dry_run":"NOT_RECORDED_IN_THIS_SNAPSHOT",
            "alpaca_paper_executor":"NOT_RECORDED_IN_THIS_SNAPSHOT",
            "kalshi_demo_executor":"NOT_RECORDED_IN_THIS_SNAPSHOT",
            "autonomous_paper_activation":"DISABLED",
            "live_execution":"UNAVAILABLE",
        }
    elif not isinstance(execution,Mapping):
        raise ValueError("dashboard execution engineering state must be a mapping")

    def meter(label:str,value:object)->str:
        try:
            pct=max(0,min(100,int(value)))
        except (TypeError,ValueError):
            pct=0
        return (
            f'<section class="meter"><label>{esc(label)} <strong>{pct}%</strong></label>'
            f'<progress max="100" value="{pct}">{pct}%</progress></section>'
        )

    def card(
        title:str,
        rows:list[tuple[str,object]],
        meters:list[tuple[str,object]]|None=None,
    )->str:
        body="".join(
            f"<div><span>{esc(k)}</span><strong>{esc(v)}</strong></div>"
            for k,v in rows
        )
        progress="".join(meter(label,value) for label,value in (meters or []))
        return f"<article><h2>{esc(title)}</h2>{progress}{body}</article>"

    cards="".join((
        card("Six Crypto",[
            ("Prospective hours",crypto["prospective_source_hours"]),
            ("Scored outcomes",crypto["fully_scored_outcomes"]),
            ("Hours remaining",crypto["source_hours_remaining"]),
            ("Outcomes remaining",crypto["scored_outcomes_remaining"]),
            ("Next",crypto["next_action"]),
        ],[
            ("Source evidence",crypto.get("source_progress_pct",0)),
            ("Scored outcomes",crypto.get("score_progress_pct",0)),
        ]),
        card("US Equities",[
            ("Session plans",equity["session_plans"]),
            ("Core-hour receipts",equity["core_hour_receipts"]),
            ("Sessions remaining",equity["session_plans_remaining"]),
            ("Core hours remaining",equity["core_hour_receipts_remaining"]),
            ("Capture windows open",equity["capture_windows_open"]),
            ("Next",equity["next_action"]),
        ],[
            ("Session plans",equity.get("session_progress_pct",0)),
            ("Core-hour evidence",equity.get("core_hour_progress_pct",0)),
        ]),
        card("Kalshi",[
            ("Plan present",kalshi["plan_present"]),
            ("Planned markets",kalshi["planned_markets"]),
            ("Decision snapshots",kalshi["decision_snapshots"]),
            ("Settlements",kalshi["settlements"]),
            ("Snapshots remaining",kalshi["decision_snapshots_remaining"]),
            ("Settlements remaining",kalshi["settlements_remaining"]),
            ("Next",kalshi["next_action"]),
        ],[
            ("Decision evidence",kalshi.get("decision_progress_pct",0)),
            ("Settlement evidence",kalshi.get("settlement_progress_pct",0)),
        ]),
        card("Latest Kalshi Tick",[
            ("Status",latest_kalshi.get("status","NOT_RECORDED")),
            ("Planning failure",latest_kalshi.get("planning_failure_code") or latest_kalshi.get("failure_class") or "None"),
            ("Public GETs used",latest_kalshi.get("public_get_requests_used","n/a")),
            ("GET budget",latest_kalshi.get("public_get_budget","n/a")),
            ("Planned markets",latest_kalshi.get("planned_market_count","n/a")),
            ("Snapshots captured",latest_kalshi.get("prospective_snapshots_captured","n/a")),
            ("Settlements captured",latest_kalshi.get("settlement_receipts_captured","n/a")),
        ]),
        card("Strategy Research",[
            ("Status",research.get("status","NOT_IMPORTED")),
            ("Family",research.get("candidate_family") or "None"),
            ("Selected / candidate",research.get("selected_strategy") or "None"),
            ("Prospective confirmation required",research.get("new_prospective_confirmation_required",False)),
            ("PAPER activation permitted",research.get("paper_activation_permitted",False)),
            ("Base-friction rows",len(research.get("base_friction_rows",[]) if isinstance(research.get("base_friction_rows",[]),list) else [])),
        ]),
        card("PAPER Pipeline",[
            ("Shared risk governor",execution["shared_cross_market_risk_governor"]),
            ("Route preview",execution["multimarket_paper_route_preview"]),
            ("Crypto decision intent",execution["crypto_research_to_paper_intent"]),
            ("Crypto dry run",execution["crypto_end_to_end_paper_dry_run"]),
            ("Alpaca executor",execution["alpaca_paper_executor"]),
            ("Kalshi demo executor",execution["kalshi_demo_executor"]),
            ("Autonomous activation",execution["autonomous_paper_activation"]),
            ("LIVE",execution["live_execution"]),
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
.meter{{margin:10px 0 14px}}.meter label{{display:flex;justify-content:space-between;color:#9fb0bf;font-size:.9rem}}
.meter progress{{width:100%;height:12px;margin-top:6px}}
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
