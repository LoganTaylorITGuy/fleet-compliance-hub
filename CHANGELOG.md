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
- Login and logout (Flask-Login, hashed passwords, CSRF on every form), four
  roles with a single permission table, provider tenant switcher, and a
  one-click demo login switcher that only exists when `DEMO_MODE=true`.
- Automatic audit log of every create, update and delete on carrier data, with
  before/after values, plus a filterable Audit log page (Provider Admins see all
  carriers; Carrier Admins see their own).
- `python seed.py` demo data: three fictional carriers (3, 8 and 15 drivers) and
  an academy fleet with students, 30 days of HOS logs, DVIRs, maintenance, tests
  and training, users for every role, and planted records for each demo step.
  Deterministic, dated relative to today, refuses to run in production.
- Compliance status rules (`app/compliance/`): red for anything expired, a failed
  test, an unresolved DVIR defect or an HOS violation in the last 7 days; yellow
  for anything due within 30 days; green otherwise. Thresholds live in
  `app/compliance/thresholds.py`. Unit tests cover every rule and boundary.
- Provider dashboard (every carrier, ranked most urgent first, with totals and
  one-click Open) and carrier dashboard (driver and unit counts, Needs action
  now, Expiring in 30 days, per-driver and per-unit status). Status badges use
  text and shapes, not color alone; layouts adapt to phone width.
- Drivers (search, status filter, detail with qualification file checklist,
  tests, training, last 7 days of hours, audited edits), Fleet (type and status
  filters, unit detail with DVIRs and maintenance, add maintenance, complete a
  shop repair, which resolves its DVIR defect), Hours of Service (7-day grid with
  violations highlighted, labeled as synced from Motive (mock)) and Training
  (academy student progress, mark course complete, certification expirations).
- Spreadsheet import for drivers, vehicles, training, drug tests and
  maintenance: upload .xlsx/.csv, preview, column matching suggested from
  headers, saved mapping templates, validation (dates in many formats, required
  fields, bad values, duplicates in the file), fix or skip rows in place, then
  import with history and undo of the last import.
- Export to Excel on Drivers, Fleet, Hours of Service, Training and Audit log,
  with spreadsheet formula injection escaped.
- Messy sample spreadsheets in `samples/` and a script to regenerate them.
- Motive ELD stub (`app/integrations/motive.py`): `get_drivers`, `get_vehicles`,
  `get_hos_logs`, `get_dvirs` return REST-shaped mock data in demo mode; live
  calls are not implemented and endpoints are marked TODO pending Motive's docs.
- Integrations page with "Connected (demo mode)" and Sync now: an incremental,
  idempotent sync of today's hours, recent DVIRs and odometers that never
  rewrites past days.
- Design system: color tokens (CSS variables) with light and dark themes; dark
  follows the device by default, with a one-click toggle in the header and an
  Auto/Light/Dark choice in the account menu (saved, no flash on load).
- Liquid glass look: frosted translucent panels with a specular highlight over a
  soft gradient backdrop, falling back to solid panels when the OS asks for
  reduced transparency. Contrast is checked by tests in both themes.
- Full-width layout: a header (carrier switcher, theme toggle, help, account
  menu) and an always-available bottom bar with a Menu button (navigation
  overlay with every page and the carrier switcher) and a search bar that
  finds pages, drivers and units as you type (Cmd/Ctrl+K or /).
- Search suggestions: clicking into the empty search bar shows recently viewed
  pages, drivers and units (kept in the browser per user and per carrier,
  cleared on log out); typing suggests pages ranked by name and keywords
  ("dvir" finds Fleet, "logs" finds Hours of Service).

### Fixed

- Account and carrier menus in the header weren't actually blurred: an element
  with backdrop-filter becomes the backdrop for its children, so the header's
  own glass blocked theirs. The header's frosted layer now sits on a
  pseudo-element, and menus use a more opaque, more blurred popover glass.
- The bottom pill now has a defined edge (hairline ring, crisper rim, deeper
  shadow) so it stands out from busy pages in both themes.
- Screen-reader-only text inside scrolling tables made whole pages scroll
  sideways on phones.

### Changed

- Replaced the left sidebar with the header and bottom bar, so pages use the
  full screen width.
- Seed data assigns red/yellow quotas per tenant instead of random dates per
  item, which had compounded into a mostly red fleet.
