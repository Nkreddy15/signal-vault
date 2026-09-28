# Provider assumptions checked 2026-09-28 — recheck before provider paper runs

Official Alpaca documentation (links are part of our engineering record, not guarantees):

- Crypto trading, supported orders, quantity precision and minimum: https://docs.alpaca.markets/us/docs/crypto-trading-1 . Crypto market/limit/stop-limit are documented with GTC/IOC and USD pair minimum quantity dynamically calculated as 10 / USD price; no more than 9 decimal places. This is why a proposed $5 order is rejected rather than automatically increased. A $15 research position can still become < $10 after adverse movement, requiring an explicit dust/manual-resolution policy.
- API order types and TIF: https://docs.alpaca.markets/us/docs/orders-at-alpaca . Do NOT reuse stock-style DAY orders for crypto.
- Public historical BTC/USD market data: https://docs.alpaca.markets/us/v1.1/reference/cryptobars-1 . Current planned endpoint: `https://data.alpaca.markets/v1beta3/crypto/us/bars`, hourly UTC bars, pagination, source/timeframe recorded. Fetch without account access where allowed. The prototype feed NEVER calls a trading endpoint.
- Alpaca paper trading: https://docs.alpaca.markets/us/docs/paper-trading . Separate paper host `https://paper-api.alpaca.markets`; provider paper fills are not live-market fill guarantees.
- Hypothetical backtest cost assumptions: taker fee **0.25%** per side, additional **0.10%** slippage per side, fixed $15 entry; they are sensitivity inputs, not verified actual account charges. Re-check current account fee tier and quantify spread and unmatched orders. Report all costs separately from hosting/LLM expenses.

**Authorization state:** No credentials collected; no authenticated requests, authenticated paper orders, live trades, funding, hosting, or billing. Paper access and actual submission require additional implementation, testing and approved access. Do not copy any broker secrets into Git or this document.
