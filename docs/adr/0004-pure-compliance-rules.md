# 0004. Compliance rules as pure functions with one threshold file

**Status:** Accepted · **Date:** 2026-11-10

## Context

Red / yellow / green status is the product's core value, and the rules will
change: a compliance professional will review them, and regulations move. The
rules need to be easy to read, easy to test, and impossible to apply
differently on two pages.

## Decision

- `compliance/rules.py` holds pure functions: model objects and a `today` date
  in, a `Status` with `Finding`s out. No Flask, no database.
- Every number (30-day warning window, 7-day HOS lookback, 365-day inspection
  interval, which test results count as failed) lives in
  `compliance/thresholds.py`.
- `compliance/service.py` does the loading: a fixed number of queries with
  `selectinload`, then the rules. Dashboards, the driver and fleet pages, and
  exports all use it.
- "Today" comes from `app/clock.py` in US Central time, so a UTC server
  doesn't flip records to expired at 18:00 local.

## Consequences

- Each rule is unit tested with plain objects and fixed dates.
- Changing a threshold is a one-line, reviewable diff.
- Status is identical everywhere it appears.
- `tests/test_architecture.py` keeps `rules.py` free of Flask and the database.

## Revisit when

Carriers need different thresholds (per-tenant settings), or rules need to be
edited by non-developers.
