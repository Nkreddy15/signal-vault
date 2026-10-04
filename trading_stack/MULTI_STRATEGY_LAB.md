# Multi-strategy research and compounding

V10 is paused after failing its historical OHLC stress replay. Its $5 campaign
loss trigger was a risk cutoff, not a ceiling on potential profit. That replay
filled exits at candle extremes; a normal trigger model must be compared with
that stress assumption before attributing all losses to the signals.

This release builds a research runner. It does not activate another paper
strategy or claim to have found a profitable candidate. The user's target is
$100 to $1,000 or more in one month; the report explicitly measures how often
an independent complete calendar month ends at $1,000+. Tenfold growth in 30
days requires about 7.98% compounded daily. A remembered profitable trading day
does not establish that monthly expectancy or its drawdown.

## Run on the Mac

Fetch and pull `phase-162-multimarket-reset` in GitHub Desktop, then run from
the existing Signal Vault repository with Docker Desktop running:

```bash
bash trading_stack/research_multi_mac.sh
cat .data/multi-strategy-lab/multi-strategy-results.md
```

Existing Q1/Q2 Feather files are reused; missing files are prepared from the
cached Kraken quarterly archives. Running containers are not restarted. The
V10 drain marker, ledgers, and dashboard remain intact. No keys, deposits,
subscriptions, broker orders, or new service are involved.

The default run evaluates 80 fixed configurations: five strategy arrangements
times two risk profiles, two side modes, two modeled spreads, and two execution
models. Each prints progress, runs one continuous compounding account across
H1, and runs independent $100 calendar-month accounts. It also evaluates 16
selectors that choose next month's arrangement using the preceding month only;
they carry actual cash and rolling fee volume continuously. If the previous
month offers no positive candidate, they open no new positions. Existing
positions retain their exits. There is no parameter optimizer or automatic
activation of a historical winner.

JSON summary and the readable Markdown table are copied to
`.data/multi-strategy-lab/`. Detailed trades, daily equity curves, individual
reports and an incremental progress checkpoint are retained in the existing
Docker volume at `/freqtrade/data/multi-strategy-lab/`.

## Strategies sharing one account

The same six currently available archive assets are used: BTC, ETH, SOL, XRP,
DOGE and ADA in USD. This is not an all-coin or all-market result.

| Arrangement | Entry hypothesis | Exit design |
|---|---|---|
| Breakout | 24h price-channel break, EMA trend and elevated volume | ATR stop, larger target, trailing stop, 96h maximum |
| Pullback | Price recrosses EMA20 within an EMA60/200 trend, ADX and RSI confirmation | ATR stop, larger target, trailing stop, 72h maximum |
| Range reversal | Prior 2-sigma stretch reverses in low ADX, with sufficient room to the 24h mean | ATR stop, mean target, 24h maximum |
| Rotation | Once daily, rank eligible assets by directional 24h return divided by ATR | Wider ATR stop, target, trailing stop, 48h maximum |
| Blend | All four compete for the same cash; opposing same-asset signals are rejected | Each position retains its owning strategy's exit rules |

Signals use only completed candles and enter at the following bar's open.
Opening price drift is limited to the larger of 1% and three prior-candle ATRs.
Range targets remain anchored to the signal's actual rolling mean; target room
after costs is checked again against the modeled entry fill.
Indicator state restarts after every missing candle; missing data is not filled.
The blend holds one position per asset and allocates at most half of marked
equity to one family when opening new positions. Individual arrangement runs
are comparisons; their returns must never be added as though they used one $100
account. Cross-asset score ranking is a fixed heuristic, not a learned forecast
of expected profit or confidence.

## Capital, costs, and risk

Position budgets use current marked equity, so retained profit can compound.
Available simultaneous positions scale with equity: two at $100, four at $200,
and up to six at $300+. Fees do not instantly collapse the slot count at a
threshold. More capacity does not force extra orders when no signal qualifies.

| Profile | Budgeted loss per position | Daily equity-loss trigger | Peak-equity drawdown trigger |
|---|---:|---:|---:|
| Balanced | 1% including cost reserve | 10% | 25% |
| Aggressive | 3% including cost reserve | 20% | 50% |

These are **research scenarios**, not an activated risk change. Stakes are also
limited by available unreserved cash, an 80% allocation budget and the available
slot count. Exposure changes after price moves; these entry budgets are not
guaranteed loss limits. Every entry deducts its fee immediately. An asset's
capital is reserved until exit; another strategy cannot spend it. All scenarios
use one-times notional collateral, without leverage.

