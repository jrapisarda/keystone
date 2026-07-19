# ADR-0002: Smoke/e2e criteria never auto-green from unit phases

**Status:** Accepted · **Date:** 2026-07-19 · **Deciders:** Jonathan (stakeholder), Claude

## Context

The first real Keystone project (aurelia-astrology) closed all 7 phases with **84/84
ledger criteria green and 925 unit tests passing** — yet when the stakeholder ran the
app, two things were broken:

1. **No usable UI.** The birth-data journey (form → chart → reading → wheel) had logic,
   an API route, and tests, but was never assembled into a page a user could reach.
2. **The existing save 500'd.** A schema change generated a migration that the unit
   tests applied to a fresh pglite DB — but it was never applied to the real dev DB,
   so Drizzle queried a column the database lacked.

Both are the **real-build smoke surface** (AC-XCUT-4..9). Two design faults let them
reach the stakeholder instead of the gate:

- The smoke criteria were modeled as single-owner criteria of a unit phase, so the
  ledger **auto-greened them the moment that phase's unit tests passed** (`criterion_status`
  returned green on phase completion for non-cross-cutting criteria).
- The real-build smoke was **deferred to "manual UAT"** and never actually run.

Unit tests run against mocks and pglite; they structurally cannot prove the build boots,
that a page renders, or that the real database has the migration. Green unit tests are
therefore not evidence for a runtime claim.

## Decision

**A criterion whose truth is only knowable by the running system is tagged `"smoke": true`
and can never auto-green from phase completion.** It greens only via a separate
`smoke_verified` set — exactly mirroring the `integration_verified` gate for cross-cutting
criteria, but for the real-build modality. A criterion that is both cross-cutting and smoke
requires BOTH gates.

The **real-build smoke gate** (skill §"real-build smoke gate", run by the verifier) must:
boot the production build, **run migrations against a real DB**, drive the specced journeys
against the running app (Playwright + a real-API round-trip), then `cli.py smoke-verify <ids>`
only for what genuinely passed. `cli.py status` surfaces the rest as `smoke_pending`, and
**`all_green` is false while any smoke criterion is unverified** — so a feature cannot be
called done on unit tests alone.

## Consequences

- **Positive:** the ledger can no longer report "done" for a non-booting or headless app;
  the real DB + real UI are exercised before close; manual-only checks are surfaced, not
  faked. Enforced in `ledger.criterion_status`/`ledger_summary` and `cli.smoke-verify`,
  with tests.
- **Negative / cost:** the smoke gate needs a real DB + a browser driver, so it's heavier
  than unit tests and can't run fully headless everywhere. Genuinely un-automatable pieces
  remain manual and stakeholder-surfaced — but they are now *tracked as pending*, not
  silently green.
- **Migration provenance corollary:** "the tests pass against pglite" is not "the running
  DB is migrated." The smoke gate owns applying migrations where the app actually runs.
