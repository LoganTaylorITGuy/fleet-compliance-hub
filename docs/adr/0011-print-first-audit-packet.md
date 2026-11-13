# 0011. Driver audit packet as a print-first page, logged on every pull

**Status:** Accepted · **Date:** 2026-11-13

## Context

A compliance provider's value is keeping carriers ready for a DOT audit. The
driver page already shows the whole qualification file, but an auditor wants a
document: one driver, everything in one place, dated, and traceable to whoever
produced it. Two questions came up: how to make the document (a PDF from the
server, or a page the browser prints), and whether to log a read.

## Decision

- **A print-first HTML page,** `/drivers/<id>/packet`, not a server-generated
  PDF. The browser's print dialog prints it or saves it as a PDF on every
  platform, including iPhone. Print styles in `input.css` hide the app's
  header, bottom bar and toolbar, and pin the color tokens to the light theme's
  values, so a packet printed from dark mode is still dark text on white paper.
  `tests/test_print_styles.py` keeps those pinned values equal to `:root`.
- **The same data as the driver page.** Both views build their data in one
  helper (`_driver_file` in `app/drivers/routes.py`), and the checklist's
  due-date status uses the compliance rules' own `date_finding`, so the packet
  can't disagree with the dashboards.
- **Every pull is logged.** Opening a packet writes an audit entry (`action =
  "packet"`, against the driver). The entry's id is printed on the packet as its
  reference, with who generated it and when (US Central, 24-hour). This is the
  one GET that writes. It writes only to the audit log, never to tenant data.
- **Same access as the driver page:** `require_view("drivers")` and a tenant
  scope. Another carrier's driver id is a 404 (ADR 0002), and refused requests
  log nothing.

## Consequences

- No new dependency. A server-side PDF library such as WeasyPrint needs system
  libraries (Pango, Cairo) on every machine and in CI; this adds none.
- Page breaks, margins and headers are up to each browser, within the rules in
  the print stylesheet. The output is good, but it isn't pixel-identical
  across browsers.
- The audit log grows with each view of a packet, not only with changes.
  That's intended: who pulled a driver's file is itself a compliance record.
- A missing checklist item shows red on the packet (as on the driver page), but
  the compliance rules don't yet count missing file items. A driver can read
  "Current" overall with a red checklist line.

## Revisit when

- Packets need to be emailed or archived without a person in the loop. Render
  the same template to PDF on the server then.
- The rules start counting missing file items. Change them in
  `compliance/rules.py` and the packet follows automatically.
