"""Cloud-PORTABLE GET-only hourly BTC observer + offline EMA shadow receipt.

This is a separately activated collector instance with its OWN persistent
volume/segment, not a network endpoint or a broker daemon. It reuses the
already tested exact-hour non-backfilling capture/audit implementation and
fixed, redirect-refusing Alpaca historical-DATA HTTPS GET transport.

NO cloud account is configured/deployed merely by merging this code. The
Docker command is a deployment template. No Keychain, paper account reader,
order executor, POST, model inference, arbitrary URL, order or live fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from .forward_capture import _read_data_get_no_redirect
from .market_data import AlpacaAuthenticatedCryptoBars
from .paper_credentials import PaperCredentials
from .runtime_lock import RuntimeFileLock
from .shadow_signal_snapshot import inspect_latest_shadow_signal
from .unattended_forward_cycle import (
    FORBIDDEN_ENV, run_unattended_once, status_unattended,
)

CLOUD_ROOT = Path("/var/lib/signal-vault/forward")
KEY_FILE = Path("/run/secrets/forward_data_key_id")
SECRET_FILE = Path("/run/secrets/forward_data_secret")
PAUSE_NAME = ".cloud-collector-paused.json"
SHADOW_DIR = "cloud-shadow-receipts"
FORBIDDEN_CLOUD_ENV = FORBIDDEN_ENV + (
    "ALPACA_PAPER_KEY_ID", "ALPACA_PAPER_SECRET_KEY",
    "SIGNAL_VAULT_ENABLE_PAPER_ORDERS",
)
HOUR = timedelta(hours=1)


def _utc(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("UTC-aware cloud scheduler clock required")
    return now.astimezone(timezone.utc)


def _private_volume(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("cloud evidence volume must PREEXIST as a nonsymlink directory")
    if root.stat().st_mode & 0o077:
        raise PermissionError("cloud evidence volume must be private (0700)")
    if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
        raise PermissionError("cloud evidence volume must be writable by isolated worker")
    return root


def _secret_bytes(path: Path) -> str:
    """Read a fixed-name file-mounted DATA secret; never log, expose in env/argv."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or symlinked cloud DATA secret")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o022:
        raise PermissionError("cloud DATA secret must be a non-writable regular mount")
    if not os.access(path, os.R_OK) or path.stat().st_size > 1024:
        raise ValueError("cloud DATA secret is unreadable or oversized")
    # Enforce exact values: no unexpected whitespace, newline, NUL, UTF8 replacement.
    value = path.read_bytes().decode("utf-8", errors="strict")
    if not value or value != value.strip() or len(value) > 512:
        raise ValueError("cloud DATA secret is blank, altered or malformed")
    return value


def _cloud_credentials(
    key_file: Path = KEY_FILE, secret_file: Path = SECRET_FILE,
    environ: Mapping[str, str] | None = None,
) -> PaperCredentials:
    env = os.environ if environ is None else environ
    if any(str(env.get(name, "")).strip() for name in FORBIDDEN_CLOUD_ENV):
        raise ValueError("generic/live/order-enabled environment forbidden in GET-only cloud worker")
    return PaperCredentials(_secret_bytes(key_file), _secret_bytes(secret_file))


def _historical_get_only_provider(
    key_file: Path = KEY_FILE, secret_file: Path = SECRET_FILE,
):
    credentials = _cloud_credentials(key_file, secret_file)
    return AlpacaAuthenticatedCryptoBars(
        credentials.key_id, credentials.secret_key,
        transport=_read_data_get_no_redirect,
    )


def _pause_path(root: Path) -> Path:
    return root / PAUSE_NAME


def _read_pause(root: Path) -> bool:
    path = _pause_path(root)
    if path.is_symlink():
        raise ValueError("cloud pause marker may not be a symlink")
    if not path.exists():
        return False
    if (not path.is_file() or path.stat().st_mode & 0o077
            or path.stat().st_size > 1024):
        raise ValueError("cloud pause marker is unsafe")
    contents = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(contents, dict)
            or contents.get("kind") != "CLOUD_COLLECTOR_FAIL_CLOSED_PAUSE"
            or contents.get("schema_version") != 1):
        raise ValueError("cloud pause marker is invalid")
    return True


