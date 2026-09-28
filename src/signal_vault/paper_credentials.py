"""Paper-only credential loader.

This module deliberately knows only the Alpaca PAPER credential variable names.
It has no live host, no generic broker URL and no fallback to production keys.
Credentials are never included in repr/str or persisted by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import os


@dataclass(frozen=True, repr=False)
class PaperCredentials:
    key_id: str
    secret_key: str

    def __post_init__(self) -> None:
        if not self.key_id.strip() or not self.secret_key.strip():
            raise ValueError("both separate Alpaca PAPER credentials are required")
        if len(self.key_id) > 256 or len(self.secret_key) > 512:
            raise ValueError("paper credential length is invalid")
        for value in (self.key_id, self.secret_key):
            if any(ch in value for ch in "\r\n\x00"):
                raise ValueError("paper credentials contain forbidden control characters")

    def __repr__(self) -> str:
        return "PaperCredentials(key_id=<redacted>, secret_key=<redacted>)"

    __str__ = __repr__

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "PaperCredentials":
        values = os.environ if env is None else env
        # Refuse common production/live key names if present. This catches operator
        # mistakes instead of silently accepting credentials for the wrong account.
        forbidden = (
            "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "APCA_API_KEY_ID",
            "APCA_API_SECRET_KEY", "ALPACA_LIVE_KEY_ID", "ALPACA_LIVE_SECRET_KEY",
        )
        present = [name for name in forbidden if values.get(name, "").strip()]
        if present:
            raise ValueError("production/generic Alpaca credential variables are forbidden in paper runtime")
        return cls(
            key_id=values.get("ALPACA_PAPER_KEY_ID", ""),
            secret_key=values.get("ALPACA_PAPER_SECRET_KEY", ""),
        )
