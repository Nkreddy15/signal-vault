"""Re-analyze SHA-audited old historical artifacts with revised OFFLINE v2 rules.

A manual main-only GitHub Actions replay fetches a prior run's PRIVATE artifact
using only GITHUB_TOKEN scoped to actions:read, never historical Alpaca DATA
credentials. Original historical archives are copied once into a fresh private
temporary directory after validating every source digest and original window.
No market-data requests, trading endpoints, account queries or order submission.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .ci_historical_report import (
    ANALYSIS_FILENAME, SCENARIOS, analyze_manual_history, audit_requested_archives,
)
from .multi_asset_research_cli import aware, historical_plan
from .research_universe import AssetClass

SRC=Path("downloaded-history")
DEST=Path("private-v2-replay")
MANIFEST="replay_manifest.json"
HISTORICAL_NAME=re.compile(
    r"historical-crypto-\d{8}T\d{4}Z-\d{8}T\d{4}Z-[0-9a-f]{16}\.json\Z"
)
WORKFLOW_NAME="bounded-crypto-history-and-offline-research-"


def _private_dir(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("private replay source or destination unavailable")
    return path


def _one_private_write(path: Path, content: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("immutable replay path already exists")
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as out:
        os.fchmod(out.fileno(),0o600)
        out.write(content)
        out.flush()
        os.fsync(out.fileno())


def _manifest_plan(original: Mapping[str, object]) -> dict[str, object]:
    if (not isinstance(original,Mapping) or
            original.get("kind") !=
            "HISTORICAL_MULTIASSET_SHA_BOUND_THREE_COST_SCENARIOS_NO_ORDERS" or
            original.get("schema_version") != 1 or
            original.get("market") != "crypto" or
            original.get("broker_order_submission") != "DISABLED" or
            original.get("strategy_promoted") is not False or
            original.get("independent_forward_strategy_edge_established") is not False or
            original.get("data_is_historical_not_new_prospective_observations") is not True):
        raise ValueError("untrusted historical source report")
    names=original.get("symbols")
    windows=original.get("predeclared_request_windows")
    audits=original.get("historical_archive_audit")
    if (not isinstance(names,list) or not isinstance(windows,list)
            or not isinstance(audits,list) or len(windows)!=len(audits)
            or not 1<=len(windows)<=30
            or not 1<=len(names)<=6 or names!=sorted(set(names))):
        raise ValueError("invalid complete historical source manifest")
    try:
        start=aware(windows[0]["start_utc"])
        end=aware(windows[-1]["end_utc"])
    except (KeyError,TypeError,ValueError,IndexError) as exc:
        raise ValueError("historical source has missing requested window bounds") from exc
    plan=historical_plan(
        symbols=tuple(names),start=start,end=end,market=AssetClass.CRYPTO)
    if plan["windows"]!=windows:
        raise ValueError("old report's requested history windows are incomplete/noncontiguous")
    return plan


def reanalyze_existing_history(
    *, source: Path=SRC, destination: Path=DEST,
    source_run_id: int,
    report_builder: Callable[...,dict[str,object]]=analyze_manual_history,
) -> dict[str,object]:
    """One restricted copy and offline re-analysis, no new provider requests."""
    if type(source_run_id) is not int or not 1<=source_run_id<=10**14:
        raise ValueError("explicit bounded previous GitHub run ID required")
    root=_private_dir(source)
    if root.stat().st_mode & 0o002:
        raise ValueError("artifact source folder may not be world-writable")
    if destination.exists() or destination.is_symlink():
        raise ValueError("replay output folder must not exist before this run")
    source_report_path=root/ANALYSIS_FILENAME
    if (source_report_path.is_symlink() or not source_report_path.is_file()
            or not 0<source_report_path.stat().st_size<=2_000_000):
        raise ValueError("original offline historical analysis report missing")
    original=json.loads(source_report_path.read_bytes())
    plan=_manifest_plan(original)
    manifests=original["historical_archive_audit"]
    expected_names=[entry["filename"] for entry in manifests]
    if (len(expected_names)!=len(set(expected_names)) or
            any(not isinstance(name,str) or
                not HISTORICAL_NAME.fullmatch(name) for name in expected_names)):
        raise ValueError("unrecognized or duplicate old historical filename")
    original_files=[
        entry for entry in root.iterdir()
        if HISTORICAL_NAME.fullmatch(entry.name)
    ]
    if (set(entry.name for entry in original_files)!=set(expected_names) or
            any(entry.is_symlink() or not entry.is_file() for entry in original_files)):
        raise ValueError("missing/extra/symlinked original historical captures")
    audited_bytes={}
    for entry in manifests:
        basename=entry["filename"]
        expected_sha=entry["sha256"]
        if (not isinstance(expected_sha,str) or
                not re.fullmatch(r"[0-9a-f]{64}",expected_sha)):
            raise ValueError("original history lacks valid content SHA")
        blob=(root/basename).read_bytes()
        if not 0<len(blob)<=8_000_000 or hashlib.sha256(blob).hexdigest()!=expected_sha:
            raise ValueError("original historical dataset SHA does not match report")
        audited_bytes[basename]=blob

    # No on-disk output exists until all source archives have passed their
    # exact original SHA audit. Old source artifact remains UNCHANGED.
    destination.mkdir(mode=0o700)
    if destination.stat().st_mode & 0o077:
        raise PermissionError("replay output directory must be private")
    for basename,content in audited_bytes.items():
        _one_private_write(destination/basename,content)
    verified=audit_requested_archives(destination,plan=plan)
    if set(x.name for x in verified)!=set(expected_names):
        raise ValueError("new copy fails independent per-window historical audit")
    result=report_builder(folder=destination,plan=plan)
    if (result.get("broker_order_submission")!="DISABLED" or
            result.get("status")!="COMPLETE_HISTORICAL_DATA_AND_THREE_COST_SCENARIOS"):
        raise ValueError("re-analysis did not finish all predeclared cost scenarios")
    output=destination/ANALYSIS_FILENAME
    report=json.loads(output.read_bytes())
    if (report.get("simulation_accounting_version")!=
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt" or
            report.get("broker_order_submission")!="DISABLED" or
            report.get("strategy_promoted") is not False):
        raise ValueError("v2 report provenance or safety contract failed")
    old_sha=hashlib.sha256(source_report_path.read_bytes()).hexdigest()
    new_sha=hashlib.sha256(output.read_bytes()).hexdigest()
    if old_sha==new_sha:
        raise ValueError("corrected model must create distinguishable provenance")
    replay={
        "kind":"OFFLINE_HISTORICAL_REPLAY_SOURCE_SHA_PRESERVED",
        "schema_version":1,
        "source_repo":"Nkreddy15/signal-vault",
        "source_workflow_run_id":source_run_id,
        "original_analysis_report_sha256":old_sha,
        "source_archive_sha256_by_name":{
            entry["filename"]:entry["sha256"] for entry in manifests},
        "corrected_analysis_report_sha256":new_sha,
        "corrected_simulation_accounting_version":
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt",
        "source_archive_content_changed":False,
        "historical_not_forward_evidence":True,
        "model_selected_on_holdout":False,
        "alpaca_market_data_requests":"NONE",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    manifest=(json.dumps(replay,indent=2,sort_keys=True)+"\n").encode("utf-8")
    _one_private_write(destination/MANIFEST,manifest)
    return {
        "kind":"OFFLINE_HISTORY_RISK_V2_REPLAY_COMPLETE",
        "source_run_id":source_run_id,
        "source_archive_count":len(verified),
        "source_analysis_report_sha256":old_sha,
        "corrected_analysis_report_sha256":new_sha,
        "replay_manifest_sha256":hashlib.sha256(manifest).hexdigest(),
        "simulation_accounting_version":
            "v2_utc_daily_reset_plus_persistent_peak_drawdown_halt",
        "no_new_market_data_requests":True,
        "credential_access":"NONE",
        "historical_only":True,
        "broker_order_submission":"DISABLED",
    }


def main() -> int:
    """Refuse PR/push/tag/fork execution; do not print untrusted exception text."""
    try:
        env=os.environ
        if (env.get("GITHUB_ACTIONS")!="true" or
                env.get("GITHUB_EVENT_NAME")!="workflow_dispatch" or
                env.get("GITHUB_REPOSITORY")!="Nkreddy15/signal-vault" or
                env.get("GITHUB_REF")!="refs/heads/main" or
                env.get("SIGNAL_VAULT_REPLAY_MODE")!="EXISTING_PRIVATE_HISTORY_ONLY"):
            raise PermissionError("explicit private main-only replay required")
        run_id=int(env.get("SIGNAL_VAULT_REPLAY_SOURCE_RUN_ID",""))
        value=reanalyze_existing_history(source_run_id=run_id)
        print(json.dumps(value,indent=2,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"OFFLINE_HISTORY_RISK_V2_REPLAY",
            "status":"BLOCKED_PRESERVE_ORIGINAL_HISTORICAL_ARTIFACT",
            "failure_class":type(exc).__name__,
            "credential_access":"NONE",
            "alpaca_market_data_requests":"NONE",
            "broker_order_submission":"DISABLED",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
