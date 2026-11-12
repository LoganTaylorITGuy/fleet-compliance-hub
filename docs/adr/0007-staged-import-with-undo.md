# 0007. Spreadsheet import as a staged wizard with undo

**Status:** Accepted · **Date:** 2026-11-10

## Context

Carriers' existing records live in messy spreadsheets: inconsistent headers,
dates in five formats, "TR-501" vs "tr 501", names in one column. A one-shot
"upload and hope" import either rejects whole files or writes bad data, and a
bad import into compliance records is hard to clean up.

## Decision

A four-step wizard, implemented as a small pipeline in `app/imports/`:

1. **Upload:** `parsing.read_table` reads every cell as text (nothing guessed
   yet) and `staging` parks the file as JSON on disk under a random token,
   bound to the uploading tenant and user.
2. **Map:** `specs.suggest_mapping` proposes column matches from synonyms;
   the user confirms, and can save the mapping as a template.
3. **Review:** `engine.build_rows` parses each cell, `resolvers` match rows to
   existing records (add or update) and flag duplicates in the file. Errors are
   shown per cell; the user fixes or skips rows and rechecks.
4. **Commit:** one transaction, one audit summary, and a change list saved on
   `ImportRun`, so the latest import can be **undone**.

Blank cells never erase existing data on update.

## Consequences

- Users fix problems in place instead of editing the spreadsheet and starting
  over.
- A token from another carrier's session can't load the staged file.
- Adding an import type takes three entries (spec, resolver, write fields);
  `test_every_import_type_is_fully_registered` enforces it.
- Staged files are on local disk, so multiple app servers would need shared
  storage.

## Revisit when

Imports exceed what fits in one request (move commit to a background job), or
the app runs on more than one server.
