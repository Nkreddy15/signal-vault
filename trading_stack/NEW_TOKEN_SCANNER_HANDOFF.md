# Signal Vault new-token experiment — October 4, 2026

Implemented and fixture-tested; not deployed as an unattended campaign.
No DEX orders were sent. No wallet, transaction signer or execution endpoint is
present. No profitability has been demonstrated. Existing dashboard design,
historical research and ledgers are preserved.

## Completed

- Solana token discovery through DEX Screener's latest token-profile feed and
  pair lookups. Rotating bounded batches prevent always scanning only the first
  five profiles. This is incomplete profile-based coverage, not every launch.
- Conservative filters: pair age 5 minutes–24 hours, at least $50,000 quoted
  liquidity, classic SPL mint program, revoked mint/freeze authority, consistent
  RPC evidence slots, and top-ten token-account concentration at most 50%.
  Pool accounts are not excluded, so valid tokens may be conservatively rejected.
  Token-2022 tokens are blocked because extensions are not audited. LP control,
  true beneficial wallet concentration, wash trading and rug safety are unknown.
- Breakout and pullback hypotheses using prospective price observations and
  recent reported transaction counts. Six observations are required for breakout,
  eight for pullback; gaps/pair changes rewarm the sequence. No earlier fills are
  fabricated. These rules have not been optimized or validated for profitability.
- Jupiter Swap V2 `/order` quote-only adapter: no `taker`, no wallet keys and
  no signing/`execute` code. Entry checks exact mint/amount identity, minimum
  output, round-trip costs and impact. Protective exits can accept adverse impact;
  unavailable routes leave positions open/unresolved instead of inventing exits.
- Shared existing $500 ledger: $10 simulated entry, maximum $25 DEX entry-cost
  allocation, reservations and global position/exposure/loss limits. This is
  part of the same portfolio, never another $500. Quote minima determine token
  amount/proceeds; $0.10 per side is an illustrative network allowance, not an
  actual measured network fee. USDC is modeled at $1. Output quote amounts include
  route costs, which are not deducted a second time. Stops 12%, targets 25%,
  trailing stop after a 12% favorable move, maximum holding time one hour,
  ten-minute portfolio entry cooldown. Gaps/rugs can exceed budgeted stop losses.
- Optional Jev annotation adapter using the official TypeSafe API. Requires
  fresh timestamped/sourced post input, a pinned model, API credentials and an
  explicit cost switch. Maximum ten calls/day, counted durably before requests.
  AI comments on promotional language only: no claim of real users, price edge
  or token safety, and no authority over entries or risk gates. Social posts are
  treated as untrusted content. No social platform crawler is connected yet.
- Dashboard keeps original layout/CSS. New positions appear in the existing
  all-market table and clickable inspector, with quote-derived simulation labels,
  order/quote evidence, costs and controls. DEX charts show observed exit quotes
  and simulated markers on a scaled price axis; they do not invent candlesticks.
  Existing controls apply; pausing entries retains exits when a valid route exists.
  The authenticated `/api/discoveries` endpoint exposes observations/rejections.

## Evidence completed here

67 Python tests passed across existing accounting, regime research and the new
scanner tests. Both existing dashboard DOM/API harnesses passed, with a new DEX
quote-chart assertion. Authenticated discovery/DEX chart routes returned 200,
and unauthenticated requests returned 401. These are functional fixtures, not
real transaction receipts or desktop/mobile screenshot QA.

Live read-only probes succeeded: 30 token profiles returned; five Solana tokens
inspected and all five rejected for liquidity below the threshold. No orders
were recorded. Public Solana `getAccountInfo` also succeeded for the known USDC
mint. The actual probe reports are saved under `trading_stack/research/`.
Jupiter and Jev credentials were absent; their API behavior is fixture-tested,
not verified with a connected account. The live probe did not verify mint and
holder checks for the rejected tokens because they failed the earlier filter.

```sh
python -m unittest trading_stack.test_cloud_paper trading_stack.test_regime_v2 trading_stack.test_discovery -q
node trading_stack/test_final_dashboard.cjs
PYTHON=python node trading_stack/test_cloud_dashboard.cjs
```

## Remaining access and deployment

The worker already accepts `SV_CONFIG`. The new experimental configuration is
`trading_stack/cloud_paper/campaign.discovery.json`; default `campaign.json`
remains unchanged. Use a separate new campaign directory with this frozen
configuration. Never overwrite/reset the old V11/cloud account. Changing source
or configuration intentionally causes old accounts to refuse resume; keep old
campaigns on their original revision. This is not a state-migration release.

Required for quote simulation: set `JUPITER_API_KEY` directly in the worker's
environment. No wallet seed/private key is needed. Verify the key's allowance
before any paid service use. Actual Jupiter minimum/fee fields and provider
behavior must be checked against connected responses before starting the
prospective campaign.

Optional Jev setup: `TYPESAFE_API_KEY`, `SV_JEV_MODEL` pinned to an accessible
version (not `latest`), `SV_ALLOW_AI_CALLS=1`, and `SV_SOCIAL_EVIDENCE_FILE`.
That file maps mint addresses to objects containing numeric Unix-second `at`,
HTTPS `url` and `text`. It is local sourced input, not an implemented social
collector. Do not enable paid calls or add billing until the user's existing
no-cost testing constraint is resolved. Never put credentials in Git/chat.

Continuous no-charge hosting and an authenticated cloud dashboard URL remain
unverified. The existing Railway hourly GET-only research collector was not
changed or repurposed. Earlier allowance inspections failed with an agent usage
limit; this is not evidence that hosting credits are exhausted. The new worker
has not been deployed or left running. Docker, connected Jupiter/Jev behavior,
production restarts and browser screenshot QA remain outstanding.

Next action: configure the quote API key in an approved runtime, verify actual
buy/sell quote receipts and risk filters, confirm durable no-charge continuous
hosting, then start the explicitly experimental prospective paper campaign.
Report rejects, failed exits and complete after-cost results. Do not infer
profits from the social-media screenshots or from isolated test trades.

Official references checked:
- https://docs.dexscreener.com/api/reference
- https://solana.com/docs/rpc/http/getaccountinfo
- https://developers.jup.ag/docs/api-reference/swap/order
- https://developers.jup.ag/docs/swap/order-and-execute
- https://docs.typesafe.ai/api
