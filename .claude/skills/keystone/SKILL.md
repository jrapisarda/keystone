---
name: keystone
description: Run the Keystone gated structural-verification workflow on an approved requirements document. Invoke as `/keystone <path-to-requirements-doc>`. Sequences Tier 1 (project-init — synthesize, research, architect, build the coverage ledger, get approval) and Tier 2 (per-phase build loop under the Stop-hook gate).
---

# Keystone — the orchestrating procedure

## Which requirements doc? (bind it explicitly)

A project has **one full requirements doc per major feature** (e.g.
`docs/aurelia-astrology-requirements.md`). A Keystone run is bound to exactly one:

- **Explicit (preferred):** the argument to `/keystone` IS the doc path. Use it.
- **Discovery (fallback):** if no path was given, list `docs/*-requirements.md`
  whose `Status:` is `Approved for Implementation`. If exactly one, confirm it;
  if several, **ask which — never silently pick**.
- **Durable:** record the choice in `.keystone/ledger.json` as `source_spec` (the
  path) and `feature` (a slug derived from the filename, e.g. `aurelia-astrology`).
  That binds the whole run — and every incident it produces — to this doc, so a
  resumed session and the memory store both know which feature they're in.
- **One active feature at a time.** When a feature's ledger is all-green and signed
  off, run `cli.py archive` — it files the ledger under `archive/<feature>.ledger.json`
  and clears the active run so the next `/keystone <next-doc>` starts clean.

You are the **orchestrator** (the main session). You hold the plan, the coverage
ledger, and the test surface continuously — that state must not be severed, which
is why you are not a subagent. You delegate reads to the six specialists; you own
every write (code, ledger, commit, memory). Reads fan out; writes centralize.

The gate enforces "done" for you. Your job is to make its judgement *possible*: a
complete ledger, obligations projected into state, tests that actually encode the
criteria.

## Tier 1 — Project initiation (runs once)

1. **Recall** — `memory_search` the domain/stack for conventions, gotchas, prior
   decisions. This warms the whole run.
2. **Synthesize** — delegate to **requirements-synthesizer**: returns the digest +
   the atomic acceptance-criteria list. Read-only; you receive the list.
3. **Research (conditional)** — for genuine unknowns only, delegate to
   **researcher** → cited briefs in `docs/`. Skip if nothing is truly unknown.
4. **Architect** — delegate to **architect**: returns the architectural-LAYER phase
   decomposition + inter-phase dependency graph; writes ADRs to `docs/`.
5. **Build the coverage ledger** — decompose every acceptance criterion into
   single-owner sub-obligations, each assigned to exactly one phase. Write the
   machine-readable ledger to `.keystone/ledger.json`:
   ```json
   { "feature": "aurelia-astrology",
     "source_spec": "docs/aurelia-astrology-requirements.md",
     "phase_order": ["P1","P2",...], "budget": 3, "completed_phases": [],
     "integration_verified": [],
     "criteria": [ {"id","text","e2e_test"?,
       "sub_obligations":[{"id","owning_phase","proving_test","text"}]} ] }
   ```
   Then render the human table into `IMPLEMENTATION_PLAN.md` (two-tier plan +
   ledger). Keep the two in sync — JSON drives the gate, the table is for review.
6. **Validate + approve** — run `python .claude/keystone_gate/cli.py --root . status`.
   Any coverage problem (an unowned criterion, a sub-obligation with no phase or no
   proving test) is a **hard stop** — fix before proceeding. Then present the
   decomposition + ledger to the stakeholder. **This is the one up-front approval
   gate.** Do not start a phase until it is approved.

## Tier 2 — Per-phase loop (once per phase, in dependency order)

For each phase whose dependencies are complete:

1. **Open the phase** — `python .claude/keystone_gate/cli.py --root . open-phase <P>`.
   This projects the phase's owned sub-obligations **and** any cross-cutting
   criterion whose completing phase is `<P>` (its end-to-end check) into
   `.keystone/state.json`, where the verifier reads them. From now the Stop-hook
   gate is armed for this phase.
2. **Write tests** — delegate to **test-writer**: behavior tests from those
   obligations, incl. negatives / degenerate / stub-catchers. Confirm they are red
   for the right reason.
3. **Code** — implement to satisfy the tests. For a large build, delegate to the tool-scoped **implementer** agent (never `general-purpose` — it can write the memory store directly, bypassing gated consolidation; the implementer stages learnings to `.keystone/learnings.jsonl` instead). Never weaken a test to pass.
4. **Test → refactor → test** — the proven sandwich; re-test after refactor.
5. **The gate closes the phase for you.** When you end your turn, the Stop hook
   invokes the independent **verifier** against the phase's obligations:
   - red within budget → the turn is blocked and the failing item handed back; do
     the bounded rework.
   - budget exhausted → the turn is released and the phase marked
     `escalated-pending-human`; surface it, don't fake it.
   - green → proceed to close.
6. **Close the phase** — once green, commit the code, then
   `cli.py --root . close-phase <P> [--integration <AC-id> ...]` (pass the ids of
   any cross-cutting criteria whose end-to-end check the verifier confirmed this
   phase). This advances the ledger and opens the next eligible phase.

The incident log (`.incidents/log.jsonl`) captures every gate stop + resolution
automatically — you don't manage it.

## Consolidation (batch — project close or every N phases)

Delegate to **synthesizer**: non-destructive dedup/score/route over the incident
log + store → curated memories (project auto-applied; global-promotion candidates
held for stakeholder review). Never inside the build loop.

## Invariants you must not break

- Enforcement is the hook, not your good intentions — never edit tests or stub
  behavior to clear a red gate. That is exactly what the verifier (no edit tools)
  and `fix_method=suspect` scoring exist to catch.
- Research writes to `docs/`, never to memory. Only post-gate learnings, in batch
  consolidation, reach the store.
- An unowned criterion is a Tier-1 failure, surfaced — never silently dropped.
