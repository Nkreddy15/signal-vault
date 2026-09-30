"""Read-only activation preflight for the existing Railway research service.

This does not start collectors, create directories, read credentials, contact
providers, or submit orders. It validates only the exact opt-in flags and the
existing shared-volume contract required before the all-market cron is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from .cloud_forward_service import CLOUD_ROOT
from .equity_cloud_sidecar import (
    ACTIVATION as EQUITY_ACTIVATION_VALUE,
    ACTIVATION_ENV as EQUITY_ACTIVATION_ENV,
)
from .kalshi_cloud_sidecar import (
    ACTIVATION_ENV as KALSHI_ACTIVATION_ENV,
    ACTIVATION_VALUE as KALSHI_ACTIVATION_VALUE,
)
from .railway_btc_first_dual_cron import (
    ACTIVATION_FLAG as CRYPTO_ACTIVATION_ENV,
    ACTIVATION_VALUE as CRYPTO_ACTIVATION_VALUE,
    BTC_FINGERPRINT_EXCLUDED_CHILDREN,
)

EXPECTED_START_COMMAND="python -m signal_vault.railway_all_markets_research_cron --once"
EXPECTED_CRON="7 * * * *"


def all_market_activation_preflight(
    *,
    environ:Mapping[str,str]|None=None,
    root:Path=CLOUD_ROOT,
    observed_start_command:str|None=None,
    observed_cron_schedule:str|None=None,
)->dict[str,object]:
    env=os.environ if environ is None else environ
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode&0o077:
        raise ValueError("existing forward evidence root must be private real directory")

    crypto_exact=env.get(CRYPTO_ACTIVATION_ENV)==CRYPTO_ACTIVATION_VALUE
    equity_exact=env.get(EQUITY_ACTIVATION_ENV)==EQUITY_ACTIVATION_VALUE
    kalshi_exact=env.get(KALSHI_ACTIVATION_ENV)==KALSHI_ACTIVATION_VALUE

    start_exact=(
        None if observed_start_command is None
        else observed_start_command==EXPECTED_START_COMMAND
    )
    cron_exact=(
        None if observed_cron_schedule is None
        else observed_cron_schedule==EXPECTED_CRON
    )

    active_lanes=[
        name
        for name,active in (
            ("six_crypto",crypto_exact),
            ("us_equity",equity_exact),
            ("kalshi",kalshi_exact),
        )
        if active
    ]
    missing=[
        name
        for name,active in (
            (CRYPTO_ACTIVATION_ENV,crypto_exact),
            (EQUITY_ACTIVATION_ENV,equity_exact),
            (KALSHI_ACTIVATION_ENV,kalshi_exact),
        )
        if not active
    ]

    ready=(
        crypto_exact
        and equity_exact
        and kalshi_exact
        and (start_exact in (None,True))
        and (cron_exact in (None,True))
    )

    return {
        "kind":"ALL_MARKET_EXISTING_RAILWAY_ACTIVATION_PREFLIGHT_NO_ORDERS",
        "shared_forward_root":str(root),
        "shared_forward_root_matches_expected":root.resolve()==CLOUD_ROOT.resolve(),
        "expected_start_command":EXPECTED_START_COMMAND,
        "observed_start_command":observed_start_command,
        "start_command_exact":start_exact,
        "expected_cron_schedule":EXPECTED_CRON,
        "observed_cron_schedule":observed_cron_schedule,
        "cron_schedule_exact":cron_exact,
        "activation_flags":{
            "six_crypto":crypto_exact,
            "us_equity":equity_exact,
            "kalshi":kalshi_exact,
        },
        "active_research_lanes":active_lanes,
        "missing_or_unrecognized_activation_envs":missing,
        "explicit_research_children":list(BTC_FINGERPRINT_EXCLUDED_CHILDREN),
        "all_three_research_lanes_explicitly_activated":(
            crypto_exact and equity_exact and kalshi_exact
        ),
        "ready_for_existing_service_all_market_cron":ready,
        "new_Railway_service_required":False,
        "new_Railway_volume_required":False,
        "new_paid_resource_required":False,
        "network_requests":"NONE",
        "credential_access":"NONE",
        "broker_order_submission":"DISABLED",
        "paper_order_submission":"DISABLED",
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_trading":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }


def main()->int:
    try:
        result=all_market_activation_preflight()
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0 if result["ready_for_existing_service_all_market_cron"] else 2
    except Exception as exc:
        print(json.dumps({
            "kind":"ALL_MARKET_EXISTING_RAILWAY_ACTIVATION_PREFLIGHT_NO_ORDERS",
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "network_requests":"NONE",
            "credential_access":"NONE",
            "broker_order_submission":"DISABLED",
            "paper_order_submission":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
