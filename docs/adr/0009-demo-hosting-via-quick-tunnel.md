# 0009. Demo hosting through a temporary Cloudflare quick tunnel

**Status:** Accepted · **Date:** 2026-11-11

## Context

The prospect should be able to open the live demo on their own phone during
the meeting. Standing up permanent hosting for a proof of concept adds cost
and a public attack surface that would exist long after the demo.

## Decision

`scripts/demo-tunnel.sh`:

- serves the app with **waitress** (a production WSGI server, not the Flask
  dev server) bound to `127.0.0.1` only, so nothing is exposed on the local
  network;
- opens a Cloudflare quick tunnel (no account; a new random
  `*.trycloudflare.com` HTTPS address each run) and prints a QR code;
- sets secure cookies, proxy trust and a fresh random secret key for that run
  only;
- tears everything down on Ctrl+C, TERM or HUP, and a watchdog closes the
  tunnel within seconds even if the script is killed with `kill -9`.

It runs only for the length of a demo. All data is fictional.

## Consequences

- Zero hosting cost and no standing public endpoint.
- The address changes every run, so a link can't be reused later.
- A new hostname can take a minute to resolve; open it on your own phone a
  few minutes before sharing the QR code.
- Not a deployment: no uptime, backups or monitoring.

## Revisit when

A pilot with real users starts: deploy staging and production environments
from tagged releases with managed PostgreSQL (see README, "What this would
look like for real").
