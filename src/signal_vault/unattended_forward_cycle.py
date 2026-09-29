"""User-authorized, per-hour GET-only Alpaca BTC/USD observation worker.

This is ONE short-lived run, not a persistent daemon or broker worker. A macOS
user LaunchAgent may invoke it at :07 each hour AFTER explicit local setup.
It never submits a trade, creates an account, backfills hindsight, resets the
operator's original journal, or reads live/generic account credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .forward_capture import (
    _read_data_get_no_redirect, capture_current_window, default_capture_path,
)
from .forward_evidence_audit import audit_forward_evidence
from .forward_observer import ForwardObservationJournal, read_verified_capture
from .forward_readiness import forward_readiness
from .manual_forward_cycle import _safe_root, capture_and_observe
from .market_data import AlpacaAuthenticatedCryptoBars, utc_timestamp
from .paper_credentials import PaperCredentials
from .runtime_lock import RuntimeFileLock

ROOT = Path("data/forward")
SERVICE_ID = "com.signalvault.forward.alpaca-paper-data-key-id"
SERVICE_SECRET = "com.signalvault.forward.alpaca-paper-data-secret"
ACCOUNT = "signal-vault-forward"
HOUR = timedelta(hours=1)
SEGMENT_NAME = re.compile(r"observations-auto-\d{8}T\d{4}Z\.sqlite3\Z")
STATE_KEYS = {"schema_version", "active_journal", "last_successful_close_utc",
              "segment_first_closed_utc"}
FORBIDDEN_ENV = (
    "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY", "ALPACA_LIVE_KEY_ID", "ALPACA_LIVE_SECRET_KEY",
)


def _actual_utc(clock: datetime) -> datetime:
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("automatic observation clock must be timezone-aware")
    return clock.astimezone(timezone.utc)


def _hour(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def _private_automation_dir(root: Path) -> Path:
    base = _safe_root(root)
    if not base.is_dir():
        raise ValueError("operator forward data root must already exist")
    path = base / "automation"
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("automation directory cannot be a symlink or file")
    path.mkdir(mode=0o700, exist_ok=True)
    if path.stat().st_mode & 0o077:
        raise PermissionError("automation directory must be private (0700)")
    return path


def _read_keychain_item(service: str) -> str:
    """Read the logged-in owner's Apple Keychain; secret never goes in argv/log."""
    if os.name != "posix" or not Path("/usr/bin/security").is_file():
        raise RuntimeError("macOS Keychain security executable unavailable")
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-a", ACCOUNT,
         "-s", service, "-w"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=12, check=False,
    )
    if result.returncode or not result.stdout:
        raise RuntimeError("local Keychain item missing, locked or not authorized")
    return result.stdout.removesuffix("\n").removesuffix("\r")


def load_keychain_paper_data_credentials() -> PaperCredentials:
    """No .env, argv token, plist token, unattended getpass or LIVE fallback."""
    if any(os.environ.get(item, "").strip() for item in FORBIDDEN_ENV):
        raise ValueError("generic or LIVE credential environment variables are forbidden")
    key = _read_keychain_item(SERVICE_ID)
    secret = _read_keychain_item(SERVICE_SECRET)
    return PaperCredentials(key, secret)


def _provider_from_keychain() -> AlpacaAuthenticatedCryptoBars:
    creds = load_keychain_paper_data_credentials()
    return AlpacaAuthenticatedCryptoBars(
        creds.key_id, creds.secret_key, transport=_read_data_get_no_redirect)


def _state_path(root: Path) -> Path:
    return root / "automation" / "active_segment.json"


def _load_state(root: Path) -> dict | None:
    path = _state_path(root)
    if path.is_symlink():
        raise ValueError("automatic active-segment pointer must not be a symbolic link")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_size > 4096:
        raise ValueError("automatic active-segment pointer must be a small owner-only file")
    info = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(info, dict) or set(info) != STATE_KEYS
            or type(info["schema_version"]) is not int or info["schema_version"] != 1
            or not isinstance(info["active_journal"], str)
            or not SEGMENT_NAME.fullmatch(info["active_journal"])):
        raise ValueError("automatic active-segment pointer is invalid")
    first = utc_timestamp(info["segment_first_closed_utc"])
    latest = utc_timestamp(info["last_successful_close_utc"])
    if (first > latest or first != _hour(first) or latest != _hour(latest)
            or (root/info["active_journal"]).is_symlink()
            or not (root/info["active_journal"]).is_file()):
        raise ValueError("automatic segment pointer references invalid existing evidence")
    return info


