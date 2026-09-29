"""Deterministic small-notional economics, not a strategy or broker pricing quote.

Mirrors backtest.simulate's BUY and SELL cost arithmetic: the $15 buy budget
includes the buy fee; adverse slippage is applied to the entry/exit reference
prices; the sell fee is charged on gross exit USD proceeds. No trades execute.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Iterable

from .backtest import CostAssumptions

BPS = Decimal("10000")


def break_even_price_move_bps(*, costs: CostAssumptions | None = None) -> Decimal:
    """Required positive exit-reference / entry-reference change for flat cash P&L.

    Formula: (1 + entry_slippage) /
             [(1 - buy_fee) * (1 - exit_slippage) * (1 - sell_fee)] - 1.
    No exact provider spread/market impact is implied.
    """
    cfg = costs or CostAssumptions()
    fee = cfg.taker_fee_rate
    slip = cfg.slippage_rate
    return ((Decimal("1") + slip)
            / ((Decimal("1") - fee) ** 2 * (Decimal("1") - slip))
            - Decimal("1")) * BPS


def hypothetical_round_trip(*, price_move_bps: Decimal,
                            costs: CostAssumptions | None = None) -> dict[str, str]:
    """Model one self-contained BUY then full SELL for a fixed $15 budget.

    Price movement is measured from the BUY reference price to the SELL
    reference price; the reference entry price cancels from this calculation.
    This does not model order-book liquidity, funding or realistic fills.
    """
    cfg = costs or CostAssumptions()
    if (not isinstance(price_move_bps, Decimal) or not price_move_bps.is_finite()
            or price_move_bps <= -BPS):
        raise ValueError("price movement must be finite and exit price strictly positive")
    move = Decimal("1") + price_move_bps / BPS
    entry_cash_outflow = cfg.buy_budget_usd
    buy_fee = entry_cash_outflow * cfg.taker_fee_rate
    # With reference entry price normalized to one USD per base unit.
    base_qty = (entry_cash_outflow - buy_fee) / (Decimal("1") + cfg.slippage_rate)
    gross_exit = base_qty * move * (Decimal("1") - cfg.slippage_rate)
    sell_fee = gross_exit * cfg.taker_fee_rate
    net_exit = gross_exit - sell_fee
    return {
        "reference_price_move_bps": str(price_move_bps),
        "buy_budget_usd": str(entry_cash_outflow),
        "modeled_buy_fee_usd": str(buy_fee),
        "modeled_sell_fee_usd": str(sell_fee),
        "modeled_net_exit_proceeds_usd": str(net_exit),
        "modeled_round_trip_pnl_usd": str(net_exit - entry_cash_outflow),
    }


def report() -> dict:
    cfg = CostAssumptions()
    no_costs = CostAssumptions(taker_fee_rate=Decimal("0"), slippage_rate=Decimal("0"))
    moves = tuple(Decimal(v) for v in ("-100", "0", "25", "50", "75", "100", "150", "200"))
    return {
        "kind": "OFFLINE_HYPOTHETICAL_SMALL_NOTIONAL_COST_AUDIT",
        "notional_usd": str(cfg.buy_budget_usd),
        "assumed_fee_per_side_bps": str(cfg.taker_fee_rate * BPS),
        "assumed_slippage_per_side_bps": str(cfg.slippage_rate * BPS),
        "modeled_break_even_reference_price_move_bps": str(break_even_price_move_bps(costs=cfg)),
        "no_cost_break_even_bps": str(break_even_price_move_bps(costs=no_costs)),
        "scenarios": [
            {"with_assumed_costs": hypothetical_round_trip(price_move_bps=m, costs=cfg),
             "without_costs": hypothetical_round_trip(price_move_bps=m, costs=no_costs)}
            for m in moves
        ],
        "broker_order_submission": "DISABLED",
        "warning": "Sensitivity only. Fee/slippage hypotheses are not verified account-tier/provider fills; spread and liquidity may worsen actual execution.",
    }


def main() -> int:
    print(json.dumps(report(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
