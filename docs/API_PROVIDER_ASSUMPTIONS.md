# Provider assumptions checked 2026-09-28 — recheck before provider paper runs

Official Alpaca documentation links are engineering inputs, not guarantees. Runtime provider metadata wins and missing/malformed facts fail closed.

- Crypto trading/order constraints: https://docs.alpaca.markets/us/docs/crypto-trading-1 . BTC/USD crypto supports market/limit/stop-limit with crypto-valid time-in-force rules; USD-pair minimum size is dynamic and base-quantity precision is limited. Signal Vault reads current asset `min_order_size`, `min_trade_increment`, and `price_increment` and rejects rather than silently upsizing.
- General order behavior: https://docs.alpaca.markets/us/docs/orders-at-alpaca . Never infer a fill from order submission/acceptance.
- Historical crypto bars: https://docs.alpaca.markets/us/v1.1/reference/cryptobars-1 . Current endpoint `https://data.alpaca.markets/v1beta3/crypto/us/bars`. Current docs include HTTP 401 for missing/invalid authentication, so production paper runtime now uses an authenticated fixed-host read client; the old unauthenticated default fails closed.
- Latest crypto quotes: https://docs.alpaca.markets/us/reference/cryptolatestquotes-1 . Endpoint `https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes`; used for fresh bid/ask execution-reference and spread/freshness checks.
- Paper trading: https://docs.alpaca.markets/us/docs/paper-trading . Trading host is pinned to `https://paper-api.alpaca.markets`; paper fills do not guarantee live execution quality.
- Account activities: https://docs.alpaca.markets/us/reference/getaccountactivitiesbyactivitytype-1 . Signal Vault queries order-filtered FILL and crypto fee activities. Crypto fee activities may be delayed, so buy fee quantity can be inferred from independently reconciled net BTC inventory and later must match provider CFEE; sell USD fee remains blocking until provider activity is final.
- Crypto fee schedule/docs: https://docs.alpaca.markets/us/docs/crypto-fees . Research cost assumptions are sensitivity inputs; actual account tier/activity must be verified before interpreting provider-paper economics.

## Current development assumptions

- Logical initial Signal Vault capital: exactly $100, independent of Alpaca's default paper buying power.
- Paper-development BUY ceiling: $15; aggregate marked/pending long exposure ceiling: $30; daily equity-loss pause $3; peak drawdown pause $10. These are development/risk-test settings, not guaranteed loss limits and not a live mandate.
- Fresh quote maximum age: 90 seconds; current code rejects crossed quotes and spreads over 50 bps before drafting. These thresholds require paper-run review.
- Baseline strategy: fixed 12/26 hourly EMA crossover, no pyramiding, HOLD allowed indefinitely. It is a software baseline, not a claimed edge.
- Research-only historical cost sensitivity previously used taker 0.25% + slippage 0.10% per side. Recheck actual tier, spread, fee activities and paper/live discrepancies before using any performance conclusion.

**Authorization state:** no paper credentials supplied, no authenticated request, genuine paper order, live trade, funding, hosting or billing action has occurred in this checkpoint. Never place secrets in Git, docs, screenshots or chat.
