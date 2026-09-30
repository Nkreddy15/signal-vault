# Phase 13 — One independent six-crypto hourly prospective source (NOT deployed)

**Why this phase exists:** a six-coin retrospective data download does not
expand the existing Railway BTC-only prospective journal. We are building a
separate unactivated six-crypto candidate source, preserving the original
BTC cron and 168 genuinely prospective, contiguous-hour checkpoint.

The six predeclared candidates, all on an explicit crypto-US DATA feed,
are AVAX/USD, BTC/USD, ETH/USD, LINK/USD, LTC/USD and SOL/USD.
`crypto_universe_forward.py` implements a separate root and receipt chain;
`railway_universe_cron.py` is an **unactivated deployment adapter**.
No existing volume, secret, service, Railway billing, Dockerfile or start
command is changed merely by merging these research sources.

## Collection rule and independent evidence

1. Once per scheduled UTC close at minute :07 (safe :03–:24), require a
   **pre-existing separate private 0700 persistent volume**. Default future
   mount: `/var/lib/signal-vault/forward-universe`, NOT the already active
   `/var/lib/signal-vault/forward`.
2. Validate EVERY previously written immutable JSON hourly receipt, its
   create-only filename, source DATA batch SHA, per-symbol source candle
   chronology/OHLCV/feed and cross-receipt SHA pointer BEFORE using a
   credential/provider factory. A duplicate, clock rollback, late tick
   or corrupted chain issues ZERO authenticated data requests.
3. The **first run fetches the 72 fully closed hourly candles PER symbol**
   in a single bounded/paginated GET via our existing approved
   `BoundedAlpacaHistoricalBatch`. This is a retrospective baseline,
   counts as **zero genuinely prospective observations** (not 432).
   The canonical historical source remains explicitly historical.
4. On exactly the next UTC hour, fetch only the new closed one-hour
   six-symbol batch and revalidate its source/actual capture freshness;
   archive one create-only 0600 SHA-bound receipt for **six asset-bar
   observations but ONE distinct independent UTC clock hour**.
   Prospectivity is derived independently from the actual capture time
   and an intact hourly receipt chain, never from the GET endpoint itself.
5. If the scheduler misses any hour, preserve ALL earlier SHA receipts,
   start a NEW independent 72h historical baseline segment at the next
   available safe UTC slot, and reset the new segment's prospective count
   to zero. Never hide gaps or retroactively mark missing bars as forward.
6. The read-only `universe_status` reaudits all receipts without a key or
   provider request. Its threshold requires **168 genuine contiguous UTC
   clock hours for the CURRENT segment**, not 168*6 asset-bars, 72h
   bootstrap records or crypto+stock records merged.

The six-symbol provider adapter uses a fixed, redirect-refusing
`GET https://data.alpaca.markets/v1beta3/crypto/us/bars` request only.
The existing research client consumes **all** bounded page tokens and
fails closed for missing requested symbol/hour, mixed feed, unexpected
extra rows, malformed OHLCV, truncated downloads, out-of-order clocks,
symlinked/private evidence damage and duplicate immutable filenames.

Raw downloaded bars remain marked `prospective=false`, as they are always
source history returned by a provider endpoint. The collector's independent
receipt adds its separate evidence classification only for timely,
previously unobserved post-bootstrap UTC-hour captures. An unsigned
local SHA chain is an internal integrity check, NOT a signed off-host
provenance guarantee, trading recommendation or executable broker fill.

## NO automatic activation, no broker operations

The existing Railway service is still
`btcusd-hourly-get-cron`, with its original code/volume/cron intact.
The future six-market adapter deliberately requires:

| Configuration | NEW isolated value |
|---|---|
| Separate Railway service | Name `six-crypto-forward-get-only` |
| Native cron | `7 * * * *` UTC; no public port, no restart loops |
| Start command | `python -m signal_vault.railway_universe_cron --once` |
| **Different** volume mount | `/var/lib/signal-vault/forward-universe` |
| Run UID | `RAILWAY_RUN_UID=0` (Railway's mounted volume behavior) |
| New dedicated DATA-only variable names | `SIGNAL_VAULT_UNIVERSE_DATA_KEY_ID`, `SIGNAL_VAULT_UNIVERSE_DATA_SECRET` |

New DATA secret values must be supplied privately by the owner when a
separate service is authorized; they must NEVER be posted in chat, committed
to GitHub, printed, or confused with old BTC/PAPER order credentials.
A future preflight uses no network, checks exact new mounted path/private
permissions and the named DATA pair; the collector's provider factory
can only load values AFTER local old-chain/clock verification.

The adapter rejects LIVE/generic broker keys, the old BTC-forward
credential variable names, PAPER order controls, a wrong volume and a
non-root Railway UID. There is no POST, account query, paper/live trading,
stock source, SIP purchase or promotion of the original BTC collector to
this new code. Rolling it out is a SEPARATE deliberate infrastructure
change; until then the only deployed prospective feed remains BTC.

## Testing

Synthetic offline tests cover:
- historical 72h*6 bootstrap -> 0 prospective;
- next hour exactly 6 prospective asset bars, 1 independent hour;
- duplicate/late/rolled-back time -> 0 provider factory calls;
- gap -> another baseline, old receipts preserved, new segment count 0;
- missing ETH source hour, wrong provider feed -> no new receipt;
- corrupted or insecure older receipt blocks new DATA requests;
- fixed separate volume/new DATA env names and no BTC/PAPER key fallback.

All continuous research/strategy evaluation remains OFFLINE; no
six-asset trading system exists just because six candles can be collected.
