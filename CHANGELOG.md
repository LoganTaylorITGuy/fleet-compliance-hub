# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Flask app factory, environment-driven config, base layout with a responsive
  sidebar, skip link and demo disclaimer footer.
- Precompiled Tailwind CSS (no CDN at runtime), ruff, pytest with coverage,
  pip-audit, GitHub Actions CI and a pull request template.
- Data model for providers, tenants, users, drivers, driver files, drug and
  alcohol tests, training, vehicles, maintenance, HOS logs, DVIRs, imports,
  integrations and the audit log, with an initial Alembic migration.
- Tenant isolation layer (`app/tenancy.py`): every query and write on carrier
  data is filtered by tenant in one place, failing closed when no tenant is set.
- Tenant isolation test suite and CI jobs for isolation tests and migrations
  (fresh SQLite and PostgreSQL 16, upgrade, drift check, downgrade).
