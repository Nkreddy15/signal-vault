"""Offline single-position paper simulation. Orders execute at NEXT candle open.

This research tool is not a brokerage simulator and cannot predict live fills.
It models fixed conservative fees/slippage and deliberately does not optimize
strategy parameters against the validation interval.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .domain import PortfolioSnapshot, Side, TradeIntent
from .market_data import Bar, load_csv, validate_bars
from .risk import RiskEngine, RiskLimits
from .strategy import Action, StrategyConfig, generate_signal


@dataclass(frozen=True)
class CostAssumptions:
    taker_fee_rate: Decimal = Decimal("0.0025")   # estimate, re-check current tier
    slippage_rate: Decimal = Decimal("0.0010")   # hypothesis, not measured live execution
    buy_budget_usd: Decimal = Decimal("15.00")   # above approx $10 provider minimum
    minimum_order_usd: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        for value in (self.taker_fee_rate, self.slippage_rate, self.buy_budget_usd,
                      self.minimum_order_usd):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("invalid simulation cost")
        if self.taker_fee_rate >= 1 or self.slippage_rate >= 1 or self.minimum_order_usd <= 0:
            raise ValueError("invalid fee, slippage or venue minimum")
        if self.buy_budget_usd < self.minimum_order_usd:
            raise ValueError("planned buy smaller than venue minimum")


@dataclass(frozen=True)
class SimulatedFill:
    time: str
    side: str
    reference_price: Decimal
    executed_price: Decimal
    base_qty: Decimal
    cash_delta: Decimal
    estimated_fee_usd: Decimal
    evidence_id: str


@dataclass(frozen=True)
class BacktestResult:
    initial_equity_usd: Decimal
    final_equity_usd: Decimal
    net_pnl_usd: Decimal
    max_drawdown_usd: Decimal
    total_estimated_fees_usd: Decimal
    fills: tuple[SimulatedFill, ...]
    rejected: tuple[str, ...]
    marked_open_base_qty: Decimal
    assumptions: CostAssumptions
    strategy_version: str
    last_mark_price: Decimal

    def to_dict(self) -> dict:
        return {
            "kind": "OFFLINE_HYPOTHETICAL_RESEARCH_NOT_PROVIDER_PAPER",
            "initial_equity_usd": str(self.initial_equity_usd),
            "final_equity_usd": str(self.final_equity_usd),
            "net_pnl_usd": str(self.net_pnl_usd),
            "max_drawdown_usd": str(self.max_drawdown_usd),
            "total_estimated_fees_usd": str(self.total_estimated_fees_usd),
            "open_base_qty": str(self.marked_open_base_qty),
            "last_mark_price": str(self.last_mark_price),
            "fill_count": len(self.fills),
            "fills": [{k: str(v) if isinstance(v, Decimal) else v for k, v in f.__dict__.items()}
                      for f in self.fills],
            "rejected": list(self.rejected),
            "strategy_version": self.strategy_version,
            "cost_assumptions": {k: str(v) for k, v in self.assumptions.__dict__.items()},
        }


def simulate(bars: Sequence[Bar], *, as_of: datetime,
             strategy: StrategyConfig | None = None,
             costs: CostAssumptions | None = None,
             limits: RiskLimits | None = None) -> BacktestResult:
    cfg, prices = strategy or StrategyConfig(), costs or CostAssumptions()
    policy = limits or RiskLimits(max_single_buy_usd=Decimal("15"),
                                  max_total_long_exposure_usd=Decimal("30"))
    if prices.buy_budget_usd > policy.max_single_buy_usd:
        raise ValueError("simulated buy budget exceeds safety policy")
    candles = validate_bars(bars, as_of=as_of, min_count=cfg.slow_hours + 3)
    risk = RiskEngine(policy)
    starting = cash = peak = daily_anchor = Decimal("100")
    holding = Decimal("0")
    max_drawdown = fees = Decimal("0")
    last_day = None
    fills: list[SimulatedFill] = []
    rejected: list[str] = []

    # i is the OPEN of the EXECUTION candle. The signal is derived exclusively
    # from bars [:i], whose last bar closed at candles[i].start.
    for i in range(cfg.slow_hours + 2, len(candles)):
        candle = candles[i]
        mark_open = cash + holding * candle.open
        if last_day != candle.start.date():
            # Anchor at the PRIOR closed bar's marked value. Resetting at the
            # new bar's OPEN would erase an overnight/downward gap from the
            # daily loss calculation and could permit unsafe new buys.
            daily_anchor = cash + holding * candles[i - 1].close
            last_day = candle.start.date()
        peak = max(peak, mark_open)
        max_drawdown = max(max_drawdown, peak - mark_open)
        decision = generate_signal(candles[:i], cfg)
        if decision.action == Action.HOLD:
            mark_close = cash + holding * candle.close
            peak = max(peak, mark_close)
            max_drawdown = max(max_drawdown, peak - mark_close)
            continue
        if decision.action == Action.BUY and holding > 0:
            continue  # initial strategy permits only one position at a time
        if decision.action == Action.SELL and holding == 0:
            continue
        notion = prices.buy_budget_usd if decision.action == Action.BUY else holding * candle.open
        if notion < prices.minimum_order_usd:
            rejected.append(f"{candle.start.isoformat()}: {decision.action.value} below estimated venue minimum")
            continue  # e.g. sell dust is NOT assumed to have executed
        snap = PortfolioSnapshot(
            equity_usd=mark_open, cash_usd=cash, peak_equity_usd=peak,
            session_start_equity_usd=daily_anchor,
            long_positions_usd={"BTC/USD": holding * candle.open} if holding else {},
        )
        side = Side.BUY if decision.action == Action.BUY else Side.SELL
        trade = TradeIntent(market="crypto", venue="alpaca", symbol="BTC/USD", side=side,
                            notional_usd=notion, client_order_id=f"backtest-{decision.evidence_id[:32]}",
                            signal_id=decision.evidence_id, quote_timestamp=candle.start)
        result = risk.evaluate(trade, snap, now=candle.start)
        if not result.approved:
            rejected.append(f"{candle.start.isoformat()}: {'; '.join(result.reasons)}")
            continue
        if side == Side.BUY:
            executed = candle.open * (Decimal(1) + prices.slippage_rate)
            fee = notion * prices.taker_fee_rate
            qty = (notion - fee) / executed
            cash -= notion
            holding += qty
            delta = -notion
        else:
            executed = candle.open * (Decimal(1) - prices.slippage_rate)
            gross = holding * executed
            fee = gross * prices.taker_fee_rate
            qty = holding
            delta = gross - fee
            cash += delta
            holding = Decimal("0")
        fees += fee
        fills.append(SimulatedFill(candle.start.isoformat(), side.value, candle.open, executed,
                                   qty, delta, fee, decision.evidence_id))
        mark_close = cash + holding * candle.close
        peak = max(peak, mark_close)
        max_drawdown = max(max_drawdown, peak - mark_close)
    final_equity = cash + holding * candles[-1].close  # mark only; not a realized sale
    peak = max(peak, final_equity)
    max_drawdown = max(max_drawdown, peak - final_equity)
    return BacktestResult(starting, final_equity, final_equity - starting, max_drawdown,
                          fees, tuple(fills), tuple(rejected), holding, prices,
                          cfg.strategy_version, candles[-1].close)



@dataclass(frozen=True)
class ResearchFold:
    """One independent, chronologically disjoint evaluation window.

    Indicators may use earlier history; positions and the $100 research bankroll
    reset at the evaluation start. This is NOT live walk-forward optimization.
    """
    evaluation_start: str
    evaluation_end: str
    warmup_hours: int
    result: BacktestResult


def chronological_research_folds(bars: Sequence[Bar], *, as_of: datetime,
                                 strategy: StrategyConfig | None = None,
                                 evaluation_hours: int = 168,
                                 costs: CostAssumptions | None = None,
                                 limits: RiskLimits | None = None) -> tuple[ResearchFold, ...]:
    """Evaluate fixed, predeclared parameters on subsequent nonoverlapping folds.

    Earlier candles are used ONLY as indicator warmup. Each test fold runs using
    that window's next-open orders and starts with a fresh simulated $100. Never
    use these results to claim a strategy was trained and independently validated.
    """
    cfg = strategy or StrategyConfig()
    warmup = cfg.slow_hours + 2
    if not isinstance(evaluation_hours, int) or evaluation_hours < 2:
        raise ValueError("evaluation fold must contain at least two hours")
    sequence = validate_bars(bars, as_of=as_of, min_count=warmup + evaluation_hours)
    folds: list[ResearchFold] = []
    for start in range(warmup, len(sequence), evaluation_hours):
        stop = min(start + evaluation_hours, len(sequence))
        if stop - start < 2:
            break
        view = sequence[start - warmup:stop]
        run = simulate(view, as_of=view[-1].close_time, strategy=cfg, costs=costs, limits=limits)
        folds.append(ResearchFold(sequence[start].start.isoformat(),
                                  sequence[stop - 1].close_time.isoformat(), warmup, run))
    return tuple(folds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline, cost-aware Signal Vault research backtest")
    parser.add_argument("csv", type=Path, help="UTC hourly CSV with timestamp,open,high,low,close,volume")
    parser.add_argument("--as-of", required=True, help="UTC ISO-8601 timestamp, e.g. 2026-09-28T00:00:00Z")
    parser.add_argument("--fold-hours", type=int, default=0, help="Optional disjoint research folds (e.g. 168 hours)")
    args = parser.parse_args()
    from .market_data import utc_timestamp
    bars = load_csv(args.csv, as_of=utc_timestamp(args.as_of), min_count=29)
    if args.fold_hours:
        fold_results = chronological_research_folds(
            bars, as_of=utc_timestamp(args.as_of), evaluation_hours=args.fold_hours)
        output = {"kind": "OFFLINE_DISJOINT_CHRONOLOGICAL_RESEARCH_NOT_PROVIDER_PAPER",
                  "folds": [{"evaluation_start": f.evaluation_start,
                              "evaluation_end": f.evaluation_end,
                              "warmup_hours": f.warmup_hours,
                              "result": f.result.to_dict()} for f in fold_results]}
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(simulate(bars, as_of=utc_timestamp(args.as_of)).to_dict(), indent=2))


if __name__ == "__main__":
    main()
