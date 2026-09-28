"""Source-labelled performance reporting from Signal Vault's logical ledger.

Reports never infer profit from submitted orders. Only provider-reconciled orders
can enter applied_provider_orders, and total account return is based on marked
logical equity relative to the fixed $100 initial allocation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping
import json
import os
import tempfile

from .paper_store import PersistentPaperOrderStore

INITIAL_CAPITAL = Decimal("100")


def build_performance_report(store: PersistentPaperOrderStore, *, at: datetime) -> dict[str, object]:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware report time required")
    account = store.logical_account()
    mark = store.last_mark()
    stats = store.trade_statistics()
    halted, halt_reason = store.operator_halt()
    if mark is not None:
        equity = mark["equity_usd"]
        marked_utc = mark["marked_utc"].isoformat()
        mark_price = str(mark["mark_price"])
        equity_status = "MARKED_LOGICAL_EQUITY"
    elif account["btc_qty"] == 0:
        equity = account["cash_usd"]
        marked_utc = None
        mark_price = None
        equity_status = "CASH_ONLY_LOGICAL_EQUITY"
    else:
        equity = None
        marked_utc = None
        mark_price = None
        equity_status = "MARK_REQUIRED_FOR_OPEN_BTC_POSITION"
    return_pct = None if equity is None else ((equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * Decimal("100"))
    return {
        "schema_version": 1,
        "mode": "ALPACA_PAPER_ONLY",
        "source": "SIGNAL_VAULT_LOGICAL_LEDGER_AND_RECONCILED_PROVIDER_ORDERS",
        "generated_utc": at.astimezone(timezone.utc).isoformat(),
        "initial_capital_usd": str(INITIAL_CAPITAL),
        "equity_status": equity_status,
        "logical_equity_usd": None if equity is None else str(equity),
        "total_return_pct": None if return_pct is None else str(return_pct),
        "logical_cash_usd": str(account["cash_usd"]),
        "logical_btc_qty": str(account["btc_qty"]),
        "realized_pnl_usd": str(account["realized_pnl_usd"]),
        "fees_usd_equiv": str(account["fees_usd_equiv"]),
        "last_mark_price_btc_usd": mark_price,
        "last_marked_utc": marked_utc,
        "operator_halted": halted,
        "halt_reason": halt_reason,
        **stats,
        "performance_warning": "Paper/research results do not guarantee live profitability.",
    }


def write_report(path: str | Path, report: Mapping[str, object]) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.is_symlink():
        raise ValueError("report path must not be a symlink")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(report), handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target); os.chmod(target, 0o600)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
