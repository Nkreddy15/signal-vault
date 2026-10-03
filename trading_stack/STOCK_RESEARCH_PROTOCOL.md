# Stock research protocol — frozen before receiving stock data

This is a development protocol, not an approved trading strategy. No broker orders, short selling or leverage. No profit cap or return target is used to select rules. Existing pauses remain unchanged.

Universe: the existing twelve symbols SPY, QQQ, AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM, V, AMD and TSLA. This is a fixed discretionary universe, not a point-in-time constituent database. Selection and survival bias must be disclosed.

Input: observed 15-minute regular-session Alpaca bars, January–September 2026, with an official trading calendar. Raw and all-adjusted series are separate. Adjusted series can support comparable signals; actual execution must use raw prices with explicit split handling. Dividends cannot be booked twice. Missing execution quotes delay fills; no forward-filled bars may become executions. IEX data remains a separate sensitivity from SIP.

Only three initial long-only families will be tested. Daily features use completed regular sessions and signals fill at the next observed regular-session opening quote. Intraday fills still follow causal stop and gap mechanics.

1. **Twenty-session relative strength.** Every last trading session of the week, rank eligible stocks by 20-session return divided by 20-session realized volatility. Require positive return and close above EMA20. Select the best two; retain until the next weekly rank changes or the trend filter fails. Require SPY above EMA50. Maximum hold is 20 sessions.
2. **Twenty-session breakout.** Require SPY above EMA50, asset above EMA20, and a completed close above the preceding 20-session high, excluding the current session. Rank by return/volatility, take at most two new entries. Exit on close below EMA20 or after 20 sessions.
3. **Trend pullback.** Require SPY above EMA50 and asset EMA20 above EMA50. A completed close at/below EMA20 followed by a later completed close above EMA20 triggers entry. Rank simultaneous candidates by positive 20-session return/volatility; take at most two. Exit on close below EMA50 or after 20 sessions.

All families need at least 60 complete feature sessions. Initial stop is two ATR14, clipped to 3–12% of entry; causal trailing distance equals that initial stop. Test separately and then one fixed equal-risk blend, with 1% account risk per entry, three simultaneous positions maximum and 80% notional allocation maximum. Position size naturally changes with equity; more capital does not force more weak trades. No fractional order below actual broker minimum can be counted as a supported execution.

Use verified account-applicable equity trading/regulatory fees, explicit spread and slippage sensitivity, and independent $0/$0.10 per-day operating-cost replays. Trading-day/session rules and overnight financing assumptions must be explicit. There is no crypto fee substitution or zero-cost profit claim. Confirm current fees before implementing equity P&L.

Primary development segment: January–June, with warm-up excluded from results. July–September is a frozen later-time check, not a guaranteed unbiased holdout: the fixed universe was chosen later and strategy work already saw other crypto data. Once opened, it cannot be repeatedly reused as validation. Report all initial families, monthly results, trade counts, drawdowns, exposure, idle time and cost sensitivity. Rule changes require a new version and new later data before activation. Do not activate a thin or inconsistent winner merely because one aggregate result is positive.
