# 0001. Enforce tenant isolation in ORM session hooks, not in views

**Status:** Accepted · **Date:** 2026-11-10

## Context

Every carrier's drivers, trucks, tests and logs share one database. One
missing `WHERE tenant_id = ...` in any view, export, search or background job
would show one carrier's data to another: the single worst failure this
product can have. Filtering by hand in each view relies on every future change
remembering to do it.

## Decision

Tenant data models inherit `TenantScoped`. Two SQLAlchemy session events in
`app/tenancy.py` apply to all ORM work:

- `do_orm_execute` adds `with_loader_criteria(tenant_id == current)` to every
  select, update and delete, which also covers joins and relationship lazy
  loads.
- `before_flush` stamps new rows with the current tenant and raises
  `TenantViolation` for any write that would place a row in another tenant,
  move it, or link it to another tenant's parent record.

Views never filter by tenant. *Which areas* a role may use is a separate axis,
kept in one table in `app/permissions.py`.

## Consequences

- A new page, export or search is isolated by default; forgetting is not
  possible.
- Isolation is tested once, centrally: 62 tests run as their own required CI
  check, parameterized over every scoped model.
  `test_every_scoped_model_is_registered` fails if a new model skips them.
- Raw SQL (`text()`) and Core statements outside the ORM are **not** filtered.
  The app doesn't use them for tenant data, and
  `test_app_code_never_uses_unscoped_primary_key_lookups` guards the common
  slip (`session.get`).
- Cross-tenant reads need an explicit, greppable `with all_tenants():`.

## Revisit when

- More than one provider shares a deployment: add a provider-level scope so
  provider dashboards don't read through `all_tenants()` (see
  ARCHITECTURE.md, Known limitations).
- Scale or regulation calls for database-level enforcement too (PostgreSQL
  row-level security as a second layer under the ORM hooks).
