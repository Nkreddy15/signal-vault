"""Bounded retry policy for idempotent READ operations only.

Never use this helper for order POSTs. A submission timeout is ambiguous and is
handled by the order state machine as UNKNOWN_RESULT instead of being retried.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar
from urllib.error import HTTPError, URLError
import socket
import time

T = TypeVar("T")


@dataclass(frozen=True)
class ReadRetryPolicy:
    attempts: int = 3
    initial_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.attempts > 5:
            raise ValueError("read retry attempts outside reviewed bounds")
        if not (0 <= self.initial_delay_seconds <= self.max_delay_seconds <= 5):
            raise ValueError("read retry delay outside reviewed bounds")


def is_retryable_read_error(exc: BaseException) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code == 429 or 500 <= exc.code <= 599
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, URLError):
        return True
    return False


def retry_read(operation: Callable[[], T], *, policy: ReadRetryPolicy | None = None,
               sleeper: Callable[[float], None] = time.sleep) -> T:
    """Retry only transient idempotent-read transport errors with bounded backoff."""
    cfg = policy or ReadRetryPolicy()
    for attempt in range(cfg.attempts):
        try:
            return operation()
        except BaseException as exc:
            if not is_retryable_read_error(exc) or attempt + 1 >= cfg.attempts:
                raise
            delay = min(cfg.max_delay_seconds,
                        cfg.initial_delay_seconds * (2 ** attempt))
            sleeper(delay)
    raise AssertionError("unreachable retry loop")
