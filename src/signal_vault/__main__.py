"""Safe offline proof of configuration, trade proposal, and risk screening."""

from datetime import datetime, timezone
from decimal import Decimal

from .broker import LocalDryRunBroker
from .config import RuntimeConfig
from .domain import PortfolioSnapshot, Side, TradeIntent
from .risk import RiskEngine


def main() -> None:
    config = RuntimeConfig.from_environment()
    now = datetime.now(timezone.utc)
    portfolio = PortfolioSnapshot(
        equity_usd=Decimal("100"),
        cash_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        session_start_equity_usd=Decimal("100"),
    )
    proposal = TradeIntent(
        market="crypto", venue="alpaca", symbol=config.symbol,
        side=Side.BUY, notional_usd=Decimal("5"),
        client_order_id="phase1-offline-demo-001",
        signal_id="phase1-demonstration-not-real-market-signal",
        quote_timestamp=now,
    )
    result = RiskEngine().evaluate(proposal, portfolio, now=now)
    print("SIGNAL VAULT PHASE 1 | NO EXTERNAL ORDER EXECUTION")
    print(f"Mode: {config.mode} | Broker: {config.broker}")
    print(f"Proposed dry-run buy: ${proposal.notional_usd} {proposal.symbol}")
    print(f"Risk decision: {'APPROVED' if result.approved else 'REJECTED'} {result.reasons}")
    if result.approved:
        receipt = LocalDryRunBroker().submit(proposal, result)
        print(f"Record: {receipt.status} | {receipt.note}")


if __name__ == "__main__":
    main()
