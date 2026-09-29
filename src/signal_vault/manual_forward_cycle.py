"""One operator-invoked GET-only BTC/USD forward capture + observation.

This is NOT a scheduler, strategy, shadow order worker or broker integration.
It deliberately refuses the wrong UTC hour BEFORE asking for paper DATA keys,
then retains captured CSV/manifest evidence even if journaling subsequently fails.
The existing bootstrap is never modified or recreated.
"""
from __future__ import annotations

import getpass
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .forward_capture import (
    _read_data_get_no_redirect, capture_current_window, default_capture_path,
)
from .forward_observer import ForwardObservationJournal, read_verified_capture
from .market_data import AlpacaAuthenticatedCryptoBars, utc_timestamp
from .paper_credentials import PaperCredentials
from .runtime_lock import RuntimeFileLock

DEFAULT_FORWARD_ROOT = Path("data/forward")
MIN_START_MINUTE = 3
LAST_START_MINUTE_EXCLUSIVE = 25


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("manual cycle clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _safe_root(root: str | Path) -> Path:
    """Never follow a symlinked operator data root/capture folder."""
    base = Path(root).expanduser()
    if base.is_symlink() or (base.exists() and not base.is_dir()):
        raise ValueError("forward data root must be a real directory, not a symlink")
    capture_dir = base / "captures"
    if capture_dir.is_symlink() or (capture_dir.exists() and not capture_dir.is_dir()):
        raise ValueError("forward capture directory must be real, not a symlink")
    return base


def plan_manual_observation(*, root: str | Path = DEFAULT_FORWARD_ROOT,
                            now: datetime) -> dict[str, str]:
    """Fail fast without network/credentials: only the EXACT next closed hour.

    The anchored START at the last recorded hour precedes its close by 1h;
    the next new hourly bar closes exactly 2h after that anchored start.
    """
    base = _safe_root(root)
    moment = _utc(now)
    if moment.minute < MIN_START_MINUTE or moment.minute >= LAST_START_MINUTE_EXCLUSIVE:
        raise ValueError("run manual cycle between UTC minute 03 and 24 to leave verification time")
    with ForwardObservationJournal(base / "observations.sqlite3") as journal:
        snapshot = journal.status()
    latest = utc_timestamp(snapshot["latest_anchored_bar_start_utc"])
    expected_next_close = latest + timedelta(hours=2)
    actual_closed_hour = moment.replace(minute=0, second=0, microsecond=0)
    if actual_closed_hour < expected_next_close:
        raise ValueError(
            "next new candle has not closed yet: wait for " +
            expected_next_close.isoformat() + " plus three minutes"
        )
    if actual_closed_hour > expected_next_close:
        raise ValueError(
            "forward hour missed; no historical catch-up allowed. Preserve journal and "
            "use a separately reviewed new-segment bootstrap."
        )
    target = base / "captures" / default_capture_path(moment).name
    manifest = target.with_suffix(target.suffix + ".manifest.json")
    if target.is_symlink() or manifest.is_symlink() or target.exists() or manifest.exists():
        raise ValueError(
            "this UTC-hour raw capture already exists; never overwrite. "
            "If current and fresh, use the existing manual forward_observer --observe --csv path."
        )
    return {
        "expected_closed_utc": expected_next_close.isoformat(),
        "expected_candle_started_utc": latest.__add__(timedelta(hours=1)).isoformat(),
        "target_csv": str(target),
        "target_manifest": str(manifest),
        "prior_observation_count": str(snapshot["new_forward_observation_count"]),
    }


def capture_and_observe(provider, *, now: datetime,
                        root: str | Path = DEFAULT_FORWARD_ROOT,
                        after_capture_now: Callable[[], datetime] | None = None) -> dict:
    """The only API-capable object here is an injected historical DATA GET reader.

    The critical journal append is atomic. Capture files are distinct,
    irreversible local evidence; they are not deleted after a journal failure.
    The test-only clock dependency never appears in CLI options.
    """
    base = _safe_root(root)
    # Prevent another invocation of THIS manual helper racing on raw capture.
    with RuntimeFileLock(base / ".manual_forward_cycle.lock"):
        plan = plan_manual_observation(root=base, now=now)
        path = Path(plan["target_csv"])
        manifest = capture_current_window(provider, now=_utc(now), output_csv=path)
        # Use the genuine post-fetch clock (not the pre-fetch call time). If a
        # fetch takes too long or crosses the next UTC boundary, refuse append.
        completed = _utc(after_capture_now() if after_capture_now is not None
                         else datetime.now(timezone.utc))
        if completed < _utc(now):
            raise ValueError("manual cycle clock moved backwards; raw capture retained")
        try:
            bars, digest = read_verified_capture(path, observed_at=completed)
            if digest != manifest.csv_sha256:
                raise ValueError("captured CSV SHA differs from newly written manifest")
            with ForwardObservationJournal(base / "observations.sqlite3") as journal:
                outcome = journal.process(
                    bars, csv_sha256=digest, observed_at=completed, bootstrap=False)
        except Exception as exc:
            raise RuntimeError(
                "raw capture retained at " + str(path) +
                "; journal was not reset. Review the error and, only while the "
                "capture is still current/fresh, use manual --observe with this exact CSV."
            ) from exc
        if (outcome.get("outcome") != "ONE_NEW_CLOSED_BAR_RECORDED_NO_TRADE"
                or outcome.get("new_forward_observation_count")
                != int(plan["prior_observation_count"]) + 1):
            raise RuntimeError("unexpected forward journal result; inspect status without recapturing")
        return {
            "kind": "ONE_MANUAL_READ_ONLY_CAPTURE_AND_FORWARD_OBSERVATION",
            "capture_csv": str(path),
            "capture_manifest": plan["target_manifest"],
            "capture_sha256": manifest.csv_sha256,
            "capture_row_count": manifest.row_count,
            "capture_end_utc": manifest.end_utc,
            "journal": outcome,
            "paper_order_submission": "DISABLED",
            "automatic_scheduling": "DISABLED",
            "warning": "One current-hour data observation only; no trading signals, paper fills or holdout validation.",
        }


def main() -> int:
    print("Signal Vault: one manual DATA GET + new closed-hour observation. No broker orders.")
    # Preflight BEFORE asking for credentials, so an early/late/missed hour
    # cannot trigger an unnecessary authenticated network request.
    start = datetime.now(timezone.utc)
    plan = plan_manual_observation(now=start)
    print("Eligible UTC close:", plan["expected_closed_utc"])
    print("New local capture:", plan["target_csv"])
    key = getpass.getpass("Local Alpaca PAPER data key ID (hidden): ")
    secret = getpass.getpass("Local Alpaca PAPER data secret (hidden): ")
    creds = PaperCredentials(key, secret)
    provider = AlpacaAuthenticatedCryptoBars(
        creds.key_id, creds.secret_key, transport=_read_data_get_no_redirect)
    # If a human spends too long finding credentials, second preflight uses
    # the true start of API capture rather than relabelling earlier time.
    result = capture_and_observe(provider, now=datetime.now(timezone.utc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
