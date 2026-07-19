---
name: test-conventions
description: How Keystone tests are written — behavior-level, traceable to a ledger sub-obligation, and designed to catch stubs. Preloaded into the test-writer. Recall project-specific framework gotchas from the memory store on top of these.
---

# Test conventions

The test is the executable form of an acceptance criterion. It exists before the
code, and it is the thing that must not bend to make code pass.

## Non-negotiables
- **Trace every test to its obligation.** Name the criterion / sub-obligation id in
  the test name or a comment, so the verifier and the ledger can line up.
- **Behavior, not implementation.** Assert observable outcomes, not internal calls
  — unless the contract *is* the call. Implementation-coupled tests pass a rewrite
  that breaks behavior, and fail a refactor that doesn't. Both are wrong.
- **Currently red, for the right reason.** With no implementation yet, a new test
  must fail because the behavior is absent — not from an import or harness error.
  Confirm the failure reason before moving on.

## Catch the stub — the class of bug the gate exists for
For each obligation, add the test a **stub or over-fit implementation would pass**:
- A criterion of the form "output varies by seed" gets a fixed-seed assertion
  **paired with** a distinct-outputs assertion — so over-satisfying one requirement
  can't hide breaking another.
- A "populates X" criterion asserts X is actually non-empty and correct after the
  action, not merely that the action returned without error.
- Negative and degenerate inputs are tested, not just the happy path.

## Interactions
Where two requirements meet, test the combination — the class where each side
passes alone but together they fail. This is where cross-cutting criteria break.

## Hygiene
- Deterministic: inject clocks/seeds/uuids; never assert on wall-clock or random
  values. Hermetic: no network or shared mutable state between tests.
- Recall the project's framework quirks from the store (mock patterns, async
  traps, fixture scoping, encoding) and match the existing test idiom rather than
  importing your own.
