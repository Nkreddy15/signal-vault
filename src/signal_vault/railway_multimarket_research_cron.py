"""Existing-volume BTC + six-crypto + six-stock Railway research cron.

Runs the already-reviewed BTC-first/six-crypto cron first. Only when original
BTC evidence remains healthy does it permit the optional six-stock GET-only
sidecar to run. Both research namespaces are excluded explicitly from the
original BTC mutation fingerprint; every other BTC byte remains covered.

No new Railway service or volume is created here. The stock lane is inactive
unless its exact opt-in flag is present. All order submission remains disabled.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .btc_evidence_fingerprint import fingerprint_btc_evidence_tree
from .cloud_forward_service import CLOUD_ROOT
from .equity_cloud_sidecar import (
    ROOT_ENV as EQUITY_ROOT_ENV,
    run_equity_sidecar_once,
)
from .railway_btc_first_dual_cron import (
    BTC_FINGERPRINT_EXCLUDED_CHILDREN,
    BTC_HEALTHY,
    BTC_MINIMUM_FREE_RESERVE_BYTES,
    combined_btc_first_once,
)

EQUITY_MAX_TOTAL_BYTES = 16 * 1024 * 1024
EQUITY_MAX_NEW_TICK_BUDGET_BYTES = 2 * 1024 * 1024


def _stock_storage_budget(
    *,
    btc_root: Path,
    stock_child_name: str,
) -> dict[str, int]:
    if btc_root.is_symlink() or not btc_root.is_dir():
        raise ValueError("original BTC volume root unavailable")
    stats = os.statvfs(btc_root)
    available = stats.f_bavail * stats.f_frsize
    if available < (
        BTC_MINIMUM_FREE_RESERVE_BYTES + EQUITY_MAX_NEW_TICK_BUDGET_BYTES
    ):
        raise ValueError("stock sidecar would consume protected BTC free-space reserve")
    stock_root = btc_root / stock_child_name
    total = 0
    inspected = 0
    if stock_root.exists():
        if stock_root.is_symlink() or not stock_root.is_dir():
            raise ValueError("stock evidence child must be a real directory")
        for item in stock_root.rglob("*"):
            inspected += 1
            if inspected > 20_000 or item.is_symlink():
                raise ValueError("unsafe or excessive stock evidence tree")
            if item.is_file():
                total += item.stat().st_size
                if total + EQUITY_MAX_NEW_TICK_BUDGET_BYTES > EQUITY_MAX_TOTAL_BYTES:
                    raise ValueError("stock evidence cap reached; preserve BTC volume")
            elif not item.is_dir():
                raise ValueError("unexpected stock evidence inode")
    return {
        "available_bytes_before_stock": available,
        "existing_stock_evidence_bytes": total,
    }


def combined_multimarket_once(
    *,
    now: datetime,
    environ: Mapping[str, str] | None = None,
    btc_root: Path = CLOUD_ROOT,
    btc_crypto_runner: Callable[..., dict[str, object]] = combined_btc_first_once,
    equity_runner: Callable[..., dict[str, object]] = run_equity_sidecar_once,
    equity_provider_factory: Callable[..., object] | None = None,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware multimarket cron timestamp required")
    stamp = now.astimezone(timezone.utc)
    output: dict[str, object] = {
        "kind": "RAILWAY_EXISTING_VOLUME_MULTIMARKET_GET_ONLY_CRON",
        "crypto_btc_status": "NOT_RUN",
        "equity_status": "NOT_RUN",
        "new_Railway_service_created": False,
        "new_Railway_volume_created": False,
        "broker_order_submission": "DISABLED",
        "paper_order_submission": "DISABLED",
        "live_order_submission": "DISABLED",
        "automatic_live_trading": "DISABLED",
        "live_trading": "UNAVAILABLE",
    }

    crypto = btc_crypto_runner(
        now=stamp,
        environ=env,
        btc_root=btc_root,
    )
    if not isinstance(crypto, dict) or not isinstance(
        crypto.get("btc_status"), str
    ):
        raise ValueError("BTC/crypto combined cron returned malformed result")
    output["crypto_btc"] = crypto
    output["crypto_btc_status"] = crypto["btc_status"]

    if crypto["btc_status"] not in BTC_HEALTHY:
        output["equity_status"] = "SKIPPED_BTC_NOT_HEALTHY"
        return output
    if (
        crypto.get("btc_evidence_changed_during_sidecar_stage") is True
        or crypto.get("sidecar_status") == "FAILED_BTC_EVIDENCE_MUTATION_GUARD"
    ):
        output["equity_status"] = "SKIPPED_BTC_INTEGRITY_NOT_PROVEN"
        return output

    before = fingerprint_btc_evidence_tree(
        btc_root,
        excluded_sidecar_names=BTC_FINGERPRINT_EXCLUDED_CHILDREN,
    )
    output["btc_evidence_before_equity_SHA256"] = before["tree_sha256"]

    stock_child_name = BTC_FINGERPRINT_EXCLUDED_CHILDREN[1]
    budget = _stock_storage_budget(
        btc_root=btc_root,
        stock_child_name=stock_child_name,
    )
    output.update(budget)

    stock_env = dict(env)
    stock_env.setdefault(EQUITY_ROOT_ENV, str(btc_root))
    kwargs = {
        "env": stock_env,
        "now": stamp,
    }
    if equity_provider_factory is not None:
        kwargs["provider_factory"] = equity_provider_factory
    equity = equity_runner(**kwargs)
    if not isinstance(equity, dict) or not isinstance(
        equity.get("status"), str
    ):
        raise ValueError("equity sidecar returned malformed result")
    output["equity"] = equity
    output["equity_status"] = equity["status"]

    after = fingerprint_btc_evidence_tree(
        btc_root,
        excluded_sidecar_names=BTC_FINGERPRINT_EXCLUDED_CHILDREN,
    )
    output["btc_evidence_after_equity_SHA256"] = after["tree_sha256"]
    changed = after["tree_sha256"] != before["tree_sha256"]
    output["btc_evidence_changed_during_equity_stage"] = changed
    if changed:
        output["equity_status"] = "FAILED_BTC_EVIDENCE_MUTATION_GUARD"
        output["equity_failure_class"] = "BtcEvidenceFingerprintMismatch"
        output["original_BTC_status_preserved"] = False
        output["existing_BTC_evidence_deleted_or_reset"] = None
    else:
        output["original_BTC_status_preserved"] = True
        output["existing_BTC_evidence_deleted_or_reset"] = False
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Existing-volume BTC + crypto + stocks GET-only research cron"
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args(argv)
    result = combined_multimarket_once(
        now=datetime.now(timezone.utc)
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["crypto_btc_status"] in BTC_HEALTHY else 2


if __name__ == "__main__":
    raise SystemExit(main())
