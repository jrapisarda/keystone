# Keystone

A gated, structural-verification development workflow for Claude Code that makes
**"done" a verified property, not a self-reported claim.** It runs a capable
coding agent through architecturally-scoped phases against an approved coverage
ledger, and blocks each phase from closing until an independent verifier
confirms — via tests derived from the requirements — that every acceptance
criterion the phase owns is actually satisfied.

See [`docs/WORKFLOW_SPEC.md`](docs/WORKFLOW_SPEC.md) for the full specification.

> **Status:** early build. The load-bearing core — the Stop-hook gate — is
> proven in [`spike/`](spike/README.md) (13 passing tests). The workflow is
> being built on top of it, gate-first.

## How it relates to the memory system

Keystone is the **workflow**; the [distributed memory
system](../claude-memory-system) is the **substrate** it recalls from and writes
learnings back to. They are separate repos that meet at one seam: Keystone's
consolidation pass writes validated learnings via the memory server's
`memory_write`. The batch consolidation engine itself lives in
`claude-memory-system` (memory-native Python).

## Layout

```
.claude/                    # the portable tree — installs into any project
├── settings.json           # hook wiring (the gate)
├── hooks/stop_gate.py      # Stop-hook entrypoint
├── keystone_gate/          # the gate package (pure core + fs I/O)
├── keystone_gate/          # core (gate) + verify (seam) + ledger + cli
├── agents/                 # 6 thin subagents (verifier, architect, …)
├── skills/                 # /keystone + incident-schema/adr-format/test-conventions
└── rules/                  # path-scoped instructions     (next)
docs/                       # spec, ADRs, research briefs
spike/                      # proof tests (46 across 5 suites)
.keystone/                  # runtime: ledger.json + state.json (per project)
.incidents/log.jsonl        # append-only incident log (synthesizer input)
```

## Build order

1. **Gate spike** — block / release / escalate + durable counter + incident
   capture. ✅ *done, proven*
2. Incident schema + append path. ✅ *done (skill + gate emit the same record)*
3. Six thin subagents (fixed-harness, Opus, tool-scoped). ✅ *done*
4. Verifier↔gate wiring (swappable verdict-provider seam). ✅ *done (ADR-0001)*
5. Coverage ledger + `/keystone` orchestration + ledger CLI + skills. ✅ *done*
6. Enforcement hook map — config-conformance guard (PreToolUse), SessionStart
   ledger injection, PostToolUse formatter, pre-commit close-integrity, smoke
   runner. ✅ *done*
7. Consolidation engine + always-on tiering (in `claude-memory-system`). *next*
8. Dogfood on the astrology/natal-chart feature — and there, confirm the live
   verifier-subagent runner (the one open item in ADR-0001).

## Run the proof

```bash
python spike/tests/test_gate_core.py
python spike/tests/test_gate_hook.py
```
