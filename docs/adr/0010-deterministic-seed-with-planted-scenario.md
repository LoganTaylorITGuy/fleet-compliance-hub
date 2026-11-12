# 0010. Deterministic seed data with a planted demo scenario

**Status:** Accepted · **Date:** 2026-11-12

## Context

A demo needs realistic data (a believable mix of red, yellow and green) and it
needs specific records at specific moments of the walkthrough ("this driver's
medical card expires in 12 days"). Purely random data can't promise the
second; hand-written fixtures don't scale to dozens of drivers and trucks.

## Decision

The `app/seed/` package separates the two:

- `plans.py`: the shape of the data set (tenants, sizes, courses).
- `generator.py`: bulk data from a **fixed random seed**, with dates relative
  to the seeding day so statuses stay current. Problems are assigned by quota
  (about 10% red, 18% yellow, rest green) rather than by independent random
  dates, which compound into an all-red fleet.
- `scenario.py`: the hand-placed records each walkthrough step relies on, and
  the demo logins.

All names, DOT/MC/CDL numbers and VINs are fictional.

## Consequences

- Same seed and date, same data: `test_seed_is_deterministic` checks it, and
  the 2026-11-12 restructuring was verified by comparing a full database dump
  before and after.
- Every walkthrough step is covered by a test in `test_seed.py`.
- Editing the generator changes the random sequence for every row after the
  edit; that is expected, and the planted scenario is unaffected.

## Revisit when

Demos are tailored per prospect (make the scenario a parameter).
