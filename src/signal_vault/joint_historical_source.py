"""PRIVATE keyless two-artifact -> synchronized 12-asset common-horizon study.

Accept either an owner's historical crypto+IEX ZIPs or flat directories
created by GitHub actions/download-artifact. Repack retrieved directory
files ONLY into safe bounded temporary ZIPs. Independently re-audit BOTH
original source SHA manifests, stock XNYS calendar, cost assumptions and
all original three-case baseline reports before permitting a joint
historical analysis. No Alpaca key/account network or broker order API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime,timezone
from pathlib import Path

from .ci_historical_report import ANALYSIS_FILENAME,audit_requested_archives,SCENARIOS
from .ci_replay_history import _manifest_plan
from .cross_market_joint_review import (
    CRYPTO_SIX,STOCK_SIX,
    evaluate_predeclared_twelve_market_common_history,
)
from .offline_equity_zip_audit import (
    REPORT as STOCK_REPORT,SOURCE_NAME as STOCK_SOURCE_RE,
    _read_safe_zip,audit_equity_history_zip,
)
from .offline_multimarket_pipeline import (
    combine_historical_archives,read_historical_archive,
)
from .offline_zip_attribution import (
    SOURCE_ARCHIVE_RE as CRYPTO_SOURCE_RE,
    _read_bounded_zip,analyze_six_asset_zip,
)
from .research_universe import candidate,AssetClass

# Exact immutable stock run already independently captured, SHA-checked and
# saved to Library. A human-approved *new* stock run requires a reviewed
# new immutable source digest; no silent fallback or changed feed.
STOCK_REFERENCE_RUN_ID = 36637836735
STOCK_REFERENCE_REPORT_SHA256 = (
    "15010a1cbf376264423c5cb08cd58075c2e9d7319a74037b41d3683d819f2e6f"
)
MAX_ARTIFACT_INPUT_BYTES = 40_000_000


def _create_exact(path:Path,blob:bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("no overwriting a historical source or existing report")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as dest:
        os.fchmod(dest.fileno(),0o600)
        dest.write(blob);dest.flush();os.fsync(dest.fileno())


def _eligible_name(name:str, market:str) -> bool:
    if market=="crypto":
        return bool(
            name==ANALYSIS_FILENAME or
            name in {"cost_assumptions-"+label+".json" for label in SCENARIOS}
            or CRYPTO_SOURCE_RE.fullmatch(name))
    if market=="us_equity":
        return bool(name==STOCK_REPORT or STOCK_SOURCE_RE.fullmatch(name))
    raise ValueError("unknown zipped market")


def _normalize_artifact_path(source:Path,market:str,root:Path) -> Path:
    if source.is_symlink():
        raise ValueError("artifact path may not be a symlink")
    if source.is_file():
        if not 0<source.stat().st_size<=MAX_ARTIFACT_INPUT_BYTES:
            raise ValueError("oversized/missing historical artifact")
        return source
    if not source.is_dir():
        raise ValueError("historical artifact must be an exact file or flat folder")
    entries=tuple(source.iterdir())
    if (not entries or len(entries)>40 or
            any(not entry.is_file() or entry.is_symlink() or
                not _eligible_name(entry.name,market)
                for entry in entries) or
            len({entry.name for entry in entries})!=len(entries) or
            sum(e.stat().st_size for e in entries)>MAX_ARTIFACT_INPUT_BYTES):
        raise ValueError("invalid, nested or nonallowlisted extracted research files")
    target=root/("temporary-"+market+".zip")
    if target.exists():
        raise ValueError("temporary artifact repack path already exists")
    with zipfile.ZipFile(target,"x",compression=zipfile.ZIP_DEFLATED) as z:
        for entry in sorted(entries,key=lambda item:item.name):
            raw=entry.read_bytes()
            if not raw or len(raw)>8_000_000:
                raise ValueError("oversized/missing bounded artifact member")
            z.writestr(entry.name,raw)
    return target


def analyze_two_verified_history_artifacts(
    *,
    crypto_artifact:Path,
    stock_artifact:Path,
    require_reference_stock_digest:bool=True,
    include_order_sensitivity:bool=False,
) -> dict[str,object]:
    """Fail closed when the old July-Aug crypto & Sep stock data do NOT overlap."""
    with tempfile.TemporaryDirectory(
            prefix="signal-vault-offline-two-class-study-") as folder:
        root=Path(folder)
        root.chmod(0o700)
        cp=_normalize_artifact_path(Path(crypto_artifact),"crypto",root)
        sp=_normalize_artifact_path(Path(stock_artifact),"us_equity",root)
        ccheck=analyze_six_asset_zip(cp)
        scheck=audit_equity_history_zip(sp)
        cbytes=_read_bounded_zip(cp)
        sbytes=_read_safe_zip(sp)
        if (require_reference_stock_digest and
                scheck["original_stock_report_sha256"]!=
                STOCK_REFERENCE_REPORT_SHA256):
            raise ValueError("stock history differs from reviewed exact provider run")

        crypto_report=json.loads(cbytes[ANALYSIS_FILENAME])
        crypto_plan=_manifest_plan(crypto_report)
        if (tuple(sorted(crypto_plan["symbols"]))!=CRYPTO_SIX or
                ccheck["assets"]!=list(CRYPTO_SIX) or
                scheck["symbols"]!=list(STOCK_SIX)):
            raise ValueError("not the entire registered twelve-asset source cohort")
        crypto_root=root/"crypto-source"
        stock_root=root/"stock-source"
        crypto_root.mkdir(mode=0o700)
        stock_root.mkdir(mode=0o700)
        for item in crypto_report["historical_archive_audit"]:
            name=item["filename"]
            _create_exact(crypto_root/name,cbytes[name])
        cpaths=audit_requested_archives(crypto_root,plan=crypto_plan)
        cbatches=tuple(read_historical_archive(p) for p in cpaths)
        crypto_as_of=max(datetime.fromisoformat(b.downloaded_utc)
                         .astimezone(timezone.utc) for b in cbatches)
        crypto,crypto_reviews=combine_historical_archives(
            cbatches,as_of=crypto_as_of)
        if set(crypto)!=set(CRYPTO_SIX):
            raise ValueError("incomplete six-asset crypto history")
        stocks_report=json.loads(sbytes[STOCK_REPORT])
        for item in stocks_report["source_sha256"]:
            name=item["filename"]
            _create_exact(stock_root/name,sbytes[name])
        sbatches=tuple(read_historical_archive(stock_root/item["filename"])
                       for item in stocks_report["source_sha256"])
        stock_as_of=max(datetime.fromisoformat(b.downloaded_utc)
                        .astimezone(timezone.utc) for b in sbatches)
        grid=tuple(datetime.fromisoformat(t) for t in
                   scheck["distinct_common_regular_core_utc_opens"])
        stocks,stock_reviews=combine_historical_archives(
            sbatches,as_of=stock_as_of,
            equity_calendars={sym:grid for sym in STOCK_SIX})
        if stocks_report["quality_reviews"]!=stock_reviews:
            raise ValueError("stock ZIP source quality report disagrees with reloaded source")
        if (crypto_report["scenarios"]["illustrative_base_friction"][
                "offline_report"]["asset_quality_reviews"]!=crypto_reviews):
            raise ValueError("crypto ZIP source quality differs from original SHA report")
        result=evaluate_predeclared_twelve_market_common_history(
            crypto=crypto,equities=stocks,
            independently_verified_stock_core_opens_utc=grid,
            as_of=max(crypto_as_of,stock_as_of),
            include_order_sensitivity=include_order_sensitivity)
        return {
            **result,
            "source_pair_provenance":{
                "crypto_original_historical_GitHub_ZIP_SHA256_or_local_repack":
                    hashlib.sha256(cp.read_bytes()).hexdigest(),
                "crypto_original_offline_report_SHA256":
                    ccheck["source_research_report_sha256"],
                "crypto_original_session_archive_SHA256":
                    ccheck["original_historical_archives_sha256"],
                "stock_original_historical_GitHub_ZIP_SHA256_or_local_repack":
                    hashlib.sha256(sp.read_bytes()).hexdigest(),
                "stock_original_offline_report_SHA256":
                    scheck["original_stock_report_sha256"],
                "stock_expected_reference_run_id":
                    STOCK_REFERENCE_RUN_ID if require_reference_stock_digest else None,
                "stock_original_session_archive_SHA256":
                    scheck["original_session_sha256_by_name"],
                "new_historical_downloads_triggered_by_this_joint_analysis":0,
                "stock_and_crypto_artifact_bytes_modified":False,
            },
        }


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(
        description="Offline SHA-audited 12-asset source-artifact comparison; NO provider calls.")
    parser.add_argument("--crypto-artifact",required=True,type=Path)
    parser.add_argument("--stock-artifact",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--allocation-sensitivity",action="store_true",
                        help="add three fixed class-based tie-order alternatives; no optimizer")
    args=parser.parse_args(argv)
    study=analyze_two_verified_history_artifacts(
        crypto_artifact=args.crypto_artifact,
        stock_artifact=args.stock_artifact,
        include_order_sensitivity=args.allocation_sensitivity)
    raw=(json.dumps(study,indent=2,sort_keys=True)+"\n").encode("utf-8")
    _create_exact(args.output,raw)
    print(json.dumps({
        "kind":"OFFLINE_TWELVE_ASSET_EXACT_TWO_SOURCE_REVIEW",
        "status":"COMPLETE_COMMON_HORIZON_RESEARCH_NOT_VALIDATED_STRATEGY",
        "source_asset_count":12,
        "stock_common_hour_count":study["stock_and_crypto_time_compatibility"][
            "common_source_closed_bar_open_hours"],
        "post_warmup_stock_core_hour_count":
            study["evaluated_stock_regular_CORE_hour_opens_after_global_warmup"],
        "report_basename":args.output.name,
        "allocation_sensitivity_included":args.allocation_sensitivity,
        "report_sha256":hashlib.sha256(raw).hexdigest(),
        "keys_or_network_or_broker_orders":"NONE",
    },indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
