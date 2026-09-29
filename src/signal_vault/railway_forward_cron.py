"""Railway CRON adapter for the isolated forward DATA GET collector.

Railway runs a new short-lived process at UTC minute :07, NOT a 24h daemon.
Railway-managed private variables are used instead of Docker Compose file
secrets; they are read only inside the provider factory after the original
time/evidence checks. No generic Alpaca key fallback, paper-account trading
API, Keychain, broker order path, POST, or live host.

Absent persistent Railway volume or missing explicit credential variable names
blocks BEFORE capture. No local fallback can silently write ephemeral evidence.
Volume mount path is checked against Railway's own injected metadata.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .cloud_forward_service import (
    CLOUD_ROOT, _private_volume, cloud_cycle_once, cloud_status,
)
from .forward_capture import _read_data_get_no_redirect
from .market_data import AlpacaAuthenticatedCryptoBars
from .paper_credentials import PaperCredentials
from .unattended_forward_cycle import FORBIDDEN_ENV

KEY_VARIABLE = "SIGNAL_VAULT_FORWARD_DATA_KEY_ID"
SECRET_VARIABLE = "SIGNAL_VAULT_FORWARD_DATA_SECRET"
RAILWAY_MOUNT_VARIABLE = "RAILWAY_VOLUME_MOUNT_PATH"
FORBIDDEN_VARIABLES = FORBIDDEN_ENV + (
    "ALPACA_PAPER_KEY_ID",
    "ALPACA_PAPER_SECRET_KEY",
    "SIGNAL_VAULT_ENABLE_PAPER_ORDERS",
    "SIGNAL_VAULT_MODE",
)


def railway_data_credentials(*, environ: Mapping[str, str] | None = None) -> PaperCredentials:
    """Read only the two dedicated Railway DATA variable values; NEVER log."""
    env = os.environ if environ is None else environ
    if any(str(env.get(name, "")).strip() for name in FORBIDDEN_VARIABLES):
        raise ValueError("generic, live or order-enabled environment forbidden")
    key = env.get(KEY_VARIABLE)
    secret = env.get(SECRET_VARIABLE)
    if not isinstance(key, str) or not isinstance(secret, str):
        raise ValueError("both private DATA service variables are required")
    if key != key.strip() or secret != secret.strip():
        raise ValueError("DATA variables contain unexpected whitespace")
    return PaperCredentials(key, secret)


def railway_provider():
    """This factory is called only AFTER collector time, pause and archive preflight."""
    keys = railway_data_credentials()
    return AlpacaAuthenticatedCryptoBars(
        keys.key_id, keys.secret_key, transport=_read_data_get_no_redirect)


def configured_railway_volume(
    *, environ: Mapping[str, str] | None = None,
    expected_root: Path = CLOUD_ROOT,
    allow_owner_permission_repair: bool = False,
) -> Path:
    """Prove this is an attached volume, never accidentally use image-local disk.

    Railway mounts its volume root-owned; its documentation recommends running
    with RAILWAY_RUN_UID=0. That is a deliberate Railway-specific operational
    tradeoff. Repair only exact expected mount root permissions, never parent
    directories, capture files, original journals, or any symlink.
    """
    env = os.environ if environ is None else environ
    marker = env.get(RAILWAY_MOUNT_VARIABLE)
    if not isinstance(marker, str) or marker != str(expected_root):
        raise ValueError("exact Railway persistent volume mount marker required")
    if expected_root.is_symlink() or not expected_root.is_dir():
        raise ValueError("expected Railway evidence mount missing or symlink")
    if not stat.S_ISDIR(expected_root.stat().st_mode):
        raise ValueError("Railway volume must be a real directory")
    if expected_root.stat().st_mode & 0o077:
        if not allow_owner_permission_repair or os.geteuid() != 0:
            raise PermissionError("persistent volume root must be private (0700)")
        # A first-time Railway mount can be root-owned and world-readable.
        # Only restrict the dedicated mount root; no data is erased or moved.
        os.chmod(expected_root, 0o700)
    return _private_volume(expected_root)


def railway_once(
    *,
    now: datetime,
    environ: Mapping[str, str] | None = None,
    expected_root: Path = CLOUD_ROOT,
    provider_factory=railway_provider,
    after_capture_now=None,
) -> dict[str, object]:
    """One UTC schedule tick; always returns credential-free public status."""
    env = os.environ if environ is None else environ
    out: dict[str, object] = {
        "kind": "RAILWAY_ISOLATED_CRON_FORWARD_DATA_GET_ONLY",
        "status": "BLOCKED_NO_COLLECTION",
        "reason_code": "NOT_CHECKED",
        "broker_order_submission": "DISABLED",
        "automatic_paper_trading": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "credential_values_in_output": False,
        "old_mac_collector_modified": False,
    }
    try:
        root = configured_railway_volume(
            environ=env, expected_root=expected_root,
            allow_owner_permission_repair=True)
    except Exception as exc:
        out.update(reason_code="RAILWAY_PERSISTENT_VOLUME_NOT_READY",
                   failure_class=type(exc).__name__)
        return out

    # Before creating any operational receipt, ensure the Railway service is
    # configured with BOTH dedicated variable names and no unsafe fallback.
    # Values are NOT accessed here; the provider validates them just in time
    # after original collector's strict time and archive preflight.
    if (not isinstance(env.get(KEY_VARIABLE), str)
            or not isinstance(env.get(SECRET_VARIABLE), str)
            or not env[KEY_VARIABLE] or not env[SECRET_VARIABLE]
            or any(str(env.get(name, "")).strip() for name in FORBIDDEN_VARIABLES)):
        out["reason_code"] = "DEDICATED_DATA_VARIABLE_NAMES_NOT_READY_OR_UNSAFE_ENV"
        return out
    result = cloud_cycle_once(
        root=root, now=now, provider_factory=provider_factory,
        after_capture_now=after_capture_now)
    out.update({
        "status": result["status"],
        "reason_code": result["reason_code"],
        "collector_decision": result.get("collector_decision"),
        "prospective_observations_verified": result.get("prospective_observations_verified"),
        "shadow_signal_count": result.get("shadow_signal_count"),
        "shadow_receipt": result.get("shadow_receipt"),
        "failure_class": result.get("failure_class"),
    })
    return out


def railway_preflight(
    *, environ: Mapping[str, str] | None = None,
    expected_root: Path = CLOUD_ROOT,
) -> dict[str, object]:
    """No-network check. Never prints Railway secret values."""
    env = os.environ if environ is None else environ
    out = {
        "kind": "RAILWAY_FORWARD_CREDENTIAL_AND_VOLUME_PREFLIGHT_NO_NETWORK",
        "status": "BLOCKED",
        "network_requests": "NONE",
        "broker_order_submission": "DISABLED",
        "secrets_logged": False,
        "service_deployed_by_preflight": False,
    }
    try:
        configured_railway_volume(environ=env, expected_root=expected_root,
                                  allow_owner_permission_repair=False)
        railway_data_credentials(environ=env)
        out.update(status="RAILWAY_LOCAL_PREFLIGHT_PASS_NO_NETWORK",
                   reason_code="NONE")
    except Exception as exc:
        out.update(reason_code="VOLUME_OR_DATA_VARIABLES_NOT_READY",
                   failure_class=type(exc).__name__)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Railway UTC cron DATA GET only; never PAPER/live trading.")
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument("--once", action="store_true")
    flags.add_argument("--preflight", action="store_true")
    flags.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.once:
        result = railway_once(now=datetime.now(timezone.utc))
        code = 0 if result["status"] in (
            "ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED",
            "HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW",
            "SAFE_NO_NEW_OBSERVATION") else 2
    elif args.preflight:
        result = railway_preflight()
        code = 0 if result["status"] == "RAILWAY_LOCAL_PREFLIGHT_PASS_NO_NETWORK" else 2
    else:
        try:
            root = configured_railway_volume(allow_owner_permission_repair=False)
            result = cloud_status(root=root)
            code = 0 if result["status"] in (
                "PAUSED", "READ_ONLY_STATUS_AVAILABLE") else 2
        except Exception as exc:
            result = {
                "kind": "RAILWAY_OFFLINE_COLLECTOR_STATUS",
                "status": "BLOCKED",
                "reason_code": "RAILWAY_PERSISTENT_VOLUME_NOT_READY",
                "failure_class": type(exc).__name__,
                "broker_order_submission": "DISABLED",
                "network_requests": "NONE",
                "credential_access": "NONE",
            }
            code = 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
