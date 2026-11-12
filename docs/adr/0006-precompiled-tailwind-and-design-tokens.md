# 0006. Precompiled Tailwind with semantic design tokens

**Status:** Accepted · **Date:** 2026-11-11

## Context

The UI has to look professional and custom in both light and dark themes,
including a frosted "liquid glass" style, and stay WCAG 2.1 AA. Loading
Tailwind from its CDN at runtime would add a third-party script (weakening the
CSP), break offline demos, and ship an unoptimized stylesheet.

## Decision

- Tailwind is compiled ahead of time (`npm run build:css`) into
  `static/css/app.css`, which is committed. Nothing loads from a CDN.
- Colors are **semantic tokens** (`text-ink`, `text-muted`, `bg-danger-soft`,
  `glass`) defined once in `static/css/input.css` with light and dark values.
  Templates never use raw palette classes like `text-slate-600`.
- `tests/test_design_tokens.py` computes WCAG contrast for every token pair in
  both themes, composited over the translucent glass, and fails below AA.
- A reduced-transparency fallback is provided for users who ask for it.

## Consequences

- Works offline and under a strict CSP.
- A theme change is a token change, not a hunt through templates.
- Accessibility can't silently regress.
- Contributors must rebuild and commit the CSS after template changes
  (documented in CONTRIBUTING.md).

## Revisit when

A shared design system across several products is needed (publish the tokens
as a package).
