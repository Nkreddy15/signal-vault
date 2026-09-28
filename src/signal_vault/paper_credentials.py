"""Separate Alpaca PAPER credential boundary; never load generic/live key names.

Do not paste keys into chat, commit them, log them, or attach them to reports.
This object has a redacted repr and knows only environment-provided sandbox
credentials. There is no ability to select a live host with these values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, repr=False)
class PaperCredentials:
    key_id: str
    secret_key: str

    def __post_init__(self) -> None:
        for value in (self.key_id, self.secret_key):
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise ValueError("separate PAPER key and secret are both required")
            if any(character in value for character in "\r\n\x00"):
                raise ValueError("paper credential contains forbidden control characters")

    def __repr__(self) -> str:
        return "PaperCredentials(key_id=<redacted>, secret_key=<redacted>)"

    __str__ = __repr__

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> "PaperCredentials":
        source = os.environ if values is None else values
        forbidden = (
            "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "APCA_API_KEY_ID",
            "APCA_API_SECRET_KEY", "ALPACA_LIVE_KEY_ID", "ALPACA_LIVE_SECRET_KEY",
            "ALPACA_LIVE_SECRET", "SIGNAL_VAULT_LIVE_KEY",
        )
        if any(isinstance(source.get(key), str) and source.get(key, "").strip() for key in forbidden):
            raise ValueError("generic/live Alpaca credential variables forbidden in paper-only runtime")
        return cls(source.get("SV_ALPACA_PAPER_KEY", ""),
                   source.get("SV_ALPACA_PAPER_SECRET", ""))
