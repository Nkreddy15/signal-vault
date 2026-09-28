"""Unattended ALPACA PAPER-only scheduler.

This is the long-running runtime shell. It has no live endpoint and inherits the
same exact paper-order acknowledgement gate as ``paper_worker``. A filesystem
leadership lock prevents two daemons from operating the same SQLite journal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import json
import os
import signal
import time

from .alerts import JsonlAlertSink
from .backup import DailyBackupManager
from .alpaca_paper import PaperAlpacaReadClient
from .health import build_health_snapshot, write_health_snapshot
from .market_data import AlpacaAuthenticatedCryptoBars, AlpacaAuthenticatedLatestQuote
from .ml_policy import load_promoted_paper_artifact
from .paper_credentials import PaperCredentials
from .paper_executor import PaperOnceExecutor
from .paper_runtime import PaperCycleRunner, PaperCycleResult
from .paper_schedule import next_delay_seconds
from .paper_store import PersistentPaperOrderStore
from .preflight import check_sqlite_runtime
from .reporting import build_performance_report, write_report
from .paper_worker import paper_submission_authorized, _db_path, _ml_artifact_from_env
from .runtime_lock import RuntimeFileLock
from .safe_log import emit_cycle_log


@dataclass
class StopFlag:
    requested: bool = False


def _derived_path(db: Path, suffix: str) -> Path:
    return db.with_name(db.name + suffix)


def _safe_path_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    if "\x00" in raw:
        raise ValueError(f"invalid {name} path")
    return Path(raw).expanduser()


def run_loop(*, runner: PaperCycleRunner, store: PersistentPaperOrderStore,
             allow_submission: bool, health_path: Path, stop: StopFlag,
             alert_sink: JsonlAlertSink | None = None,
             log_cycle: Callable[..., None] | None = emit_cycle_log,
             backup_hook: Callable[[datetime], object] | None = None,
             report_hook: Callable[[datetime], object] | None = None,
             clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
             sleeper: Callable[[float], None] = time.sleep,
             max_cycles: int | None = None) -> list[PaperCycleResult]:
    """Run cycles until stopped. ``max_cycles`` exists only for deterministic tests."""
    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be positive")
    results: list[PaperCycleResult] = []
    while not stop.requested:
        now = clock()
        if backup_hook is not None:
            try:
                backup_hook(now)
            except Exception as exc:
                result = PaperCycleResult(
                    "BLOCKED_BACKUP_FAILURE",
                    f"paper ledger backup failed: {type(exc).__name__}",
                )
                stop.requested = True
            else:
                result = None
        else:
            result = None
        if result is None:
            try:
                result = runner.run_once(now=now, allow_paper_submission=allow_submission)
            except Exception as exc:
                result = PaperCycleResult(
                    "BLOCKED_RUNTIME_EXCEPTION",
                    f"unexpected paper runtime failure: {type(exc).__name__}",
                )
                stop.requested = True
        if report_hook is not None and not result.state.startswith("BLOCKED_BACKUP"):
            try:
                report_hook(now)
            except Exception as exc:
                result = PaperCycleResult(
                    "BLOCKED_REPORTING_FAILURE",
                    f"paper reporting failed: {type(exc).__name__}",
                    client_order_id=result.client_order_id,
                    provider_stage=result.provider_stage,
                    paper_post_attempted=result.paper_post_attempted,
                )
                stop.requested = True
        logical = store.logical_account()
        halted, _ = store.operator_halt()
        write_health_snapshot(
            health_path,
            build_health_snapshot(result=result, logical=logical,
                                  operator_halted=halted, at=now, last_mark=store.last_mark()),
        )
        if alert_sink is not None:
            alert_sink.record_if_needed(result, at=now)
        if log_cycle is not None:
            log_cycle(result=result, logical=logical, operator_halted=halted, at=now)
        results.append(result)
        if max_cycles is not None and len(results) >= max_cycles:
            break
        if stop.requested:
            break
        sleeper(next_delay_seconds(result, now=now))
    return results


def main() -> int:
    env = os.environ
    credentials = PaperCredentials.from_environment(env)
    allow_submission = paper_submission_authorized(env)
    db = _db_path(env)
    ml_artifact = _ml_artifact_from_env(env)
    lock_path = _safe_path_from_env("SIGNAL_VAULT_RUNTIME_LOCK", _derived_path(db, ".lock"))
    health_path = _safe_path_from_env("SIGNAL_VAULT_HEALTH_FILE", _derived_path(db, ".health.json"))
    alert_path = _safe_path_from_env("SIGNAL_VAULT_ALERT_FILE", _derived_path(db, ".alerts.jsonl"))
    backup_dir = _safe_path_from_env("SIGNAL_VAULT_BACKUP_DIR", db.parent / "backups")
    report_path = _safe_path_from_env("SIGNAL_VAULT_REPORT_FILE", db.with_name(db.name + ".report.json"))
    stop = StopFlag()

    def request_stop(signum, frame) -> None:  # pragma: no cover - OS delivery is integration behavior
        del signum, frame
        stop.requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    with RuntimeFileLock(lock_path), PersistentPaperOrderStore(db) as store:
        check_sqlite_runtime(db)
        reader = PaperAlpacaReadClient(credentials.key_id, credentials.secret_key)
        executor = PaperOnceExecutor(paper_key=credentials.key_id,
                                     paper_secret=credentials.secret_key,
                                     store=store)
        runner = PaperCycleRunner(
            store=store,
            reader=reader,
            executor=executor,
            bars=AlpacaAuthenticatedCryptoBars(credentials.key_id, credentials.secret_key),
            quotes=AlpacaAuthenticatedLatestQuote(credentials.key_id, credentials.secret_key),
            confirmation_artifact=ml_artifact,
        )
        backup_manager = DailyBackupManager(db, backup_dir)
        results = run_loop(runner=runner, store=store, allow_submission=allow_submission,
                           health_path=health_path, stop=stop, alert_sink=JsonlAlertSink(alert_path),
                           backup_hook=lambda when: backup_manager.maybe_backup(at=when),
                           report_hook=lambda when: write_report(report_path, build_performance_report(store, at=when)))

    last = results[-1] if results else None
    print(json.dumps({
        "mode": "ALPACA_PAPER_ONLY",
        "daemon_stopped": True,
        "last_state": last.state if last else None,
        "paper_submission_enabled": allow_submission,
    }, sort_keys=True))
    return 2 if last is not None and last.state in {"BLOCKED_RUNTIME_EXCEPTION", "BLOCKED_BACKUP_FAILURE", "BLOCKED_REPORTING_FAILURE"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
