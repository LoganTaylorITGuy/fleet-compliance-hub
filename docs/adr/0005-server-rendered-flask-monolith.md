# 0005. Server-rendered Flask monolith, not a single-page app

**Status:** Accepted · **Date:** 2026-11-10

## Context

The proof of concept needs multi-tenant data, roles, spreadsheet import and an
ELD integration, built and demonstrated in about a week, on a phone as well as
a laptop, and with a security posture a compliance business can trust. The
users are office staff and carrier owners, not power users of a rich client.

## Decision

- **Flask** with an app factory and one blueprint per feature area, Jinja
  templates, SQLAlchemy 2, Alembic, Flask-Login and Flask-WTF.
- **Server-rendered pages, progressively enhanced.** Every link and form works
  without JavaScript. `static/js/app.js` (vanilla, no build step) adds
  overlays, search-as-you-type, the theme switcher and keyboard shortcuts.
- One deployable app; no separate API service.

## Consequences

- Fewer moving parts: one language, one deploy, no client-side state to keep
  in sync with the server, and no API layer to secure separately.
- A strict Content Security Policy (`script-src 'self'`, no inline scripts) is
  easy to keep.
- Authorization and tenant isolation run on the server for every page; the
  browser never receives data it isn't allowed to see.
- Very interactive screens (drag-and-drop scheduling, live maps) would be
  harder in this model.

## Revisit when

A mobile app or third-party integrations need an API: add a versioned JSON API
over the same services and isolation hooks. A richer client (for example React
with TypeScript) can then be introduced screen by screen where it earns its
keep.
