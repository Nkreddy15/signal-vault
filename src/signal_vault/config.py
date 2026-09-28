"""Fail-closed Phase 1 runtime configuration.

This deliberately cannot be enabled for live trading by changing a flag.
Enabling a future paper-broker adapter requires a reviewed implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import os


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    broker: str
    network_orders_enabled: bool
    symbol: str

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "RuntimeConfig":
        settings = os.environ if env is None else env
        mode = settings.get("SIGNAL_VAULT_MODE", "paper").strip().lower()
        broker = settings.get("SIGNAL_VAULT_BROKER", "local_dry_run").strip().lower()
        network = settings.get(
            "SIGNAL_VAULT_ENABLE_NETWORK_ORDER_SUBMISSION", "false"
        ).strip().lower()
        symbol = settings.get("SIGNAL_VAULT_SYMBOL", "BTC/USD").strip().upper()

        if mode != "paper":
            raise ValueError("Phase 1 is PAPER ONLY. No live runtime is implemented.")
        if broker != "local_dry_run":
            raise ValueError("Phase 1 permits only the local dry-run broker.")
        if network != "false":
            raise ValueError("Network order submission is disabled in Phase 1.")
        if symbol != "BTC/USD":
            raise ValueError("Phase 1 permits only BTC/USD for the offline demo.")
        return cls(mode=mode, broker=broker, network_orders_enabled=False, symbol=symbol)
