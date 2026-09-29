"""Explicit, bounded PAPER-account GET-only Phase 3 preflight.

This is NOT a trading worker and cannot place, cancel or fund an order.
It first verifies an existing, private local paper ledger offline. Only an
explicit invocation then retrieves the owner's existing macOS PAPER-data
Keychain items and issues fixed-path Alpaca PAPER account GET reads using the
read-only client (account, BTC asset rules, positions, open orders). No account
identifiers, provider payloads, credentials or exception messages are printed.
The installed hourly data LaunchAgent NEVER invokes this module.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from .alpaca_paper import PaperAlpacaReadClient
from .preflight import inspect_paper_runtime

# Reasons are emitted ONLY by the existing read-only client, not taken from an
# untrusted provider payload and never printed unfiltered.
_REASON_CODES = {
    "paper account not active": "PAPER_ACCOUNT_NOT_ACTIVE",
    "paper account trading status not confirmed unblocked": "TRADING_STATUS_NOT_CONFIRMED_UNBLOCKED",
    "account has pre-existing positions; cannot assume empty test portfolio":
        "EXISTING_PROVIDER_POSITIONS_NEED_REVIEW",
    "account has existing open orders; cannot assume empty test portfolio":
        "EXISTING_PROVIDER_OPEN_ORDERS_NEED_REVIEW",
    "invalid non-marginable buying power": "INVALID_BUYING_POWER",
}


def inspect_account_get_only(
    *,
    db: str | Path = "data/signal-vault-paper.sqlite3",
    local_inspector: Callable[..., object] = inspect_paper_runtime,
    credential_loader: Callable[[], object] | None = None,
    client_factory: Callable[..., object] = PaperAlpacaReadClient,
) -> dict[str, object]:
    """One explicitly triggered read-only check, with injectable offline fakes.

    A missing/bad/unclean local paper ledger BLOCKS before Keychain access.
    A pass verifies basic paper account state, NOT affordability of a specific
    future order, live execution, profitability or consent to submit.
    """
    report: dict[str, object] = {
        "kind": "PHASE3_PAPER_ACCOUNT_READ_ONLY_PREFLIGHT",
        "status": "BLOCKED",
        "reason_codes": [],
        "error_class": None,
        "local_ledger_checked": False,
        "paper_account_get_attempted": False,
        "credential_source": "OWNER_KEYCHAIN_IF_LOCAL_PREFLIGHT_PASSES",
        "credentials_logged": False,
        "broker_order_submission": "DISABLED",
        "automatic_paper_trading": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "warning": (
            "This check never places/cancels orders. Provider/account readiness "
            "is NOT order authorization, fill evidence or a strategy promotion."
        ),
    }

    try:
        local = local_inspector(db)
    except Exception as exc:
        report["reason_codes"] = ["LOCAL_PAPER_LEDGER_MISSING_OR_INVALID"]
        report["error_class"] = type(exc).__name__
        return report

    if not isinstance(local, dict):
        report["reason_codes"] = ["INVALID_LOCAL_PREFLIGHT_RESULT"]
        return report
    report["local_ledger_checked"] = True
    if (local.get("status") != "READ_ONLY_PREFLIGHT_OK"
            or local.get("mode") != "ALPACA_PAPER_ONLY"
            or local.get("paper_order_post_enabled") is not False
            or local.get("live_trading_available") is not False
            or local.get("authenticated_provider_read_performed") is not False
            or local.get("sqlite_wal") is not True):
        report["reason_codes"] = ["INVALID_OR_UNSAFE_LOCAL_PAPER_PREFLIGHT"]
        return report
    if local.get("operator_halted") is not False:
        report["reason_codes"] = ["LOCAL_OPERATOR_HALTED_OR_UNKNOWN"]
        return report
    pending = local.get("unresolved_paper_orders")
    if (type(pending) is not int or pending != 0
            or local.get("provider_lookup_required") is not False):
        report["reason_codes"] = ["LOCAL_ORDER_RECONCILIATION_REQUIRED"]
        return report

    if credential_loader is None:
        # Only this explicitly invoked command loads keys, NEVER module import,
        # unattended observation scheduling, phase3_readiness or tests.
        from .unattended_forward_cycle import load_keychain_paper_data_credentials
        credential_loader = load_keychain_paper_data_credentials
    try:
        credentials = credential_loader()
        key, secret = credentials.key_id, credentials.secret_key
        if not isinstance(key, str) or not isinstance(secret, str) or not key or not secret:
            raise ValueError("invalid credentials")
    except Exception as exc:
        report["reason_codes"] = ["PAPER_KEYCHAIN_ACCESS_BLOCKED"]
        report["error_class"] = type(exc).__name__
        return report

    try:
        # The production factory is fixed-path Alpaca PAPER GET-only. Never
        # import paper_executor, paper_worker, POST transport, or live host here.
        client = client_factory(key, secret)
        report["paper_account_get_attempted"] = True
        checked = client.readiness()
    except Exception as exc:
        report["reason_codes"] = ["PAPER_READ_ONLY_PROVIDER_PREFLIGHT_FAILED"]
        report["error_class"] = type(exc).__name__
        return report

    ready = getattr(checked, "ready", None)
    reasons = getattr(checked, "reasons", None)
    logical_cap = getattr(checked, "logical_cap_usd", None)
    # No provider response/identifier, hidden credential or unexpected reason
    # ever leaves via stdout. This tool is diagnostic, not a promotion gate.
    if (type(ready) is not bool or not isinstance(reasons, tuple)
            or str(logical_cap) != "100"):
        report["reason_codes"] = ["INVALID_READINESS_CONTRACT"]
        return report
    if not ready or reasons:
        codes = {_REASON_CODES.get(reason, "UNRECOGNIZED_PROVIDER_STATE")
                 if isinstance(reason, str) else "UNRECOGNIZED_PROVIDER_STATE"
                 for reason in reasons}
        report["reason_codes"] = sorted(codes) or ["PROVIDER_READINESS_NOT_CONFIRMED"]
        report["status"] = "PAPER_ACCOUNT_REQUIRES_REVIEW"
        return report
    report["status"] = "BASIC_PAPER_ACCOUNT_GET_CHECK_PASSED"
    report["reason_codes"] = []
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicit GET-only Alpaca PAPER account preflight; NEVER submits orders.")
    parser.add_argument("--db", default="data/signal-vault-paper.sqlite3")
    args = parser.parse_args(argv)
    result = inspect_account_get_only(db=args.db)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "BASIC_PAPER_ACCOUNT_GET_CHECK_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
