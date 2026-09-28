"""Independent paper-broker end-state accounting checks (NO order submission).

An accepted/filled status cannot alone release a durable local reservation.
The pre-submission account/position snapshot MUST be durably recorded before
HTTP POST. At terminal, fresh source-retrieved order + account + positions must
be consistent with the local draft and the baseline, allowing for crypto fees
in the received currency. Divergence stays unreconciled and needs investigation.

This is a conservative single-venue, one-order-at-a-time PAPER prototype. It
is not a generalized brokerage tax/fee ledger or proof of live profitability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Mapping, Sequence

from .paper_order_state import PaperOrderState, Stage, TERMINAL_PROVIDER_STATES

EPS_BTC = Decimal("0.000000001")
EPS_USD = Decimal("0.03")
MAX_FEE_RATIO = Decimal("0.02")  # conservative audit tolerance, not fee quote


def _decimal(value: object, *, name: str, nonnegative: bool = True) -> Decimal:
    try:
        result = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError(f"invalid provider {name}") from exc
    if not result.is_finite() or (nonnegative and result < 0):
        raise ValueError(f"non-finite or negative provider {name}")
    return result


def _aware(stamp: datetime) -> bool:
    return isinstance(stamp, datetime) and stamp.tzinfo is not None and stamp.utcoffset() is not None


@dataclass(frozen=True)
class PaperHoldings:
    account_id: str
    cash_usd: Decimal
    btc_qty: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, str) or not self.account_id.strip():
            raise ValueError("source account identity required")
        if not _aware(self.observed_at):
            raise ValueError("source snapshot must have timezone-aware capture time")
        for key in ("cash_usd", "btc_qty"):
            v = getattr(self, key)
            if not isinstance(v, Decimal) or not v.is_finite() or v < 0:
                raise ValueError(f"invalid source holdings {key}")

    def canonical(self) -> dict[str, str]:
        return {"account_id": self.account_id, "cash_usd": str(self.cash_usd),
                "btc_qty": str(self.btc_qty),
                "observed_at": self.observed_at.astimezone(timezone.utc).isoformat()}

    @classmethod
    def from_canonical(cls, data: Mapping[str, str]) -> "PaperHoldings":
        return cls(data["account_id"], _decimal(data["cash_usd"], name="cash"),
                   _decimal(data["btc_qty"], name="btc quantity"),
                   datetime.fromisoformat(data["observed_at"]))


def parse_paper_holdings(account: Mapping[str, object],
                         positions: Sequence[Mapping[str, object]], *,
                         observed_at: datetime) -> PaperHoldings:
    """Parse independent paper GET responses, rejecting untracked positions.

    The caller must obtain account and positions from the allowlisted PAPER host.
    These responses must not originate from an AI model or an estimated balance.
    """
    if not isinstance(account, Mapping) or not isinstance(positions, list):
        raise ValueError("paper account and positions GET responses required")
    if str(account.get("status", "")).upper() != "ACTIVE":
        raise ValueError("paper account not active")
    if account.get("trading_blocked") is not False:
        raise ValueError("paper account is blocked or status unknown")
    if account.get("crypto_status") not in (None, "ACTIVE"):
        raise ValueError("paper crypto privileges not active")
    if not isinstance(account.get("id"), str) or not account["id"].strip():
        raise ValueError("paper account id missing")
    cash = _decimal(account.get("cash"), name="cash")
    nonmargin = _decimal(account.get("non_marginable_buying_power"), name="buying power")
    if cash < 0 or nonmargin < 0:
        raise ValueError("borrowed-funds balance not permitted")
    btc = Decimal("0")
    seen = False
    for position in positions:
        if not isinstance(position, Mapping) or position.get("symbol") not in ("BTC/USD", "BTCUSD"):
            raise ValueError("unexpected external position: isolated BTC test required")
        if seen or position.get("side") != "long":
            raise ValueError("duplicate BTC position or short exposure")
        seen = True
        btc = _decimal(position.get("qty"), name="BTC position")
    return PaperHoldings(account["id"], cash, btc, observed_at)


def validate_terminal_evidence(state: PaperOrderState, draft: Mapping[str, str],
                               baseline: PaperHoldings, post: PaperHoldings,
                               order: Mapping[str, object], *,
                               at: datetime) -> str:
    """Return tamper-evident SHA256 of corroborated broker facts, else reject.

    This checks *net holdings*, not assumptions that filled_qty equals a crypto
    position increase: purchase fees can be deducted from the received asset.
    If concurrent account activity has changed holdings, do not guess which
    dollars are ours; keep the order unreconciled until separately investigated.
    """
    if state.stage is not Stage.BROKER_TERMINAL_UNRECONCILED:
        raise ValueError("only terminal paper orders can be reconciled")
    if not _aware(at) or not _aware(baseline.observed_at) or not _aware(post.observed_at):
        raise ValueError("auditor requires timezone-aware event times")
    if (baseline.account_id != post.account_id or
        post.observed_at <= baseline.observed_at or
        post.observed_at > at or
        at - post.observed_at > timedelta(seconds=90)):
        raise ValueError("stale, unordered, or mismatched account snapshots")
    if not isinstance(order, Mapping) or (
        order.get("id") != state.broker_order_id or
        order.get("client_order_id") != state.client_order_id or
        order.get("symbol") != draft.get("symbol") or
        order.get("side") != draft.get("side") or
        order.get("type") != draft.get("type") or
        order.get("time_in_force") != draft.get("time_in_force") or
        order.get("status") != state.provider_status or
        order.get("status") not in TERMINAL_PROVIDER_STATES
    ):
        raise ValueError("source order facts disagree with durable approved order")
    if draft.get("side") == "buy":
        if "qty" in draft or "qty" in order and order["qty"] is not None:
            raise ValueError("paper notional buy unexpectedly turned into quantity order")
        if _decimal(order.get("notional"), name="order notional") != _decimal(draft.get("notional"), name="draft notional"):
            raise ValueError("broker notional differs from approved draft")
    elif draft.get("side") == "sell":
        if "notional" in draft or ("notional" in order and order["notional"] is not None):
            raise ValueError("paper quantity sell unexpectedly turned into notional order")
        if _decimal(order.get("qty"), name="order quantity") != _decimal(draft.get("qty"), name="draft quantity"):
            raise ValueError("broker quantity differs from approved draft")
    else:
        raise ValueError("unsupported draft side")

    qty = _decimal(order.get("filled_qty"), name="filled quantity")
    if qty != state.cumulative_filled_qty:
        raise ValueError("source cumulative fill differs from tracked paper state")
    px_raw = order.get("filled_avg_price")
    px = None if px_raw is None else _decimal(px_raw, name="average price")
    if px != state.filled_avg_price:
        raise ValueError("average price changed between broker reads")
    if qty > 0 and (px is None or px == 0):
        raise ValueError("filled order has no positive price")
    if qty == 0 and px is not None:
        raise ValueError("unfilled order has unexpected price")
    if draft.get("side") == "sell" and qty > _decimal(draft["qty"], name="draft quantity"):
        raise ValueError("sell filled more than was approved")
    if draft.get("side") == "buy" and qty > 0 and qty * px > _decimal(draft["notional"], name="draft notional") + EPS_USD:
        raise ValueError("buy filled value exceeded authorized notional")

    actual_cash_delta = post.cash_usd - baseline.cash_usd
    actual_btc_delta = post.btc_qty - baseline.btc_qty
    gross = qty * px if qty else Decimal("0")
    # Receive-currency fees may reduce BTC bought or USD received after a sell.
    if draft["side"] == "buy":
        if not (-gross - EPS_USD <= actual_cash_delta <= -gross + EPS_USD):
            raise ValueError("buy cash debit does not reconcile")
        if not (qty * (Decimal("1") - MAX_FEE_RATIO) - EPS_BTC <= actual_btc_delta <= qty + EPS_BTC):
            raise ValueError("buy BTC receipt does not reconcile including possible base fees")
    else:
        if not (-qty - EPS_BTC <= actual_btc_delta <= -qty + EPS_BTC):
            raise ValueError("sell BTC debit does not reconcile")
        if not (gross * (Decimal("1") - MAX_FEE_RATIO) - EPS_USD <= actual_cash_delta <= gross + EPS_USD):
            raise ValueError("sell USD receipt does not reconcile including possible quote fees")

    evidence = {"client_order_id": state.client_order_id,
                "broker_order_id": state.broker_order_id,
                "status": state.provider_status, "side": draft["side"],
                "cumulative_filled_qty": str(qty), "filled_avg_price": str(px) if px else None,
                "baseline": baseline.canonical(), "post": post.canonical(),
                "source_order": {k: order.get(k) for k in
                                 ("client_order_id", "id", "symbol", "side", "type",
                                  "time_in_force", "status", "filled_qty", "filled_avg_price", "qty", "notional")}}
    return sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
