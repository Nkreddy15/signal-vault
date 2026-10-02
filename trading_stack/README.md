# Open-source autonomous PAPER stack

This branch is intentionally separate from Signal Vault's custom engine.

## Crypto
- Engine: Freqtrade official Docker image
- Dashboard: built-in FreqUI
- Exchange data: Kraken spot public market data
- Mode: dry-run only
- Simulated wallet: $100
- Universe: BTC/USD, ETH/USD, SOL/USD, XRP/USD, DOGE/USD, ADA/USD
- Strategy: Strategy001 pinned from freqtrade/freqtrade-strategies commit f3340ce11f5bdf62f598522e64d1f5638eaa13f5
- Max open trades: 4
- Stake per trade: $15
- Startup: downloads 30 days of data and runs a bootstrap backtest, then starts dry-run trading.

## Stocks
- Engine: Lumibot 4.6.1
- Broker: Alpaca PAPER only
- Logical strategy budget: $100 regardless of Alpaca's simulated account balance
- Universe: AAPL, MSFT, GOOGL, AMZN, META, NVDA, JPM, V
- Rule: daily top-3 rotation by 20-trading-day momentum
- The strategy only manages symbols in its own universe and never touches crypto positions.

## Dashboards
- Crypto: FreqUI served by the Freqtrade REST service.
- Stocks: Alpaca's native PAPER dashboard for account equity, orders, positions, and P/L.

## One-week evaluation
Do not judge only by ending profit. Record:
1. net P/L,
2. maximum drawdown,
3. number of trades,
4. win/loss distribution,
5. turnover,
6. periods with no trades,
7. whether the bot stayed running without manual intervention.

The experiment is PAPER/dry-run only. No live-trading credentials or live endpoints are part of this stack.