def _private_atomic_json(path: Path, record: dict) -> None:
    """The state/receipt is operational metadata, NEVER an original data capture."""
    if path.is_symlink():
        raise ValueError("will not write through a symbolic link")
    raw = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temp = tempfile.mkstemp(prefix=".pending-state-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temp, path)
        dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        Path(temp).unlink(missing_ok=True)


def _write_receipt(root: Path, report: dict) -> None:
    folder = root / "automation" / "receipts"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("automation receipt directory is unsafe")
    folder.mkdir(mode=0o700, exist_ok=True)
    if folder.stat().st_mode & 0o077:
        raise PermissionError("automation receipt directory must be private")
    # Unique receipt names; never overwrite an earlier incident/event receipt.
    for _ in range(3):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        dest = folder / (stamp + "_" + os.urandom(4).hex() + ".json")
        if dest.exists() or dest.is_symlink():
            continue
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(dest, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            os.fchmod(out.fileno(), 0o600)
            json.dump(report, out, sort_keys=True, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        return
    raise FileExistsError("could not allocate unique nonoverwriting receipt name")


def _update_state(root: Path, db: Path, closed: datetime,
                  first: datetime) -> None:
    if not SEGMENT_NAME.fullmatch(db.name) or db.parent.resolve() != root.resolve():
        raise ValueError("automatic journal must be an explicitly named local segment")
    data = {
        "schema_version": 1,
        "active_journal": db.name,
        "last_successful_close_utc": closed.isoformat(),
        "segment_first_closed_utc": first.isoformat(),
    }
    _private_atomic_json(_state_path(root), data)


def _bootstrap_fresh_segment(
    *, root: Path, now: datetime, provider_factory: Callable[[], object],
    after_capture_now: Callable[[], datetime], previous: Path | None = None,
    missed_close: datetime | None = None,
) -> dict:
    """New verified fresh 72h historical anchor; ZERO false forward observations."""
    end = _hour(now)
    db = root / ("observations-auto-" + end.strftime("%Y%m%dT%H%MZ") + ".sqlite3")
    if db.exists() or db.is_symlink():
        raise ValueError("new prospective automatic segment journal already exists")
    capture = root / "captures" / default_capture_path(now).name
    manifest = capture.with_suffix(capture.suffix + ".manifest.json")
    if (capture.exists() or manifest.exists() or capture.is_symlink()
            or manifest.is_symlink()):
        raise ValueError("current-hour raw evidence exists; never overwrite or reclassify it")
    with RuntimeFileLock(root / ".manual_forward_cycle.lock"):
        # Recheck once inside the same lock used by the manual helper.
        if (db.exists() or db.is_symlink() or capture.exists() or capture.is_symlink()
                or manifest.exists() or manifest.is_symlink()):
            raise ValueError("journal/capture destination became occupied")
        source = provider_factory()  # Keychain read only AFTER time/path preflight
        receipt = capture_current_window(source, now=now, output_csv=capture)
        finished = _actual_utc(after_capture_now())
        if finished < now:
            raise ValueError("system clock rolled backward after read-only capture")
        bars, digest = read_verified_capture(capture, observed_at=finished)
        if digest != receipt.csv_sha256:
            raise ValueError("just captured SHA mismatch; preserving raw evidence")
        with ForwardObservationJournal(db, initialize=True) as journal:
            outcome = journal.process(bars, csv_sha256=digest,
                                      observed_at=finished, bootstrap=True)
        if (outcome["outcome"] != "BOOTSTRAPPED_HISTORY_ONLY_NO_RETROSPECTIVE_SIGNALS"
                or outcome["new_forward_observation_count"] != 0):
            raise RuntimeError("new automatic segment did not have zero prospective observations")
    verification = audit_forward_evidence(root=root, db=db)
    if verification["prospective_observations_verified"] != 0:
        raise RuntimeError("new segment archive could not be verified as bootstrap only")
    _update_state(root, db, end, end)
    return {
        "decision": ("NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR"
                     if previous is not None else "FIRST_AUTO_SEGMENT_BOOTSTRAPPED"),
        "active_journal": str(db),
        "new_forward_observation_count": 0,
        "new_capture_csv": str(capture),
        "new_capture_sha256": receipt.csv_sha256,
        "new_capture_end_utc": end.isoformat(),
        "previous_segment_preserved": str(previous) if previous else None,
        "first_missed_prospective_close_utc": missed_close.isoformat() if missed_close else None,
        "no_hindsight_backfill": True,
    }


def _cycle_locked(
    *, root: Path, now: datetime, provider_factory: Callable[[], object],
    after_capture_now: Callable[[], datetime],
) -> dict:
    """Timing and full old-chain audit BEFORE requesting Keychain credentials."""
    active = _load_state(root)
    if not 3 <= now.minute < 25:
        return {"decision": "SKIP_OUTSIDE_SAFE_UTC_MINUTE_03_TO_24",
                "active_journal": active["active_journal"] if active else None,
                "reason": "LaunchAgent resumed late or woke outside the closed-hour collection window."}
    if active is None:
        return _bootstrap_fresh_segment(root=root, now=now,
                                        provider_factory=provider_factory,
                                        after_capture_now=after_capture_now)
    db = root/active["active_journal"]
    audit = audit_forward_evidence(root=root, db=db)
    latest = utc_timestamp(audit["last_anchored_bar_started_utc"])
    last_real_close = latest + HOUR
    last_saved = utc_timestamp(active["last_successful_close_utc"])
    seen_clock = utc_timestamp(audit["last_journal_recorded_utc"])
    if now < seen_clock or last_saved > last_real_close:
        raise ValueError("clock rollback or automatic pointer ahead of verified source journal")
    current_close = _hour(now)
    if current_close <= last_real_close:
        return {
            "decision": "ALREADY_PROCESSED_OR_NEXT_HOUR_NOT_CLOSED",
            "active_journal": str(db),
            "existing_prospective_observations": audit["prospective_observations_verified"],
            "verified_last_close_utc": last_real_close.isoformat(),
            "network_requests": "NONE",
        }
    expected = last_real_close + HOUR
    if current_close > expected:
        return _bootstrap_fresh_segment(
            root=root, now=now, provider_factory=provider_factory,
            after_capture_now=after_capture_now, previous=db, missed_close=expected)
    readiness = forward_readiness(root=root, db=db, now=now)
    if readiness["decision"] != "READY_FOR_ONE_EXPLICIT_READ_ONLY_MANUAL_CYCLE":
        raise ValueError("verified current-hour collector not ready: " + readiness["decision"])
    source = provider_factory()
    result = capture_and_observe(source, now=now, root=root, db_path=db,
                                 after_capture_now=after_capture_now)
    verified = audit_forward_evidence(root=root, db=db)
    if (result["journal"]["outcome"] != "ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE"
            or verified["prospective_observations_verified"] !=
            audit["prospective_observations_verified"] + 1):
        raise RuntimeError("new observational append did not pass independent archive audit")
    _update_state(root, db, current_close,
                  utc_timestamp(active["segment_first_closed_utc"]))
    return {
        "decision": "ONE_NEW_PROSPECTIVE_CANDLE_RECORDED",
        "active_journal": str(db),
        "new_forward_observation_count": verified["prospective_observations_verified"],
        "new_capture_csv": result["capture_csv"],
        "new_capture_sha256": result["capture_sha256"],
        "new_capture_end_utc": current_close.isoformat(),
        "prior_pointer_reconciled": last_saved < last_real_close,
        "no_hindsight_backfill": True,
    }


def run_unattended_once(*, root: str | Path = ROOT, now: datetime,
                        provider_factory: Callable[[], object] = _provider_from_keychain,
                        after_capture_now: Callable[[], datetime] | None = None) -> dict:
    """Single explicit schedule tick. All public receipts are credential-free.

    Caller can inject a fake provider and clocks in OFFLINE unit tests. CLI
    never exposes a backdated clock option or arbitrary provider endpoint.
    """
    stamp = _actual_utc(now)
    folder = _private_automation_dir(Path(root))
    base = folder.parent
    report: dict = {
        "kind": "UNATTENDED_GET_ONLY_FORWARD_OBSERVATION_TICK",
        "checked_utc": stamp.isoformat(),
        "market_data_request": "NONE_UNLESS_TIME_AND_EVIDENCE_PREFLIGHT_PASSES",
        "broker_order_submission": "DISABLED",
        "live_trading": "DISABLED",
        "automatic_paper_orders": "DISABLED",
        "credentials_written_to_disk_or_logs": False,
        "warning": "User-authorized macOS scheduling of GET-only prospective market observations; no trading strategy, fills or signed provider attestations.",
    }
    finished_clock = (after_capture_now if after_capture_now is not None
                      else lambda: datetime.now(timezone.utc))
    with RuntimeFileLock(folder / ".unattended_cycle.lock"):
        try:
            step = _cycle_locked(root=base, now=stamp,
                                 provider_factory=provider_factory,
                                 after_capture_now=finished_clock)
            report.update(step)
            if step["decision"] in (
                    "FIRST_AUTO_SEGMENT_BOOTSTRAPPED",
                    "NEW_AUTO_SEGMENT_AFTER_MISSED_HOUR",
                    "ONE_NEW_PROSPECTIVE_CANDLE_RECORDED"):
                report["market_data_request"] = "ALPACA_BTCUSD_HISTORICAL_DATA_GET_ONLY"
        except Exception as exc:
            # Never render exception messages, URL headers, provider payload,
            # stdout of security -w or secrets in unattended logs/receipts.
            report.update({
                "decision": "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE",
                "failure_class": type(exc).__name__,
                "manual_review_required": True,
                "note": "Check local archive integrity/current capture before trying again. No retrospective catch-up.",
            })
        _write_receipt(base, report)
    return report


def status_unattended(*, root: str | Path = ROOT) -> dict:
    base = Path(root).expanduser()
    if not base.is_dir() or base.is_symlink():
        return {"kind": "UNATTENDED_FORWARD_LOCAL_STATUS",
                "state": "NOT_INITIALIZED", "broker_order_submission": "DISABLED"}
    path = _state_path(base)
    if not path.exists() and not path.is_symlink():
        return {"kind": "UNATTENDED_FORWARD_LOCAL_STATUS",
                "state": "NO_AUTO_SEGMENT_STARTED", "broker_order_submission": "DISABLED"}
    state = _load_state(base)
    audit = audit_forward_evidence(root=base, db=base/state["active_journal"])
    return {
        "kind": "UNATTENDED_FORWARD_LOCAL_STATUS",
        "state": "ARCHIVED_INTERNAL_EVIDENCE_VERIFIED",
        "active_auto_journal": state["active_journal"],
        "segment_first_closed_utc": state["segment_first_closed_utc"],
        "prospective_observations_verified": audit["prospective_observations_verified"],
        "last_anchored_bar_started_utc": audit["last_anchored_bar_started_utc"],
        "last_journal_recorded_utc": audit["last_journal_recorded_utc"],
        "broker_order_submission": "DISABLED",
        "network_requests": "NONE",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One short-lived user-authorized GET-only forward tick; never submits paper/live orders.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="One actual time-gated read-only market DATA tick.")
    group.add_argument("--status", action="store_true", help="Offline archived auto-segment status, without credentials.")
    args = parser.parse_args()
    if args.status:
        result = status_unattended()
    else:
        result = run_unattended_once(now=datetime.now(timezone.utc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result.get("decision") == "HALT_PRESERVE_ALL_ORIGINAL_EVIDENCE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
