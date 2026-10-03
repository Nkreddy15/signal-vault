# Financing and bear-regime research — 2026-10-03

No strategy from this round qualifies for paper activation. Existing new-entry pauses remain in place. These changes add research accounting and data collection; they do not start services, place orders or alter account settings.

## Actual replay

The supplied `signal-vault-research.zip` contains 412,086 observed 15-minute candles for the original 24-asset formation universe, January–June 2026. January–February are feature warm-up; the continuous account and independent monthly accounts replay March–June. Each account starts with $100. These months have already been used in development and are not untouched validation.

128 weekly-strategy scenarios vary asset eligibility, direction, risk, financing, execution and operating cost. Another 24 scenarios test three fixed bear-regime hypotheses. All include taker trading fees, a 15-basis-point spread sensitivity and 0.10% slippage per side. No leverage increase was added; full entry notional is reserved.

The new short financing model charges an opening fee and four-hour rollover fees during the holding period. Rollover uses borrowed asset quantity and the latest observed mark in a shadow USD account. Cash, equity and risk limits see these debits immediately. Closing P&L includes them without charging twice. Financing does not increase trading volume for fee tiers. Missing quotes and delayed assessments retain their observation and due timestamps.

These are explicitly illustrative financing assumptions, not captured broker quotes:

| Profile | Opening fee | Rollover every four hours |
|---|---:|---:|
| Zero control | 0% | 0% |
| Light | 0.01% | 0.01% |
| Medium | 0.025% | 0.025% |
| Heavy | 0.05% | 0.05% |

Current US pair eligibility is applied **before ranking**. Its intersection with the original formation universe is BTC, ETH, XRP, SOL, SUI, DOGE, ZEC, PEPE, ADA, AVAX, LINK, RENDER, BCH, LTC and PENGU. This October 3 list does not reconstruct historical March–June eligibility or product availability.

## Results

All figures below are continuous March–June ending equity from $100, using trigger execution. They are development simulations, not paper or live profits.

| Experiment | Financing | Running cost/day | Ending equity | Trades |
|---|---|---:|---:|---:|
| Weekly short-only, current pair intersection, aggressive | Zero control | $0 | $102.74 | 16 |
| Same | Light | $0 | $101.25 | 16 |
| Same | Medium | $0 | $99.07 | 16 |
| Same | Heavy | $0 | $95.52 | 16 |
| BTC-gated weekly shorts | Light | $0 | $105.71 | 9 |
| Failed-rebound shorts | Light | $0 | $106.88 | 10 |
| Seven-day bear-channel shorts | Light | $0 | $100.22 | 10 |
| Failed-rebound shorts | Light | $0.10 | $93.43 | 9 |

The $106.88 failed-rebound result has only one profitable independent month, median monthly return of −0.21%, and ten trades. Its $93.43 operating-cost sensitivity has nine trades: costs change account size and later position sizing, so this is a separate replay rather than subtraction from the earlier result.

None of the 128 weekly scenarios passes the numerical development screen. All 76 scenarios across both labs with $0.10/day operating cost end below $100. None of the three bear families has enough trades or consistent independent-month performance to qualify. The larger $108.91 weekly gain uses the unrestricted 24-asset archive, zero financing and no operating costs; it is not a supported execution candidate.

The bear hypotheses use closed daily data and the next observed executable quote. The BTC gate requires price below EMA21 and 28-day return at or below −3%. The failed-rebound rule additionally requires an asset below EMA21 with negative 28-day momentum, a preceding two-day rebound of at least 3%, followed by a lower daily close. The channel rule requires a close below prior seven-day lows. Existing stops, trailing exits, account limits and a 28-day maximum hold remain in effect. These hypotheses were specified after seeing the earlier weekly results; that selection is another reason these are development evidence.

## Limits and verification

Actual collateral rules, liquidation, borrow availability, account minimums and historical financing quotes are not modeled. The simplified conversion of borrowed-asset charges also differs from native broker settlement. Current pair support alone cannot make these venue-native backtests. Monthly accounts reset independently; the continuous account does not.

The two earlier weekly baselines reproduce all 34 trade identities, fills, fees and P&L to within $0.000000001. Ending equity is unchanged at $103.85338002273382 for trigger and $102.7359981446472 for extrema. Focused tests cover financing boundaries, missing observations, accounting reconciliation, eligibility before ranking, causal features, pagination, session calendars, feed fallback and credential handling. The checked-in evidence directory contains scenario summaries, full ledgers, input receipts, source hashes and accounting checks.

## Next research input: US stocks

`prepare_stock_data_mac.sh` collects historical data for the original twelve-stock universe: SPY, QQQ, AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM, V, AMD and TSLA. It performs only GET requests to Alpaca historical bars and the trading calendar, using existing local paper credentials. It does not query private account state or send orders. Keys are never included in the ZIP.

The export covers January–September 2026, keeps raw and all-adjusted prices separate, respects regular session hours, daylight saving and early closes, records missing bars, and checks file hashes. It first requests SIP; if access is denied with HTTP 403, it restarts both adjustments on IEX and records the single-venue feed explicitly. It never fabricates omitted bars or combines feeds.

After pulling `phase-162-multimarket-reset`, run from the repository root:

```bash
bash trading_stack/prepare_stock_data_mac.sh
```

Then attach `Downloads/signal-vault-stock-data.zip`. Docker and the existing `trading_stack/.env` Alpaca paper keys are needed on the Mac. The API path has fixture coverage here; a real broker-data request cannot be verified without those local credentials. This command builds a research image and runs a one-off exporter; it does not resume trading.

Before inspecting that data, the stock research hypotheses are frozen in `STOCK_RESEARCH_PROTOCOL.md`. There is no stock-profit result from this round.

## Primary source references

- [Kraken US margin fees](https://support.kraken.com/articles/us-margin-fees)
- [Kraken US margin eligibility](https://support.kraken.com/articles/getting-started-us-margin)
- [Kraken financing fee basis](https://support.kraken.com/articles/206161568-what-are-the-fees-opening-and-rollover-for-trading-using-margin-)
- [Alpaca historical stock bars](https://docs.alpaca.markets/reference/stockbars)
- [Alpaca trading calendar](https://docs.alpaca.markets/reference/getcalendar-1)
- [Alpaca market-data FAQ](https://docs.alpaca.markets/docs/market-data-faq)
