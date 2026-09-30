"""Unattended Railway-compatible GET-only US-equity forward sidecar.

Designed for the existing hourly :07 cloud cadence:
- before the XNYS open, archive the day's immutable six-stock session plan;
- during each planned post-close window, capture exactly one six-stock IEX bar;
- if the pre-open plan was missed, never recreate it after the open;
- repeated invocations are idempotent and avoid duplicate provider reads.

This module has no broker/account/order imports. Paper and live order submission
remain disabled.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping
from zoneinfo import ZoneInfo

from .equity_forward_collector import (
    archive_equity_forward_session_plan,
    archive_prospective_equity_hour,
    collect_precommitted_equity_hour,
    precommit_equity_forward_session,
    _validate_plan,
)
from .multi_asset_historical import BoundedAlpacaHistoricalBatch

ACTIVATION = "STOCK_FORWARD_GET_ONLY_NO_ORDERS_V1"
ACTIVATION_ENV = "SIGNAL_VAULT_SIX_EQUITY_SIDECAR"
KEY_ENV = "SIGNAL_VAULT_FORWARD_DATA_KEY_ID"
SECRET_ENV = "SIGNAL_VAULT_FORWARD_DATA_SECRET"
ROOT_ENV = "SIGNAL_VAULT_FORWARD_ROOT"
DEFAULT_ROOT = Path("/var/lib/signal-vault/forward")
CHILD = "isolated-six-stock-prospective"
NY = ZoneInfo("America/New_York")


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timezone-aware cloud stock timestamp required")
    return value.astimezone(timezone.utc)


def _root_from_env(env: Mapping[str, str]) -> Path:
    raw = env.get(ROOT_ENV, str(DEFAULT_ROOT))
    if not isinstance(raw, str) or not raw.startswith("/"):
        raise ValueError("absolute forward evidence root required")
    root = Path(raw)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("forward evidence root must already exist")
    child = root / CHILD
    if child.exists() or child.is_symlink():
        if child.is_symlink() or not child.is_dir():
            raise ValueError("stock sidecar path must be a real directory")
    else:
        child.mkdir(mode=0o700)
    child.chmod(0o700)
    if child.stat().st_mode & 0o077:
        raise PermissionError("stock sidecar directory must be private")
    return child


def _plan_path_for_date(root: Path, trading_date: str) -> Path | None:
    matches = tuple(
        root.glob(
            "equity-forward-plan-"
            + trading_date.replace("-", "")
            + "-*.json"
        )
    )
    if len(matches) > 1:
        raise ValueError("multiple stock session plans for one trading date")
    return matches[0] if matches else None


def _load_plan(path: Path) -> dict[str, object]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_mode & 0o077
        or not 0 < path.stat().st_size <= 1_000_000
    ):
        raise ValueError("unsafe stock session-plan file")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("stock session plan must be a JSON object")
    _validate_plan(value)
    return value


def _existing_receipt_for_hour(root: Path, opened: datetime) -> Path | None:
    prefix = "equity-forward-" + opened.strftime("%Y%m%dT%H%MZ") + "-"
    matches = tuple(root.glob(prefix + "*.json"))
    if len(matches) > 1:
        raise ValueError("multiple stock receipts for one planned core hour")
    return matches[0] if matches else None


def _safe_result(status: str, **extra: object) -> dict[str, object]:
    return {
        "kind": "RAILWAY_SIX_STOCK_GET_ONLY_FORWARD_SIDECAR",
        "status": status,
        **extra,
        "network_method_allowlist": ["GET"],
        "broker_order_submission": "DISABLED",
        "paper_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
        "automatic_live_trading": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }


def run_equity_sidecar_once(
    *,
    env: Mapping[str, str] = os.environ,
    now: datetime | None = None,
    provider_factory: Callable[..., BoundedAlpacaHistoricalBatch] = (
        BoundedAlpacaHistoricalBatch
    ),
) -> dict[str, object]:
    moment = _utc(now or datetime.now(timezone.utc))
    if env.get(ACTIVATION_ENV) != ACTIVATION:
        return _safe_result(
            "INACTIVE",
            credentials_accessed=False,
            filesystem_writes=False,
        )

    root = _root_from_env(env)
    local = moment.astimezone(NY)
    trading_date = local.date()
    try:
        planned = precommit_equity_forward_session(
            trading_date=trading_date,
            planned_at=moment,
        )
        market_open = datetime.fromisoformat(
            str(planned["exchange_open_utc"])
        ).astimezone(timezone.utc)
    except ValueError:
        planned = None
        market_open = None

    date_text = trading_date.isoformat()
    plan_path = _plan_path_for_date(root, date_text)

    if plan_path is None and planned is not None and moment < market_open:
        created = archive_equity_forward_session_plan(
            planned,
            output_root=root,
        )
        return _safe_result(
            "PRECOMMITTED_SESSION_PLAN",
            trading_date=date_text,
            plan_file=created.name,
            expected_core_hour_count=planned["expected_core_hour_count"],
            credentials_accessed=False,
            filesystem_writes=True,
        )

    if plan_path is None:
        return _safe_result(
            "NO_CAPTURE_NO_PRECOMMITTED_PLAN",
            trading_date=date_text,
            credentials_accessed=False,
            filesystem_writes=False,
        )

    plan = _load_plan(plan_path)
    target = None
    for raw_open in plan.get("expected_core_opens_utc", []):
        opened = datetime.fromisoformat(str(raw_open)).astimezone(timezone.utc)
        closed = opened + timedelta(hours=1)
        if closed + timedelta(minutes=3) <= moment < closed + timedelta(minutes=30):
            if target is not None:
                raise AssertionError("more than one stock core hour due in one run")
            target = opened

    if target is None:
        return _safe_result(
            "NO_DUE_CORE_HOUR",
            trading_date=date_text,
            credentials_accessed=False,
            filesystem_writes=False,
        )

    existing = _existing_receipt_for_hour(root, target)
    if existing is not None:
        return _safe_result(
            "ALREADY_CAPTURED",
            trading_date=date_text,
            core_open_utc=target.isoformat(),
            receipt_file=existing.name,
            credentials_accessed=False,
            filesystem_writes=False,
        )

    key = env.get(KEY_ENV, "")
    secret = env.get(SECRET_ENV, "")
    if not key or not secret:
        raise PermissionError("dedicated forward PAPER DATA credentials absent")
    item = collect_precommitted_equity_hour(
        plan=plan,
        core_open_utc=target,
        captured_at=moment,
        key=key,
        secret=secret,
        provider_factory=provider_factory,
    )
    receipt = archive_prospective_equity_hour(
        item,
        output_root=root,
    )
    return _safe_result(
        "ONE_SIX_STOCK_CORE_HOUR_CAPTURED",
        trading_date=date_text,
        core_open_utc=target.isoformat(),
        receipt_file=receipt.name,
        prospective_asset_bar_count_added=6,
        credentials_accessed=True,
        credential_values_in_output=False,
        filesystem_writes=True,
    )


def main() -> int:
    try:
        result = run_equity_sidecar_once()
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "kind": "RAILWAY_SIX_STOCK_GET_ONLY_FORWARD_SIDECAR",
            "status": "FAIL_CLOSED",
            "failure_class": type(exc).__name__,
            "network_method_allowlist": ["GET"],
            "broker_order_submission": "DISABLED",
            "paper_order_submission": "DISABLED",
            "live_order_submission": "DISABLED",
            "automatic_live_trading": "DISABLED",
            "live_trading": "UNAVAILABLE",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
