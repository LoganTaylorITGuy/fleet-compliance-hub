# 0003. Write the audit log automatically from a flush hook

**Status:** Accepted · **Date:** 2026-11-10

## Context

Compliance records get audited by regulators ("who changed this medical card
date, and when?"). An audit trail that depends on each view calling a logging
function will have gaps.

## Decision

An `after_flush` session hook in `app/audit/__init__.py` writes an `AuditLog`
row for every insert, update and delete of tenant data, with before and after
values for the changed columns and the current user. It inserts on the
flush's own connection, so the audit row commits or rolls back with the change
it describes.

Bulk jobs (spreadsheet import, Motive sync, seeding) wrap their work in
`audit_suppressed()` and write **one** summary entry with `record()`.

## Consequences

- Every edit made through the app is audited without the view doing anything.
- No-op updates are not logged (only changed columns are compared).
- A 500-row import shows as one readable entry ("Drivers import from x.xlsx:
  6 added, 0 updated, 3 skipped"), and its row-level detail lives in
  `ImportRun.changes`, which is also what makes undo possible.
- The audit table is itself tenant scoped, so carriers see only their own
  history.

## Revisit when

Audit records must be tamper-evident (append-only storage or hash chaining),
or retained outside the application database.
