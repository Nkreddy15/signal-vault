"""GitHub Actions manually dispatched HISTORICAL crypto GET-only entrypoint.

Does not run in PR checks, at import time, on push, in Railway, on a schedule,
or from a local developer shell. Requires a human to set dedicated GitHub
Actions secrets in the PRIVATE repo and click Run workflow on main.

No paper account, order POST, live endpoint or key logging. The default
repository workflow uses BTC/USD and ETH/USD first, then permits the remaining
predeclared crypto universe after independently confirming provider support.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .multi_asset_research_cli import aware, download_history, historical_plan
from .research_universe import AssetClass, candidate
from .unattended_forward_cycle import FORBIDDEN_ENV

KEY_ENV="SIGNAL_VAULT_RESEARCH_DATA_KEY_ID"
SECRET_ENV="SIGNAL_VAULT_RESEARCH_DATA_SECRET"
APPROVAL_ENV="SIGNAL_VAULT_RESEARCH_READ_APPROVED"
OUTPUT=Path("private-historical-artifacts")
ALLOWED_CRYPTO={
    "BTC/USD","ETH/USD","SOL/USD","LTC/USD","LINK/USD","AVAX/USD",
}
BLOCK_EXTRA=FORBIDDEN_ENV+(
    "ALPACA_PAPER_KEY_ID","ALPACA_PAPER_SECRET_KEY",
    "SIGNAL_VAULT_ENABLE_PAPER_ORDERS",
)


def resolve_manual_ci_configuration(*, env: Mapping[str,str]) -> dict[str,object]:
    """No secrets included in returned plan; deny all non-main/manual contexts."""
    if (env.get("GITHUB_ACTIONS")!="true" or
            env.get("GITHUB_EVENT_NAME")!="workflow_dispatch" or
            env.get("GITHUB_REPOSITORY")!="Nkreddy15/signal-vault" or
            env.get("GITHUB_REF")!="refs/heads/main" or
            env.get(APPROVAL_ENV)!="HISTORICAL_CRYPTO_DATA_GET_ONLY" or
            any(str(env.get(name,"")).strip() for name in BLOCK_EXTRA)):
        raise PermissionError("research data-only workflow context/approval invalid")
    symbols=tuple(env.get("SIGNAL_VAULT_RESEARCH_SYMBOLS","").split())
    if (not 1<=len(symbols)<=6 or len(symbols)!=len(set(symbols)) or
            set(symbols)-ALLOWED_CRYPTO or
            any(candidate(sym).asset_class!=AssetClass.CRYPTO for sym in symbols)):
        raise ValueError("manual workflow symbols exceed predeclared crypto universe")
    start=aware(env["SIGNAL_VAULT_RESEARCH_START_UTC"])
    end=aware(env["SIGNAL_VAULT_RESEARCH_END_UTC"])
    if end > datetime.now(timezone.utc)-timedelta(hours=1):
        raise ValueError("manual historical backfill requires an already closed period")
    plan=historical_plan(
        symbols=symbols,start=start,end=end,market=AssetClass.CRYPTO)
    return {"symbols":symbols,"start":start,"end":end,"plan":plan}


def ci_entry(*, env: Mapping[str,str]|None=None,
             downloader=download_history) -> dict[str,object]:
    current=os.environ if env is None else env
    options=resolve_manual_ci_configuration(env=current)
    key=current.get(KEY_ENV)
    secret=current.get(SECRET_ENV)
    if (not isinstance(key,str) or not isinstance(secret,str) or
            not key or not secret or key!=key.strip() or secret!=secret.strip()):
        raise PermissionError("two dedicated GitHub Actions research DATA secrets missing")
    if OUTPUT.is_symlink() or OUTPUT.exists():
        if OUTPUT.is_symlink() or not OUTPUT.is_dir() or OUTPUT.stat().st_mode & 0o077:
            raise PermissionError("unsafe historical-only artifact folder")
        if any(OUTPUT.iterdir()):
            raise ValueError("refusing to mix existing run files into research artifact")
    else:
        OUTPUT.mkdir(mode=0o700)
    result=downloader(
        symbols=options["symbols"],start=options["start"],end=options["end"],
        market=AssetClass.CRYPTO,equity_feed=None,
        output_folder=OUTPUT,key_id=key,secret=secret)
    if not isinstance(result,dict) or result.get("broker_order_submission")!="DISABLED":
        raise ValueError("invalid expected historical read-only download result")
    return result


def main() -> int:
    """Fail with exception CLASS only; avoid printing third-party error bodies."""
    try:
        result=ci_entry()
        print(json.dumps(result,indent=2,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind":"MANUAL_HISTORICAL_GET_ONLY_CI_CAPTURE",
            "status":"FAIL_CLOSED_NO_COMPLETE_DATASET_CLAIM",
            "failure_class":type(exc).__name__,
            "credential_values_in_output":False,
            "broker_order_submission":"DISABLED",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
