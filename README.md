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
├── agents/                 # 6 thin subagents            (next)
├── skills/                 # /keystone + preloaded skills (next)
└── rules/                  # path-scoped instructions     (next)
docs/                       # spec, ADRs, research briefs
spike/                      # gate spike + its proof tests
.incidents/log.jsonl        # append-only incident log (synthesizer input)
```

## Build order

1. **Gate spike** — block / release / escalate + durable counter + incident
   capture. ✅ *done, proven*
2. Incident schema + append path. ✅ *falls out of the spike*
3. Six thin subagents (fixed-harness, Opus, tool-scoped).
4. Coverage ledger + `/keystone` orchestration.
5. Consolidation engine + always-on tiering (in `claude-memory-system`).
6. Dogfood on a real feature.

## Run the proof

```bash
python spike/tests/test_gate_core.py
python spike/tests/test_gate_hook.py
```
