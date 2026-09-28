"""Explicit one-cycle Alpaca PAPER worker entry point.

This command can never select a live endpoint. By default it performs the
paper/account/data reads and may create a local durable paper draft, but does
NOT send an order. A paper POST requires an exact, paper-specific acknowledgement
in addition to separate paper credentials.

Do not put credentials in shell history. Supply them through the deployment
secret manager/environment at runtime.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .market_data import AlpacaAuthenticatedCryptoBars, AlpacaAuthenticatedLatestQuote
from .paper_credentials import PaperCredentials
from .paper_executor import PaperOnceExecutor
from .paper_runtime import PaperCycleRunner
from .paper_store import PersistentPaperOrderStore
from .runtime_lock import RuntimeFileLock

PAPER_SUBMISSION_ACK = "I_ACKNOWLEDGE_ALPACA_PAPER_ORDERS_ONLY"


def paper_submission_authorized(env: Mapping[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    forbidden = ("SIGNAL_VAULT_LIVE", "SIGNAL_VAULT_LIVE_TRADING",
                 "SIGNAL_VAULT_MODE")
    for name in forbidden:
        raw = values.get(name, "").strip().lower()
        if raw in {"live", "true", "1", "enabled", "yes"}:
            raise ValueError("live-trading flags are forbidden in the paper worker")
    raw = values.get("SIGNAL_VAULT_PAPER_ORDER_SUBMISSION", "").strip()
    if raw and raw != PAPER_SUBMISSION_ACK:
        raise ValueError("invalid paper-order acknowledgement")
    return raw == PAPER_SUBMISSION_ACK


def _db_path(env: Mapping[str, str]) -> Path:
    raw = env.get("SIGNAL_VAULT_PAPER_DB", "./data/signal-vault-paper.sqlite3").strip()
    if not raw or "\x00" in raw:
        raise ValueError("invalid paper database path")
    path = Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    env = os.environ
    credentials = PaperCredentials.from_environment(env)
    allow_submission = paper_submission_authorized(env)
    db = _db_path(env)

    raw_lock = env.get("SIGNAL_VAULT_RUNTIME_LOCK", "").strip()
    if "\x00" in raw_lock:
        raise ValueError("invalid paper runtime lock path")
    lock_path = Path(raw_lock).expanduser() if raw_lock else db.with_name(db.name + ".lock")
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
        result = runner.run_once(now=datetime.now(timezone.utc),
                                 allow_paper_submission=allow_submission)
        logical = store.logical_account()

    # Intentionally omit provider balances, account IDs, keys and secrets.
    print(json.dumps({
        "mode": "ALPACA_PAPER_ONLY",
        "state": result.state,
        "explanation": result.explanation,
        "client_order_id": result.client_order_id,
        "provider_stage": result.provider_stage,
        "paper_post_attempted": result.paper_post_attempted,
        "paper_submission_enabled": allow_submission,
        "logical_cash_usd": str(logical["cash_usd"]),
        "logical_btc_qty": str(logical["btc_qty"]),
        "logical_realized_pnl_usd": str(logical["realized_pnl_usd"]),
        "logical_fee_usd_equiv": str(logical["fees_usd_equiv"]),
    }, sort_keys=True))
    # Fail-closed states use nonzero exit so a supervisor can alert/retry reads.
    return 2 if result.state.startswith("BLOCKED_") or result.state == "HOLD_BAD_MARKET_DATA" else 0


if __name__ == "__main__":
    raise SystemExit(main())
