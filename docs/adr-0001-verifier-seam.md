# ADR-0001: The verifier reaches the gate through a swappable verdict-provider seam

**Status:** Accepted · **Date:** 2026-07-19 · **Deciders:** Jonathan (stakeholder), Claude

## Context

The Stop-hook gate (proven in `spike/`) needs a verdict — `{ok, failing, detail}`
— to decide block / release / escalate. That verdict must come from the
**independent verifier subagent** (spec §6.1), never from the coder, and the gate
must **fail closed** when a verdict can't be produced (Principle 1).

*How* a Stop hook actually invokes a subagent is the one piece of the mechanism we
could not confirm from documentation alone. Two candidate mechanisms exist:

1. A native Stop hook of `type: "agent"` — cleaner, but flagged **experimental**
   (behavior may change).
2. A `type: "command"` hook that shells out to the Claude CLI (`claude -p …`) —
   heavier and nested, but **stable today**.

Betting the architecture on (1) before it is verified would be fragile; hard-coding
(2) everywhere would make a future migration to the native handler invasive.

## Decision

Put a **verdict-provider interface** between the gate and the verifier. The gate
consumes a verdict dict and does not care how it was produced. Two providers ship:

- **StaticFileProvider** — reads `.keystone/verdict.json`. Used by tests, manual
  spikes, and any setup where the verdict is pre-supplied. Zero cost, hermetic.
- **SubagentProvider** — invokes the verifier via an **injectable runner**
  (default: the Claude CLI), parses its structured verdict tolerantly (raw JSON,
  fenced blocks, prose-wrapped, or the `--output-format json` envelope), and
  **fails closed** (red) on any non-zero exit, unparseable output, or exception.

Selected by env `KEYSTONE_VERIFIER` (`static` | `subagent`; default `static`).

The single point of live uncertainty — the exact CLI invocation that forces the
`verifier` agent — is isolated to one function (`verify._default_runner`). Swapping
to the native `type: "agent"` handler when it stabilises touches that seam and
nothing else.

## Consequences

- **Positive:** every previously-proven test stays valid (static is the default);
  the risky part is one correctable function; fail-closed is enforced and tested
  (15 hermetic tests, no live session needed); migration path to native is a seam,
  not a rewrite (Principle 5, "mirror native, adopt later").
- **Negative / open:** the *live* behaviour of `SubagentProvider._default_runner`
  (does the CLI run the intended agent and return parseable JSON here?) is
  confirmable only against a real session — tracked as the one remaining manual
  verification. The command mechanism is also nested and heavier than the native
  handler; acceptable because the gate runs the verifier at most `budget + 1`
  times per phase, not on every turn.
- **Cost bound:** the verifier engages only while a phase is open; normal turns
  pass through at zero cost.