Long-only is spot accounting. Synthetic long/short is an experimental reference:
shorts are not executable spot sales. It includes an assumed 0.03% daily short
carry, not a verified borrowing/funding quote. Eligibility, borrow availability,
funding, liquidation and collateral mechanics would require venue-specific work
before any executable short implementation.

Costs use Kraken's verified October 3, 2026 spot **taker** schedule: initially
0.80% per side, with tier changes based only on the simulated account's rolling
30-day filled notional. An exit charges its actual notional at that moment's
tier. Tier benefits are not assumed merely because capital grows. Both 5 and 15
bps modeled spreads and 0.10% slippage per side are included in fill prices.
Targets require at least a further 1% gross room beyond nominal round-trip costs.
There are no assumed free or guaranteed maker fills. Actual fees depend on the
eventual venue/account; this is a declared Kraken scenario, not a universal fee.

Trigger execution honors adverse opening gaps, fills intrabar stops/targets at
their trigger plus adverse slippage, and takes the stop when both levels are
touched. Extrema execution instead fills intrabar exits at candle extremes.
Both are approximations: 15m OHLC cannot reproduce the path of 30-second quotes
or an executable fill's liquidity. Trailing levels computed from a candle's
high/low become active in the next candle. End positions lacking a current bar
remain pending rather than receiving an invented liquidation. Drawdown is
sampled at bar opens/closes and realized exits; simultaneous intrabar portfolio
equity is unknown. Gap losses can exceed risk triggers and negative equity is
reported rather than clamped away.

## Results and decision rule

Reports include continuous ending equity, net P&L, fees, carry, trade counts,
strategy contributions, exposure, fee tiers, ambiguity, missing marks, monthly
best/median/worst outcomes, and months ending at $1,000+. Costed BTC and equal-
weight spot buy-and-hold are included as descriptive baselines.

The fixed development screen requires long-only, at least four complete months,
positive continuous and median monthly returns, at least 60% positive months,
at least 20 trades, profit factor at least 1.1, no pending positions, and drawdown
within the profile's trigger. A robust development candidate must pass all four
5/15bps trigger/extrema scenarios. Custom reduced runs cannot bypass missing
scenarios. Passing this screen neither implies the $1,000 goal was achieved nor
authorizes activation. The first calendar month is partial after indicator
warmup and is excluded from complete-month goal and screen statistics.

Q1/Q2 have already informed development. Historical selection, including the
past-month selector, does not make these data unseen. Any selected hypothesis
must be frozen and checked on untouched data plus prospective paper fills.
The full comparison count is retained to expose the risk of choosing a lucky
historical winner. Power, connectivity and subscription costs default to zero
because the user's actual costs are unknown. Supply a daily estimate with
`--daily-operating-cost-usd AMOUNT` to deduct running costs from every simulated
account, including cash-only periods and feed gaps. Results expose this cost
separately. Buy-and-hold baselines do not pay bot operating costs.

## Research sources

These support families or methods, not the profitability of the exact custom
rules above. No published performance is imported as this bot's performance.

- [Liu and Tsyvinski, Risks and Returns of Cryptocurrency](https://www.nber.org/papers/w24877): cryptocurrency momentum and investor attention.
- [Liu, Tsyvinski and Wu, Common Risk Factors in Cryptocurrency](https://www.nber.org/papers/w25882): cross-sectional momentum.
- [Short-horizon mean reversion](https://arxiv.org/abs/2608.21888): a detectable gross reversal effect can still fail after costs; preprint, not proof of our range strategy.
- [The Probability of Backtest Overfitting](https://scholarworks.wmich.edu/math_pubs/42/): repeated candidate comparison creates selection risk.
- [Freqtrade backtesting assumptions](https://www.freqtrade.io/en/stable/backtesting/) and [lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/): execution assumptions and causal signal checks.
- [Kraken fee schedule](https://support.kraken.com/articles/cross-platform-fee-tier-changes) and [historical data](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data).

## Verification limits

Mechanics tests cover timestamp resolutions, genuine duplicate rejection,
indicator/signal prefix invariance, missing-candle warmup, following-bar entries,
long/short cash accounting, cost application, rolling fee tiers, shared capital,
capacity scaling, conflict rejection, gap loss overshoot, missing end marks,
past-only month selection, trailing causality, and CLI report serialization.
Generated test paths are fixtures, not evidence of market performance. Actual
Kraken archive replays and Docker execution must run on the Mac; the build
workspace lacks those datasets and Docker.
