---
name: adr-format
description: The Architecture Decision Record format for docs/. Preloaded into the architect. One decision per file, so a future maintainer learns WHY, not just what.
---

# ADR format

One decision per file: `docs/adr-NNNN-<slug>.md` (zero-padded, monotonic). An ADR
records a decision that was hard to make and would be expensive to silently
reverse — not every choice, just the load-bearing ones.

```markdown
# ADR-NNNN: <the decision, stated as a fact>

**Status:** Proposed | Accepted | Superseded by ADR-MMMM · **Date:** YYYY-MM-DD · **Deciders:** <names>

## Context
The forces at play: the requirement/constraint that forced a choice, and what
made it non-obvious. State the tension honestly — an ADR with no tension is a note,
not a decision.

## Decision
What was chosen, in the active voice ("We put X behind an interface"). Enough that
a reader can act on it without reconstructing the debate.

## Consequences
- **Positive:** what this buys.
- **Negative / open:** what it costs, and what remains unverified. Name the open
  risks — a consequences section with only upsides is not trusted.
```

Rules:
- Prefer the smallest decision that captures the fork. Split unrelated decisions
  into separate ADRs.
- When a later decision reverses an earlier one, set the old ADR's status to
  `Superseded by ADR-MMMM` — never delete it. The trail is the value.
- Cite the criterion, principle, or constraint the decision serves.
