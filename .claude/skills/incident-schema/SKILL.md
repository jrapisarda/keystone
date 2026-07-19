---
name: incident-schema
description: The append-only Incident Record contract — the structured shape every gate stop + resolution is written in, and the input the synthesizer consolidates. Preloaded into the synthesizer; referenced by anything that reads or reasons about .incidents/log.jsonl.
---

# Incident Record schema

`.incidents/log.jsonl` is **append-only, structured, and never wired into live
recall** — it is synthesizer input only. Free prose is prohibited: the
consolidation score depends on the structured fields. A complete record is written
**once, at resolution** (green close or escalation), so the log is never mutated;
the in-flight incident is accumulated in `.keystone/state.json` first, then written
whole.

This is the single source of truth for the shape the gate emits (see
`keystone_gate/core.py::_incident`).

| Field | Type | Meaning |
|---|---|---|
| `id` | uuid | unique record id |
| `criterion_id` | string | the criterion/sub-obligation the stop was against |
| `phase` | string | owning phase |
| `symptom` | text | what the gate/verifier observed (captured at the first red) |
| `diagnosis` | text | root cause — blank at gate time; the synthesizer/rework may enrich |
| `resolution` | text | `verifier-passed` \| `escalated-pending-human` |
| `fix_method` | enum | `real_fix` \| `suspect` (weakened test / stub) \| `unresolved` — **scoring input** |
| `time_to_resolve` | int | minutes from first red to resolution — scoring input |
| `cross_cutting` | bool | scoring input (breadth) |
| `project_specific` | bool | scoring input (generalizability — `false` favors global promotion) |
| `created_at` | ISO-8601 | resolution timestamp |
| `attempts` | int | rework attempts consumed |
| `session_id` | string | origin session (provenance / correlation) |
| `feature` | string | the requirements-doc feature this run is bound to (provenance at scale) |
| `event` | enum | `phase_closed` \| `escalated` |

## How the synthesizer uses it

- **Down-weight `fix_method=suspect`** below the persistence threshold — a red gate
  "fixed" by weakening a test is not a learning.
- Score on generalizability (`project_specific=false`), breadth (`cross_cutting`),
  and cost/frequency (`time_to_resolve`, recurrence of a `symptom`).
- Route: `discard` (too narrow / below threshold) · `project` (auto-apply) ·
  `global-promotion` (held for human review).
