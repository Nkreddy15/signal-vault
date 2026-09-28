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
from .alpaca_paper import PaperAlpacaReadClient
from .health import build_health_snapshot, write_health_snapshot
from .market_data import AlpacaAuthenticatedCryptoBars, AlpacaAuthenticatedLatestQuote
from .paper_credentials import PaperCredentials
from .paper_executor import PaperOnceExecutor
from .paper_runtime import PaperCycleRunner, PaperCycleResult
from .paper_schedule import next_delay_seconds
from .paper_store import PersistentPaperOrderStore
from .paper_worker import paper_submission_authorized, _db_path
from .runtime_lock import RuntimeFileLock


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
             clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
             sleeper: Callable[[float], None] = time.sleep,
             max_cycles: int | None = None) -> list[PaperCycleResult]:
    """Run cycles until stopped. ``max_cycles`` exists only for deterministic tests."""
    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be positive")
    results: list[PaperCycleResult] = []
    while not stop.requested:
        now = clock()
        try:
            result = runner.run_once(now=now, allow_paper_submission=allow_submission)
        except Exception as exc:
            result = PaperCycleResult(
                "BLOCKED_RUNTIME_EXCEPTION",
                f"unexpected paper runtime failure: {type(exc).__name__}",
            )
            stop.requested = True
        logical = store.logical_account()
        halted, _ = store.operator_halt()
        write_health_snapshot(
            health_path,
            build_health_snapshot(result=result, logical=logical,
                                  operator_halted=halted, at=now),
        )
        if alert_sink is not None:
            alert_sink.record_if_needed(result, at=now)
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
    lock_path = _safe_path_from_env("SIGNAL_VAULT_RUNTIME_LOCK", _derived_path(db, ".lock"))
    health_path = _safe_path_from_env("SIGNAL_VAULT_HEALTH_FILE", _derived_path(db, ".health.json"))
    alert_path = _safe_path_from_env("SIGNAL_VAULT_ALERT_FILE", _derived_path(db, ".alerts.jsonl"))
    stop = StopFlag()

    def request_stop(signum, frame) -> None:  # pragma: no cover - OS delivery is integration behavior
        del signum, frame
        stop.requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    with RuntimeFileLock(lock_path), PersistentPaperOrderStore(db) as store:
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
        )
        results = run_loop(runner=runner, store=store, allow_submission=allow_submission,
                           health_path=health_path, stop=stop, alert_sink=JsonlAlertSink(alert_path))

    last = results[-1] if results else None
    print(json.dumps({
        "mode": "ALPACA_PAPER_ONLY",
        "daemon_stopped": True,
        "last_state": last.state if last else None,
        "paper_submission_enabled": allow_submission,
    }, sort_keys=True))
    return 2 if last is not None and last.state == "BLOCKED_RUNTIME_EXCEPTION" else 0


if __name__ == "__main__":
    raise SystemExit(main())
