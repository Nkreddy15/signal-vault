"""Phase 3 OFFLINE, read-only progress/readiness inspection.

This operator command is intentionally not an order preflight certificate:
it never loads Keychain/environment secrets, asks Alpaca for account/market data,
imports the POST executor, creates a journal, or authorizes paper/live trading.
The observer and paper ledger are independent. Report only safe status enums
and counts, never raw receipt/event JSON or exception messages.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Mapping


def _collector_summary(raw: object, failure: str | None) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "UNAVAILABLE",
        "prospective_observations_verified": 0,
        "latest_tick_decision": "NONE",
        "error_class": failure,
    }
    if failure:
        return result
    if not isinstance(raw, Mapping):
        result["status"] = "INVALID_STATUS"
        return result
    if (raw.get("kind") != "UNATTENDED_FORWARD_LOCAL_STATUS"
            or raw.get("broker_order_submission") != "DISABLED"):
        result["status"] = "INVALID_STATUS"
        return result
    tick = raw.get("latest_tick")
    decision = tick.get("decision") if isinstance(tick, Mapping) else None
    # Only fixed, nonsecret status categories leave this module.
    choices = {
        "FIRST_AUTO_SEGMENT_BOOTSTRAPPED",
        "NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR",
        "ONE_NEW_PROSPECTIVE_CANDLE_RECORDED",
        "ALREADY_PROCESSED_OR_NEXT_HOUR_NOT_CLOSED",
        "SKIP_OUTSIDE_SAFE_UTC_MINUTE_03_TO_24",
        "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE",
    }
    result["latest_tick_decision"] = (decision if isinstance(decision, str) and decision in choices
                                      else "NONE_OR_UNRECOGNIZED")
    if decision == "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE":
        result["status"] = "HALTED_REQUIRES_OPERATOR_REVIEW"
        return result
    state = raw.get("state")
    if state in ("NOT_INITIALIZED", "NO_AUTO_SEGMENT_STARTED"):
        result["status"] = "AWAITING_FIRST_SCHEDULED_TICK"
        return result
    count = raw.get("prospective_observations_verified")
    if (state != "ARCHIVED_INTERNAL_EVIDENCE_VERIFIED" or type(count) is not int or count < 0
            or raw.get("network_requests") != "NONE"):
        result["status"] = "INVALID_STATUS"
        return result
    result["prospective_observations_verified"] = count
    if count == 0 and decision in (
            "FIRST_AUTO_SEGMENT_BOOTSTRAPPED", "NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR"):
        result["status"] = "BOOTSTRAP_ONLY_NEXT_CONSECUTIVE_TICK_REQUIRED"
    elif count >= 1 and decision == "ONE_NEW_PROSPECTIVE_CANDLE_RECORDED":
        result["status"] = "VERIFIED_FORWARD_OBSERVATION_PRESENT"
    else:
        result["status"] = "ARCHIVE_PRESENT_INSPECT_LATEST_TICK"
    return result


def _ledger_summary(raw: object, failure: str | None, *, missing: bool) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "NOT_INITIALIZED" if missing else "UNAVAILABLE",
        "unresolved_paper_orders": None,
        "operator_halted": None,
        "error_class": failure,
    }
    if missing or failure:
        return result
    if not isinstance(raw, Mapping):
        result["status"] = "INVALID_STATUS"
        return result
    unresolved = raw.get("unresolved_paper_orders")
    if not (raw.get("status") == "READ_ONLY_PREFLIGHT_OK"
            and raw.get("mode") == "ALPACA_PAPER_ONLY"
            and raw.get("paper_order_post_enabled") is False
            and raw.get("authenticated_provider_read_performed") is False
            and raw.get("live_trading_available") is False
            and raw.get("sqlite_wal") is True
            and type(unresolved) is int and unresolved >= 0
            and type(raw.get("operator_halted")) is bool
            and type(raw.get("provider_lookup_required")) is bool):
        result["status"] = "INVALID_OR_UNSAFE_PREFLIGHT"
        return result
    result["unresolved_paper_orders"] = unresolved
    result["operator_halted"] = raw["operator_halted"]
    if raw["operator_halted"]:
        result["status"] = "OPERATOR_HALTED"
    elif unresolved or raw["provider_lookup_required"]:
        result["status"] = "UNRESOLVED_ORDER_REQUIRES_PROVIDER_RECONCILIATION"
    else:
        result["status"] = "CLEAN_LOCAL_LEDGER_NOT_PROVIDER_ATTESTED"
    return result


def assess_offline_readiness(
    *,
    forward_root: str | Path = "data/forward",
    paper_db: str | Path = "data/signal-vault-paper.sqlite3",
    collector_reader: Callable[..., object] | None = None,
    paper_reader: Callable[..., object] | None = None,
) -> dict[str, object]:
    """Observe existing local state only. Inject readers for isolated fake tests."""
    if collector_reader is None:
        from .unattended_forward_cycle import status_unattended
        collector_reader = status_unattended
    if paper_reader is None:
        from .preflight import inspect_paper_runtime
        paper_reader = inspect_paper_runtime

    root, db = Path(forward_root).expanduser(), Path(paper_db).expanduser()
    try:
        collector_raw = collector_reader(root=root)
        collector_failure = None
    except Exception as exc:
        collector_raw, collector_failure = None, type(exc).__name__
    collector = _collector_summary(collector_raw, collector_failure)

    missing_db = not (db.exists() or db.is_symlink())
    paper_raw, paper_failure = None, None
    if not missing_db:
        try:
            paper_raw = paper_reader(db)
        except Exception as exc:
            paper_failure = type(exc).__name__
    ledger = _ledger_summary(paper_raw, paper_failure, missing=missing_db)

    blockers: list[str] = []
    if collector["status"] != "VERIFIED_FORWARD_OBSERVATION_PRESENT":
        blockers.append("COLLECTOR_FORWARD_ACCEPTANCE_NOT_YET_CONFIRMED")
    if ledger["status"] != "CLEAN_LOCAL_LEDGER_NOT_PROVIDER_ATTESTED":
        blockers.append("PAPER_LOCAL_LEDGER_NOT_CLEAN_OR_INITIALIZED")
    # Other commands may already have succeeded. This offline reporter cannot
    # attest the independent provider GET or the one-time supervised PAPER order.
    # NEVER claim either was not performed merely because this command is offline.
    blockers.extend((
        "SEPARATE_PAPER_ACCOUNT_GET_RESULT_NOT_TRACKED_BY_OFFLINE_REPORT",
        "SUPERVISED_PAPER_ORDER_RESULT_NOT_TRACKED_BY_OFFLINE_REPORT",
        "NO_STRATEGY_PROMOTED_V01_V02_V03",
    ))
    local_ok = len(blockers) == 3
    return {
        "kind": "PHASE3_OFFLINE_READINESS_REPORT",
        "schema_version": 1,
        "collector": collector,
        "paper_journal": ledger,
        "local_engineering_prechecks": "PASSED_NOT_TRADE_AUTHORIZATION" if local_ok else "INCOMPLETE",
        "provider_trading_account_checked": False,
        "provider_account_check_scope": "NOT_PERFORMED_IN_THIS_OFFLINE_INVOCATION",
        "separate_provider_get_receipt": "NOT_TRACKED_BY_THIS_REPORT",
        "network_requests": "NONE",
        "credentials_accessed": False,
        "paper_order_post_attempted": False,
        "broker_order_submission": "DISABLED",
        "automatic_paper_trading": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "blockers": blockers,
        "disclosure": (
            "Offline local status only: not provider attestation, a strategy promotion, "
            "a fill, a profitability claim or permission to place paper orders."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Phase 3 readiness status: NO broker network/orders/secrets/writes.")
    parser.add_argument("--forward-root", default="data/forward")
    parser.add_argument("--paper-db", default="data/signal-vault-paper.sqlite3")
    args = parser.parse_args(argv)
    report = assess_offline_readiness(
        forward_root=args.forward_root, paper_db=args.paper_db)
    print(json.dumps(report, indent=2, sort_keys=True))
    # A generated report succeeds even when its content describes blockers.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
