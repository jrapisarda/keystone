# Spike 01 — the Gate mechanism

**Question this spike answers:** *does the Stop-hook gate actually hold?* Can it
block a phase from closing while its verification is red, hand the failing item
back to the model, bound the rework, and release-and-escalate on exhaustion —
deterministically, with a counter that survives across turns?

**Answer: yes.** Proven by 13 passing tests (10 pure state-machine + 3 real
stdin/stdout hook-contract). This is the riskiest, most load-bearing piece of
Keystone (WORKFLOW_SPEC §2.2 "The Gate"), so it was built and proven in
isolation before any workflow scaffolding was laid on top.

## What it proves

| Behavior | Spec | Test |
|---|---|---|
| Normal turns are never gated (no active phase → allow) | §2.2 | `test_no_active_phase_allows` |
| Red within budget blocks and returns the failing item | §2.2 AC1 | `test_single_red_blocks_with_reason` |
| Rework is bounded; exhaustion escalates, never loops/ships red | §2.2 AC2 | `test_block_block_block_then_escalate` |
| Release-and-escalate is deadlock-safe (turn is released) | §2.3 | `test_block_block_block_then_escalate` |
| The counter is durable across successive Stop invocations | §2.2 | full-arc + hook escalate test |
| A resolved phase is not re-gated | §2.2 | `test_escalated_phase_is_not_regated` |
| Every gate stop + its resolution is captured as one incident | §2.2 step 8 | `test_red_then_green_...`, hook escalate |
| Missing verifier verdict counts as red, not pass (fail-closed) | Principle 1 | `test_missing_verdict_counts_as_red` |
| Real stdin→stdout Stop-hook contract (`decision:block`) | §6.2 | `test_gate_hook.py` |

## Design decisions worth knowing

- **`decide()` is pure** — `(state, verdict, now_ts) → Decision`. No I/O, no
  wall-clock, no globals. That is what makes the state machine exhaustively
  testable. All filesystem work is isolated in `state.py`.
- **The state model is the crux.** `.keystone/state.json` holds the active phase
  and a per-phase attempt counter. It persists between Stop invocations, so
  "attempts 1..N block, N+1 releases" is meaningful — the counter is not
  reconstructed from the transcript, it is durable.
- **The verifier is a seam, not a stub to throw away.** `state.load_verdict()`
  reads `.keystone/verdict.json` today so tests (and a live spike) can drive
  red/green. The real verifier subagent replaces *only that function* — nothing
  in the gate logic changes.
- **Fail-closed.** A phase active with no verdict is treated as red, never as a
  silent pass.
- **Append-only incident log.** A complete Incident Record (spec §3.1) is
  written *once, whole, at resolution* (green close or escalation). The
  in-flight incident is accumulated in state first, so `.incidents/log.jsonl`
  is never mutated.
- **Deadlock backstop.** Beyond the per-phase budget, the entrypoint honors
  `stop_hook_active` + a `HARD_CEILING` so a corrupted counter can never block
  forever.

## Run it

```bash
cd C:/testprojects/keystone
python spike/tests/test_gate_core.py     # pure state machine (zero deps)
python spike/tests/test_gate_hook.py     # real hook I/O via subprocess
# or, if pytest is available:
pytest spike
```

## Try it live (optional manual check)

The gate is wired in `.claude/settings.json`. To feel it in a real session:

```bash
mkdir -p .keystone
echo '{"active_phase":"demo","budget":2}'                > .keystone/state.json
echo '{"ok":false,"failing":"demo","detail":"still red"}' > .keystone/verdict.json
```

Now Claude cannot end its turn until you flip the verdict to `{"ok":true}` — or
until it burns the 2-attempt budget and the gate releases it as
escalated-pending-human. Delete `.keystone/` to disengage.

## Not in this spike (deliberately)

- The **real verifier subagent** (this uses the verdict-file seam).
- The **coverage ledger** and the `due`/`pending`/`green` cross-cutting logic.
- `/keystone` orchestration, the other hooks (SessionStart, PreToolUse config
  guard, smoke), and the consolidation engine.

Those build *on* this proven core — which was the point of proving it first.
