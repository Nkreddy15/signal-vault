# V11: isolated $500 crypto paper trial

This launchable build implements the user's requested one-to-two-day forward experiment with the strongest recent cost-modeled crypto hypothesis: failed-rebound synthetic shorts. It creates a separate $500 simulated account and an immutable 48-hour deadline. It does not deposit funds, reset an Alpaca account, borrow assets or send broker orders. Old balances and trade histories are not carried into the new account.

## Start and review

Pull GitHub branch `phase-162-multimarket-reset` in GitHub Desktop. Open Docker Desktop, then run from the repository root:

```bash
bash trading_stack/start_v11_500_mac.sh
```

The existing `trading_stack/.env` is needed for the old local API and dashboard. The new synthetic engine receives no trading credentials and reads only public Kraken data. Its account is stored at `/freqtrade/data/paper-v11-500/ledger.sqlite3` in the existing Docker data volume. The dashboard selects V11 at `http://127.0.0.1:8090` and shows $500 starting balance and current equity.

```bash
bash trading_stack/status_v11_500_mac.sh
bash trading_stack/export_v11_500_mac.sh
```

The export saves `Downloads/signal-vault-v11-500-results.zip`. Canonical account state and events share a read-only SQLite snapshot; observed daily candles are included separately. Credentials are excluded. Attach that ZIP after the trial for analysis.

To stop entries and close synthetic positions at the next fresh observed quotes:

```bash
bash trading_stack/stop_v11_500_mac.sh
```

## Strategy and timing

The original formation universe is intersected with the current 15-pair margin sensitivity list. The signal function is imported directly from the tested bear research module. Require closed daily BTC below EMA21 with 28-day return ≤−3%. The asset must be below EMA21 with 28-day return ≤−3%, have rallied at least 3% over the two preceding closed sessions, and then close lower. Rank by negative 28-day momentum divided by 14-day volatility and select the best two candidates.

Decisions use complete UTC days, once per day. Current incomplete daily candles are excluded; daily history must be fresh, and wholly missing days reset feature warm-up. The initial scan only sets a boundary. Future qualifying signals can fill within ten minutes after 00:00 UTC on fresh public bid/ask. Signals missed during downtime are not filled retroactively. In New York on October 3, 00:00 UTC is 8 p.m. local time. No entry is guaranteed during 48 hours. This is the daily failed-rebound hypothesis, not a scalping trial.

Risk is the tested aggressive 3% equity budget per trade, with full notional reservation, at most six concurrent positions and 80% total allocation. Stops are three daily ATRs clipped to 6–20%; fixed-distance trailing begins after one initial stop-distance favorable move. There is no fixed profit target. Closed-day BTC/EMA regime failure exits at the next fresh quote; hard stops and trailing are monitored on observed quotes roughly every 30 seconds. Trial end forces prospective quote-based exits, overriding the research strategy's 28-day maximum hold. Intrabar movement, latency and gaps can produce different fills from historical candle approximations.

Current Kraken taker tiers use the trial's own rolling trade volume. Sell-short entry uses observed bid with 0.10% slippage; cover uses observed ask with 0.10% slippage, so observed spread is paid directly. Synthetic borrowing charges use the tested **illustrative light** 0.01% opening and 0.01% every four hours, with borrowed asset quantity valued at the latest observed midpoint. These are not current broker quotes. A $0.10/day operating allowance accrues by elapsed trial time, up to $0.20 for 48 hours; it is not a measured bill. Open-position financing continues until actual simulated closure if fresh quotes are unavailable after the deadline.

Existing 50% peak drawdown and 20% UTC-day loss triggers remain from the aggressive research specification; stops and price gaps can exceed planned losses. They are paper risk controls, not a capital guarantee. Actual collateral, liquidation, broker eligibility and borrow availability remain unmodeled.

## Account preservation and restart behavior

The launcher preflights complete daily history and bid/ask before creating the account. It pauses old V1 entries, stops older synthetic services and backs up their ledgers under `v11-upgrade-backups/<timestamp>`. If an older synthetic campaign still has held positions, it refuses the cutover and restarts the previously running old services so those positions retain management. It does not erase positions to obtain a clean trial. Old V1 held positions retain their own exits; their P&L remains separate.

Once the new account is selected, V1 has a persistent entry veto across restarts. Only V11 appears as the current crypto dashboard account. SQLite commits events and account state together. A rerun resumes the original balance, signals, positions and deadline; it does not grant another $500 or another 48 hours. An ended campaign cannot be silently relaunched as a fresh account. Frozen signal/indicator hashes and fee tiers are checked against persisted specifications.

Keep Docker running and the Mac powered with its lid open. The launcher reuses or starts `caffeinate`, but closing the lid, stopping Docker or shutting down interrupts quote monitoring. Rerun the launcher to resume after an interruption before the deadline. On return, the runner uses fresh prices; it cannot execute exits at prices observed while it was offline. If quotes are unavailable at the deadline, entry is blocked and positions remain pending until fresh quotes permit closure. Such a campaign is not reported as successfully closed while positions remain. Once all positions are closed at the end or stop request, the V11 process exits and does not restart automatically or continue polling public data. Dashboard and export remain available.

## Verification and evidence

The $500 historical counterpart previously ended at $542.54 before operating costs, or $529.21 with the operating allowance, over March–June on 15 trades. Those are development results, not profits booked into this trial. No historical trades or P&L seed the paper account.

Thirteen V11 fixtures cover isolated capital, persistence, duplicate prevention, stale/late quotes, incomplete rankings, daily-data parity, financing reconciliation, session closure, stop/regime exits, feed failures, caching, automatic process exit, older held-position detection and dashboard selection. Thirty existing V10 checks and the dashboard DOM harness also pass. These establish behavior on deterministic fixtures. Docker builds, public API access and actual launch on the user's Mac cannot be verified from this workspace; the launcher explicitly verifies those before announcing success.

Primary references: [Kraken OHLC endpoint](https://docs.kraken.com/api/docs/rest-api/get-ohlc-data), [fee schedule](https://www.kraken.com/features/fee-schedule), [US margin fees](https://support.kraken.com/articles/us-margin-fees).
