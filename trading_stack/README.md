# Signal Vault autonomous PAPER stack

Latest separate campaign: [V10 paper runtime and Mac activation](V10_PAPER.md).
Run `bash trading_stack/start_v10_mac.sh` after pulling the latest branch.
The V1 sections below describe the legacy engine; V9 and V10 have separate ledgers.

This stack is intentionally PAPER/dry-run only. It is for unattended execution
evidence and observability while strategy quality is evaluated separately.

## Crypto
- Engine: Freqtrade official Docker image
- Exchange data: Kraken spot public market data
- Mode: dry-run only; exchange credentials are rejected by the launcher
- Simulated wallet: $100
- Universe: BTC/USD, ETH/USD, SOL/USD, XRP/USD, DOGE/USD, ADA/USD
- Strategy: SignalVaultPaperExecutionV1 on 5-minute bars
- Signal families: trend, momentum, breakout, mean-reversion bounce
- Max open trades: 4
- Stake per trade: $15
- Stoploss: 2%
- Protections: 15-minute pair cooldown, stoploss streak guard, and 5% equity drawdown lock

## Stocks
- Engine: Lumibot 4.6.1
- Broker: Alpaca PAPER only
- Logical strategy budget: $100 regardless of Alpaca's simulated account balance
- Universe: SPY, QQQ, AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM, V, AMD, TSLA
- Schedule: every 15 minutes during the US market session
- Signal families: trend, momentum, breakout, mean-reversion bounce, daily tailwind
- Max selected symbols: 2
- Safety: $90 investable cap, $2 minimum rebalance notional, 16 new-buy submissions/day
- The strategy only manages symbols in its own universe and never touches crypto positions.

## Dashboards
- Unified Signal Vault control room: http://127.0.0.1:8090
- Crypto FreqUI: http://127.0.0.1:8080
- Alpaca PAPER remains the broker-native stock audit trail.

The unified dashboard is read-only. It fetches Freqtrade health/profit/trades and
Alpaca PAPER account/positions/orders, filters stock detail to the strategy
universe, and exposes no order-writing endpoint.

## Start on macOS
From the repository root:

```bash
bash trading_stack/install_mac.sh
```

To keep the Mac awake for the evaluation week:

```bash
bash trading_stack/start_paper_week_mac.sh
```

To inspect health:

```bash
bash trading_stack/status_mac.sh
```

## One-week evaluation
Do not judge only by ending profit. Record:
1. net P/L,
2. maximum drawdown,
3. number of trades,
4. win/loss distribution,
5. turnover,
6. periods with no trades,
7. whether the bot stayed running without manual intervention.

Paper activity proves that execution plumbing works. It does not prove that a
strategy has positive expectancy. Live trading remains outside this stack.
