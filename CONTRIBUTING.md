# Contributing

## Workflow

1. Branch from `main` (`feat/...`, `fix/...`, `docs/...`). `main` is protected:
   changes land by pull request only, and CI must pass before merging.
2. Keep each pull request to one feature or fix, and fill in the testing checklist.
3. Run the checks locally before pushing:

   ```bash
   ruff check . && ruff format --check .
   pytest
   ```

4. Any change to models needs an Alembic migration:

   ```bash
   flask db migrate -m "describe the change"
   flask db upgrade
   ```

## Ground rules

- **Know where a change belongs.** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
  lists the one place each rule lives (tenancy, permissions, audit, compliance
  rules, identifiers). Feature packages don't import each other;
  `tests/test_architecture.py` enforces it.
- **Record decisions.** A change to how the system is built (a new dependency,
  storage, hosting, a security boundary) gets an ADR in [docs/adr/](docs/adr/).
  Don't edit an accepted ADR to reverse it; supersede it with a new one.
- **Every module says what it is for.** Lint requires a module or package
  docstring (ruff D100/D104) and keeps function complexity in check (C901).

- **Tenant isolation is not optional.** Every compliance table carries a
  `tenant_id`, and queries are filtered in one place (`app/tenancy.py`). Do not
  bypass it in a view. If a new model holds carrier data, it inherits
  `TenantScoped` and gets an isolation test.
- **No secrets in the repo.** Configuration comes from environment variables;
  see `.env.example`.
- **Mock data only.** Names, DOT/MC numbers, CDL numbers and VINs are fictional.
- **Colors come from design tokens** (`text-ink`, `text-muted`, `bg-danger-soft`,
  `glass`...) defined in `app/static/css/input.css`, never raw palette classes
  like `text-slate-600`, so every page works in light and dark.
  `tests/test_design_tokens.py` fails if a token pair drops below WCAG AA.
- **Accessibility:** WCAG 2.1 AA. Status is never shown by color alone; tables use
  `<th scope>`; every form control has a label.

## Releases

- Merges to `main` are the staging candidate.
- Production releases are tagged (`vX.Y.Z`) after the staging build is checked,
  and the CHANGELOG entry moves from Unreleased to the version.

## Styles

Tailwind is compiled ahead of time into `app/static/css/app.css`. After changing
templates, run `npm install` once and then `npm run build:css`, and commit the
rebuilt file.
