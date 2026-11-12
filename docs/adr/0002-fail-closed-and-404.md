# 0002. Fail closed with no scope; answer 404, not 403, across tenants

**Status:** Accepted · **Date:** 2026-11-10

## Context

Two questions every multi-tenant app must answer: what happens when code runs
without a tenant set (a bug, a new job, a forgotten context), and what a user
sees when they guess another carrier's record ID in a URL.

## Decision

- **No scope means no access.** With no tenant scope set, scoped queries match
  nothing (filtered on an impossible tenant id) and writes raise. Scope only
  comes from the request hook (`resolve_scope`) or an explicit
  `tenant_scope()` / `all_tenants()` block.
- **Another tenant's record is "not found".** Lookups go through the scoped
  query, so a guessed ID returns **404**, never 403. A 403 would confirm that
  the record exists.

## Consequences

- A scoping bug shows an empty page or an error, never another carrier's
  data. That is the right way to fail for compliance records.
- Provider users must pick a carrier before carrier pages work; the app sends
  them to the picker instead of guessing.
- Tests cover both: `test_no_scope_sees_nothing`, `test_writes_without_scope_are_refused`,
  and `test_guessing_another_tenants_id_returns_404` for every scoped model.

## Revisit when

Not expected to change.
