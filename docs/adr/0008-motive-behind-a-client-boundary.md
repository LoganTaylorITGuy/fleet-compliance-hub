# 0008. Motive behind a client boundary, mocked in demo mode

**Status:** Accepted · **Date:** 2026-11-11

## Context

Hours of service, DVIRs and odometers should come from the carrier's ELD
(Motive is the example) rather than be typed in. The proof of concept has no
Motive account, and inventing API details would be worse than leaving them
clearly unfinished.

## Decision

- `integrations/motive.py` defines `MotiveClient`, the only code that would
  talk to Motive. In demo mode it returns generated data shaped like a typical
  paginated REST response. Every unverified endpoint, field and auth detail is
  marked `TODO` in the code.
- `integrations/sync.py` is the incremental sync: HOS from the day after the
  newest synced log through today (today's in-progress log is refreshed), DVIRs
  for the last two days, and current odometers. **Past days are never
  rewritten.** Records match local drivers and units through
  `app/identifiers.py`, the same rule the spreadsheet import uses.
- The API key comes from the environment only; the database stores at most a
  reference (`IntegrationConnection.api_key_ref`).

## Consequences

- Swapping in the real API changes one module; sync logic, pages and tests stay.
- The demo can show "Sync now" safely and repeatedly.
- Nothing in the code claims to match Motive's real API.

## Revisit when

A real Motive account is available: verify every TODO against Motive's
developer documentation, add retries with backoff and rate limiting, store
per-carrier keys in a secrets manager, and run sync on a schedule.
