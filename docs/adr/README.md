# Architecture decision records

Each file records one decision: the context, what was decided, what it costs,
and when to revisit it. New decisions get the next number; a reversed decision
is marked **Superseded** and links to its replacement rather than being edited
away.

| # | Decision | Status |
|---|---|---|
| [0001](0001-tenant-isolation-in-the-orm.md) | Enforce tenant isolation in ORM session hooks, not in views | Accepted |
| [0002](0002-fail-closed-and-404.md) | Fail closed with no scope; answer 404, not 403, across tenants | Accepted |
| [0003](0003-automatic-audit-log.md) | Write the audit log automatically from a flush hook | Accepted |
| [0004](0004-pure-compliance-rules.md) | Compliance rules as pure functions with one threshold file | Accepted |
| [0005](0005-server-rendered-flask-monolith.md) | Server-rendered Flask monolith, not a single-page app | Accepted |
| [0006](0006-precompiled-tailwind-and-design-tokens.md) | Precompiled Tailwind with semantic design tokens | Accepted |
| [0007](0007-staged-import-with-undo.md) | Spreadsheet import as a staged wizard with undo | Accepted |
| [0008](0008-motive-behind-a-client-boundary.md) | Motive behind a client boundary, mocked in demo mode | Accepted |
| [0009](0009-demo-hosting-via-quick-tunnel.md) | Demo hosting through a temporary Cloudflare quick tunnel | Accepted |
| [0010](0010-deterministic-seed-with-planted-scenario.md) | Deterministic seed data with a planted demo scenario | Accepted |

Template:

```markdown
# NNNN. Title

**Status:** Proposed | Accepted | Superseded by NNNN · **Date:** YYYY-MM-DD

## Context
## Decision
## Consequences
## Revisit when
```
