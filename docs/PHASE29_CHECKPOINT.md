# Phase 29 checkpoint — multi-market foundation

Saved before owner shuts down Mac.

## Persisted on this branch
- Unified capability model for crypto, U.S. equities, and Kalshi.
- Strict Kalshi public/demo GET-only request builder.
- Long-horizon historical chunk planner for crypto and U.S. equities.
- Tests for all three additions.
- Existing stock historical IEX/XNYS audit modules remain on main and are not overwritten.

## Safety state
- Paper order submission remains disabled.
- Live order submission remains disabled.
- No live-money credentials or order permissions were added.
- No new paid Railway resources were created.
- Existing crypto Railway collector remains separate and unchanged.

## Current resume point
The latest Phase 29 CI run fails because the existing private operator dashboard imports the older market-capability interface. Resume by making the capability module backward-compatible with the dashboard (or updating the dashboard and its tests together), then rerun the full Python 3.11/3.12 safety suite. Do not merge PR #51 until CI is green.

After CI passes:
1. Merge Phase 29.
2. Build the unified dashboard/readiness view.
3. Extend historical-data workflows to longer bounded crypto/equity horizons.
4. Add Kalshi historical/resolved-market research ingestion.
5. Add separate forward/paper validation lanes for equities and Kalshi.
6. Keep real-money execution locked until each market passes its own gates and owner authorization.