def _pause(root: Path, *, code: str) -> None:
    # Pause is durable across container restarts so restart policies cannot
    # repeatedly attempt a failed capture or mask a corrupted evidence chain.
    marker = _pause_path(root)
    if _read_pause(root):
        return
    if not isinstance(code, str) or len(code) > 64 or not code.replace("_", "").isalnum():
        code = "UNKNOWN_FAILURE_CLASS"
    payload = json.dumps({
        "kind": "CLOUD_COLLECTOR_FAIL_CLOSED_PAUSE",
        "schema_version": 1,
        "reason_code": code,
        "operator_review_required": True,
    }, sort_keys=True).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(marker, flags, 0o600)
    with os.fdopen(fd, "wb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(payload)
        writer.flush()
        os.fsync(writer.fileno())


def _write_shadow_receipt(root: Path, report: Mapping[str, object]) -> str:
    if report.get("status") != "AUDITED_ONE_CANDLE_SHADOW_SIGNALS_RESEARCH_ONLY":
        raise ValueError("refusing to archive a nonaudited shadow decision")
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("missing SHA-bound observation identity")
    closed = _utc(datetime.fromisoformat(str(evidence["bar_closed_utc"])))
    if closed.minute or closed.second or closed.microsecond:
        raise ValueError("shadow receipt must bind one fully closed UTC hour")
    name = "shadow-" + closed.strftime("%Y%m%dT%H%MZ") + ".json"
    folder = root / SHADOW_DIR
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("cloud shadow-receipt folder is unsafe")
    folder.mkdir(mode=0o700, exist_ok=True)
    if folder.stat().st_mode & 0o077:
        raise PermissionError("cloud shadow receipt folder must be private (0700)")
    dest = folder / name
    record = {
        "kind": "CLOUD_SHA_BOUND_SHADOW_EVALUATION_NO_ORDER",
        "schema_version": 1,
        "evidence": dict(evidence),
        "prospective_observations_verified": report["prospective_observations_verified"],
        "cost_assumptions": report["research_cost_assumptions"],
        "research_decisions": report["research_decisions"],
        "strategy_promoted": False,
        "broker_order_submission": "DISABLED",
        "market_data_requests_during_shadow": "NONE",
    }
    raw = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if dest.exists() or dest.is_symlink():
        if (dest.is_symlink() or not dest.is_file() or
                dest.stat().st_mode & 0o077 or dest.stat().st_size > 32768
                or dest.read_bytes() != raw):
            raise ValueError("existing immutable shadow receipt conflicts with this close")
        return "ALREADY_ARCHIVED_IDENTICAL"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(dest, flags, 0o600)
    with os.fdopen(fd, "wb") as writer:
        os.fchmod(writer.fileno(), 0o600)
        writer.write(raw)
        writer.flush()
        os.fsync(writer.fileno())
    return "NEW_IMMUTABLE_RECEIPT_WRITTEN"


def next_due_utc(now: datetime, *, last_attempted_hour: datetime | None = None) -> datetime:
    """Schedule at HH:07Z; late startup HH:07..HH:24 runs current close only.

    Never replay a missed previous hour, and at most one attempt per UTC hour
    in a single running process. A restart has the existing journal/collision
    checks as an additional guard against duplicate observations.
    """
    stamp = _utc(now)
    hour = stamp.replace(minute=0, second=0, microsecond=0)
    slot = hour + timedelta(minutes=7)
    if last_attempted_hour is not None and _utc(last_attempted_hour) == hour:
        return slot + HOUR
    if stamp <= slot:
        return slot
    if stamp < hour + timedelta(minutes=25):
        return stamp
    return slot + HOUR


def cloud_cycle_once(
    *,
    root: str | Path = CLOUD_ROOT,
    now: datetime,
    provider_factory: Callable[[], object] = _historical_get_only_provider,
    after_capture_now: Callable[[], datetime] | None = None,
    shadow_reader: Callable[..., object] = inspect_latest_shadow_signal,
) -> dict[str, object]:
    """Exactly one time-gated GET-only capture, then existing OFFLINE shadow.

    The first tick bootstraps history, emits no retroactive strategy signal;
    following prospective ticks can append one SHA-bound no-trade shadow
    receipt. On any HALT, preserve raw files and atomically latch a durable
    pause. A new server may start an independent zero-count segment; there is
    no promotion/concatenation of the old Mac's separately stored evidence.
    """
    stamp = _utc(now)
    out: dict[str, object] = {
        "kind": "CLOUD_PORTABLE_UNATTENDED_GET_ONLY_CYCLE",
        "checked_utc": stamp.isoformat(),
        "status": "BLOCKED",
        "reason_code": "NOT_CHECKED",
        "broker_order_submission": "DISABLED",
        "automatic_paper_trading": "DISABLED",
        "live_trading": "UNAVAILABLE",
        "credential_source": "FILE_MOUNT_ONLY_AFTER_TIME_AND_EVIDENCE_PREFLIGHT",
        "shadow_broker_order_submission": "DISABLED",
        "old_mac_collector_modified": False,
    }
    try:
        base = _private_volume(Path(root).expanduser())
        if _read_pause(base):
            out.update(status="PAUSED_OPERATOR_REVIEW_REQUIRED",
                       reason_code="DURABLE_FAIL_CLOSED_PAUSE_PRESENT")
            return out
        receipt = run_unattended_once(
            root=base, now=stamp, provider_factory=provider_factory,
            after_capture_now=after_capture_now)
        decision = receipt.get("decision")
        out["collector_decision"] = decision
        if decision == "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE":
            failure = receipt.get("failure_class")
            _pause(base, code=failure if isinstance(failure, str) else "UNKNOWN")
            out.update(status="PAUSED_OPERATOR_REVIEW_REQUIRED",
                       reason_code="COLLECTION_FAILED_OR_EVIDENCE_UNSAFE",
                       failure_class=failure)
            return out
        out["reason_code"] = "NONE"
        if decision == "ONE_NEW_PROSPECTIVE_CANDLE_RECORDED":
            shadow = shadow_reader(forward_root=base)
            if not isinstance(shadow, Mapping) or shadow.get("status") != (
                    "AUDITED_ONE_CANDLE_SHADOW_SIGNALS_RESEARCH_ONLY"):
                _pause(base, code="SHADOW_AUDIT_FAILED")
                out.update(status="PAUSED_OPERATOR_REVIEW_REQUIRED",
                           reason_code="OFFLINE_SHADOW_AUDIT_FAILED")
                return out
            out["shadow_receipt"] = _write_shadow_receipt(base, shadow)
            out["shadow_signal_count"] = len(shadow["research_decisions"])
            out["observed_bar_closed_utc"] = shadow["evidence"]["bar_closed_utc"]
            out["prospective_observations_verified"] = shadow[
                "prospective_observations_verified"]
            out["status"] = "ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED"
        elif decision in ("FIRST_AUTO_SEGMENT_BOOTSTRAPPED",
                          "NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR"):
            out["status"] = "HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW"
            out["prospective_observations_verified"] = 0
        else:
            out["status"] = "SAFE_NO_NEW_OBSERVATION"
        return out
    except Exception as exc:
        # If the preexisting private volume is available, fail closed even if
        # a shadow file write or its journal validation encountered a problem.
        try:
            base = _private_volume(Path(root).expanduser())
            _pause(base, code=type(exc).__name__)
        except Exception:
            pass
        out.update(status="PAUSED_OPERATOR_REVIEW_REQUIRED",
                   reason_code="CLOUD_CYCLE_OR_STORAGE_FAILED_CLOSED",
                   failure_class=type(exc).__name__)
        return out


def cloud_preflight(
    *, root: str | Path = CLOUD_ROOT,
    credential_loader: Callable[[], object] = _cloud_credentials,
) -> dict[str, object]:
    """Explicit no-network review, never prints or persists a secret."""
    out = {
        "kind": "CLOUD_GET_ONLY_PREDEPLOYMENT_PREFLIGHT",
        "status": "BLOCKED",
        "broker_order_submission": "DISABLED",
        "network_requests": "NONE",
        "no_credentials_in_output": True,
        "cloud_service_activated": False,
    }
    try:
        base = _private_volume(Path(root).expanduser())
        if _read_pause(base):
            out["reason_code"] = "DURABLE_COLLECTOR_PAUSE_PRESENT"
            return out
        creds = credential_loader()
        if not isinstance(creds, PaperCredentials):
            raise ValueError("invalid file-only DATA credential pair")
        out.update(status="LOCAL_CLOUD_PREFLIGHT_PASSED_NO_DEPLOYMENT",
                   reason_code="NONE", secret_files_readable=True)
    except Exception as exc:
        out.update(reason_code="CLOUD_VOLUME_OR_DATA_SECRET_PRECHECK_FAILED",
                   failure_class=type(exc).__name__)
    return out


def cloud_status(*, root: str | Path = CLOUD_ROOT) -> dict[str, object]:
    out: dict[str, object] = {
        "kind": "CLOUD_OFFLINE_GET_ONLY_STATUS",
        "status": "BLOCKED",
        "broker_order_submission": "DISABLED",
        "network_requests": "NONE",
        "credential_access": "NONE",
        "live_trading": "UNAVAILABLE",
    }
    try:
        base = _private_volume(Path(root).expanduser())
        out["durably_paused"] = _read_pause(base)
        archived = status_unattended(root=base)
        out["verified_collector"] = archived
        out["status"] = "PAUSED" if out["durably_paused"] else "READ_ONLY_STATUS_AVAILABLE"
    except Exception as exc:
        out["reason_code"] = "CLOUD_EVIDENCE_STATUS_FAILED"
        out["failure_class"] = type(exc).__name__
    return out


def _serve() -> int:
    """Long-lived UTC scheduler only if an operator EXPLICITLY deploys it.

    STOP on a persisted HALT; never automatically clear evidence or retry
    after corruption/network ambiguity. Sleep safely until the host stops it.
    """
    last: datetime | None = None
    # Never let RuntimeFileLock mkdir an absent or mispermissioned volume:
    # the persistent, owner-private mount must already exist.
    base = _private_volume(CLOUD_ROOT)
    with RuntimeFileLock(base / ".cloud_service.lock"):
        while True:
            try:
                paused = _read_pause(base)
            except Exception:
                paused = True  # malformed pause marker also forbids further GET
            if paused:
                print(json.dumps({
                    "status": "PAUSED_OPERATOR_REVIEW_REQUIRED",
                    "broker_order_submission": "DISABLED",
                    "note": "Preserve evidence and inspect cloud_status; no automatic retry."
                }), flush=True)
                # Keep the container stable across host/engine restarts.
                while True:
                    time.sleep(3600)
            now = datetime.now(timezone.utc)
            due = next_due_utc(now, last_attempted_hour=last)
            time.sleep(max(0, (due - now).total_seconds()))
            at = datetime.now(timezone.utc)
            last = at.replace(minute=0, second=0, microsecond=0)
            result = cloud_cycle_once(now=at)
            print(json.dumps(result, sort_keys=True), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Separately deployed CLOUD-READY historical-DATA GET + offline shadow; NO orders.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--once", action="store_true",
                       help="One actual UTC time-gated DATA GET on an explicitly provisioned cloud instance.")
    modes.add_argument("--serve", action="store_true",
                       help="UTC HH:07 scheduler; requires explicit deployment and durable isolated volume.")
    modes.add_argument("--status", action="store_true",
                       help="Strictly offline archived cloud status; no secrets or provider request.")
    modes.add_argument("--preflight", action="store_true",
                       help="Inspect existing private volume + mounted DATA secrets; NO network/deployment.")
    args = parser.parse_args(argv)
    if args.serve:
        return _serve()
    if args.status:
        result = cloud_status()
        code = 0 if result["status"] in ("PAUSED", "READ_ONLY_STATUS_AVAILABLE") else 2
    elif args.preflight:
        result = cloud_preflight()
        code = 0 if result["status"] == "LOCAL_CLOUD_PREFLIGHT_PASSED_NO_DEPLOYMENT" else 2
    else:
        result = cloud_cycle_once(now=datetime.now(timezone.utc))
        code = 0 if result["status"] in (
            "ONE_PROSPECTIVE_OBSERVATION_AND_SHADOW_ARCHIVED",
            "HISTORY_BOOTSTRAPPED_NO_RETROSPECTIVE_SHADOW",
            "SAFE_NO_NEW_OBSERVATION") else 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
