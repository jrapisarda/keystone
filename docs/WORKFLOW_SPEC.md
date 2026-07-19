# Workflow Specification: Gated Structural-Verification Development Workflow

**Version:** 1.0
**Date:** 2026-07-19
**Stakeholder:** Jonathan Rapisarda
**Status:** Approved for Implementation

> **Working codename:** "Keystone" is a placeholder — rename freely. It refers to the load-bearing enforcement piece (the Stop-hook gate) and appears only as the system identifier, with no functional dependency.

---

## Executive Summary

Keystone is a multi-phase, test-first development workflow for Claude Code that makes "done" a **structurally verified property rather than a self-reported claim**. It runs a capable coding agent through architecturally-scoped phases against an approved requirements decomposition, and blocks each phase from closing until an independent verifier confirms — via tests derived from the requirements — that every acceptance criterion the phase owns is actually satisfied. It integrates a cross-project memory system so learnings compound across builds, and a batch consolidation engine that keeps that memory high-signal over time.

### Business Value

The workflow exists to fix a specific, observed failure: a capable TDD loop **silently ships incomplete work on thin specifications**. Examples of this on the recent Aurelis project would have been features launched broken while the agent reported completion — a journal that never populated its knowledge graph, a hardcoded PRNG seed that made every output identical, stubs standing in for requirements, the wrong model wired in, runtime crashes on load — and none were caught until aggregate UAT, expensively and late. One complex project (Aurelia) reached 100% first-pass UAT, but only because its specification was exceptional enough to do the coverage work implicitly. Keystone makes that outcome **repeatable on ordinary specifications**, by moving structural verification earlier and enforcing it deterministically. Impact is measured (see §11) as first-pass UAT rate, rework time, and memory-recall utilization across a multi-project trial.

### Scope Classification

- **Type:** Greenfield (formalization and hardening of the stakeholder's existing Vault-Pattern workflow)
- **Target:** Production-Complete (a workflow the stakeholder runs on real client and internal builds)
- **Timeline:** No hard deadline; quality-gated by the stakeholder's own multi-project trial before it becomes the default loop.

---

## Design Principles (Load-Bearing Invariants)

These generate every decision below. A change that violates one of these is a change to the architecture, not a tuning knob.

1. **Structural check at the point of claim.** No claim ("done," "this memory is valuable," "tests pass") is backed by trust in the component making it. Enforcement lives at the write/close path as a structural gate, not in an instruction the model may or may not follow. This is the same guarantee the stakeholder's memory gate already provides for secrets, generalized to the whole loop. Native corollary: CLAUDE.md and memory are *context, not enforced configuration*; hard enforcement is **hooks**.
2. **Reads fan out; writes centralize.** Read-heavy work (research, requirements compression, verification) is parallel and isolated. Writes (code, memory, commit, the ledger) flow through a single writer — the orchestrator — so consolidation and consistency hold.
3. **Boundaries follow context-economy fault lines, not the step list.** A subagent exists where a large input compresses to a small durable artifact, or where gotcha-dense specialization pays off — never merely to mirror a workflow step. The tightly-coupled build loop stays in one context because its state must not be severed at a boundary.
4. **Only validated learnings reach memory.** Research produces hypotheses and writes to `docs/`, never to the memory store. Learnings are written at phase end (after tests pass) and consolidated in batch. Speculation never carries the authority of a battle-tested gotcha.
5. **Mirror native, don't re-platform.** The workflow reconstructs the design of Claude Managed Agents' Dreaming and Outcomes on the Claude Code surface using hooks, subagents, and the custom MCP store — because those native features live on a different product surface that would cost the cross-project recall that is this system's actual differentiator (and are disqualified where Zero-Data-Retention is required). Seams are designed so the native versions can be adopted later.

---

## 1. Operators & Actors

### Primary Actors

| Actor | Level | Primary Actions |
|-------|-------|-----------------|
| Stakeholder (Jonathan) | High | Approves the project decomposition + ledger once up front; handles phase-end escalations; reviews global-memory promotion candidates; runs final UAT. Sole approver. |
| Orchestrator (main Claude Code session) | — | Runs the coupled build loop; holds the plan, coverage ledger, and test surface continuously; writes the ledger and memory; delegates to subagents. **Not** a subagent — this is the state that must not be severed. |
| Subagent roster | — | Six fixed-harness specialists (§6.1), each routed by description and fed a task prompt at delegation. |

### Secondary Actors / Systems

| Entity | Interaction | Notes |
|--------|-------------|-------|
| Custom MCP memory server | Producer/Consumer | Cross-project, hybrid (semantic + BM25 + MMR) recall; sensitivity-gated; markdown source of truth. The memory layer. |
| Claude Code native primitives | Substrate | Hooks (enforcement), subagents (context firewalls), skills (playbooks/slash commands), plan mode (ephemeral scaffolding). |
| Git | Producer/Consumer | Version control for code, the `.claude/` tree, artifacts, and the markdown memory store. |
| Claude Managed Agents (Dreaming / Outcomes) | Future seam | Not used at runtime (different surface; ZDR-incompatible). Their *design* is mirrored; adoption seams retained. |

### Approval Authority

Jonathan is the **sole approver**, and approves at exactly two moments: (1) the project decomposition + coverage ledger, once, before any phase loop runs; (2) global-memory promotion candidates, in batch, during consolidation. Everything else runs autonomously, escalating on exception.

---

## 2. Functional Requirements

### 2.1 Core Execution Model — Two Tiers

Keystone runs in two tiers. **Phases are scoped by architectural layer** (infrastructure, data layer, agent pipeline, vision/camera, web app, etc.), not by feature or by agent — the architect scopes them, and multiple components may be built in a single phase. Because layers don't individually deliver working features, **most user-facing acceptance criteria are cross-cutting by construction**; this is the central fact the design accounts for.

#### Tier 1 — Project-Initiation Pass (runs once)

```
Trigger: Stakeholder invokes the workflow on an approved requirements document
Steps:
1. SCAN — SessionStart injects relevant global memories into context
2. SYNTHESIZE — requirements-synthesizer compresses the full spec to a working
   digest and emits the complete acceptance-criteria list
3. RESEARCH (conditional) — researcher investigates genuine unknowns; briefs → docs/
4. ARCHITECT — architect produces the architectural-layer phase decomposition and the
   inter-phase dependency graph; ADRs → docs/
5. LEDGER BUILD — orchestrator decomposes every acceptance criterion into single-owner
   sub-obligations and assigns each to the phase that owns it (see §3.1)
6. PERSIST — IMPLEMENTATION_PLAN.md written with both tiers (decomposition + ledger +
   per-phase detail)
7. APPROVE — Stakeholder reviews and approves the decomposition + ledger (the one
   up-front gate). The phase decomposition and the ledger ARE the plan.
Outcome: An approved, persisted, resumable project structure with a complete coverage
ledger mapping every criterion to owning phases.
```

#### Tier 2 — Per-Phase Execution Loop (runs once per phase, in dependency order)

```
Trigger: A phase becomes eligible (its dependency phases are complete)
Steps:
1. SCAN — SessionStart injects current ledger state + phase-relevant memories
2. SYNTHESIZE — requirements-synthesizer produces this phase's slice (its owned
   sub-obligations + any criteria that will become "due" this phase)
3. WRITE TESTS — test-writer derives behavior-level tests from the phase's owned
   sub-obligations and any now-due integration criteria (interactions, negatives,
   degenerate/stub cases included)
4. CODE — orchestrator implements
5. TEST → REFACTOR → TEST — the proven sandwich; re-test after refactor
6. GATE — Stop hook invokes the verifier (§6.1) to adjudicate: every owned
   sub-obligation green AND every now-due criterion passes end-to-end; plus real-build
   smoke for runtime surfaces. Red → bounded rework; on exhaustion → escalate at phase end
7. COMMIT — code committed once the gate passes
8. INCIDENT-CAPTURE — every gate stop and its resolution appended to the incident log
   as a structured record
Outcome: A phase whose owned sub-obligations and completed-this-phase features are
structurally verified, committed, with learnings captured.
```

#### Tier-adjacent — Consolidation Pass (batch: project close or every N phases)

```
Trigger: Project close, or an N-phase cadence
Steps:
1. synthesizer reads the incident log + current MCP store (curated input, not everything)
2. Produces a NEW, reorganized store (non-destructive): duplicates merged, stale/
   contradicted entries replaced, cross-session patterns surfaced, each candidate scored
   and routed (discard | project | global-promotion)
3. Project-scoped memories above threshold auto-apply; global-promotion candidates are
   held for stakeholder review-first approval
Outcome: A curated memory store that stays high-signal as it grows; the input store is
never mutated and a bad run can be discarded.
```

### 2.2 Feature Specifications

#### Feature: Coverage Ledger with Cross-Cutting Criteria

- **Description:** The single artifact that makes "done" enforceable. A shallow tree, embedded in `IMPLEMENTATION_PLAN.md`.
- **Input:** The full acceptance-criteria list + the architect's phase decomposition.
- **Output:** For each criterion, a set of single-owner sub-obligations, each mapped to (owning phase, proving test, status). The parent criterion's status is a pure AND over its sub-obligations.
- **Business Rules:**
  - A criterion that spans layers is modeled as a conjunction of sub-obligations, each owned by exactly one phase. No phase can flip a parent criterion green — only its own sub-obligation.
  - **State machine:** `pending` (not all sub-obligation phases complete — un-checkable, and that is correct) → `due` (the last owning phase has landed; now checkable end-to-end) → `green` (verifier passed).
  - An unassigned criterion is *visibly* unowned, not silently forgotten (kills coverage drift).
- **Acceptance Criteria:**
  - [ ] Every acceptance criterion in the source spec appears in the ledger with ≥1 sub-obligation, each assigned to exactly one phase.
  - [ ] A cross-cutting criterion cannot reach green until all its sub-obligation phases are green AND its end-to-end verifier passes.
  - [ ] Integration verification for a feature fires at the phase that completes its last cross-layer piece (the "due" transition), wherever that falls.

#### Feature: The Gate (Stop-hook enforcement)

- **Description:** The keystone. A Stop hook that refuses to let a phase's turn end until verification passes.
- **Input:** Phase-end signal; the ledger; the verifier's adjudication.
- **Output:** Either turn-end permitted (all clear) or turn-end blocked with the specific failing item as the reason.
- **Business Rules:**
  - Two-mode, deadlock-safe: for rework attempts 1..N the hook **blocks** turn-end and hands back the failing sub-obligation/criterion; on attempt N+1 it **releases** the turn and marks the phase escalated-pending-human.
  - Adjudication is performed by the independent **verifier** subagent, never the coder.
  - Escalation is decoupled from any "human must approve to continue" gate, so close-watching and fire-and-walk-away are the same mechanism at different attention levels — escalations queue when unattended.
- **Acceptance Criteria:**
  - [ ] A phase with any red owned sub-obligation cannot close within the attempt budget.
  - [ ] Rework is bounded; exhaustion escalates rather than looping or shipping red.
  - [ ] The component that decides "green" has no edit tools and cannot alter code or tests to pass.

#### Feature: Config-Conformance Guard

- **Description:** Static enforcement of fixed constraints (model identity, retention flags, allowed enums) that mocked tests never catch.
- **Input:** Intercepted model/API tool calls.
- **Output:** Allowed, or blocked (exit 2) with reason.
- **Business Rules:** Reject any non-approved model, and specifically any Covered Model (Fable 5 / Mythos 5) where ZDR applies. Fail-closed pattern extended from data validation to constants.
- **Acceptance Criteria:**
  - [ ] An API call specifying a non-approved or Covered model is blocked before dispatch.
  - [ ] The approved-model set is a single source of truth, editable in one place.

#### Feature: Real-Build Smoke Gate

- **Description:** Catches runtime-only failures that unit/integration tests structurally cannot reach.
- **Input:** The built production artifact.
- **Output:** Pass/fail on boot, real-API round-trip, and non-happy-path traversal.
- **Business Rules:** Boot the actual production build headless; hit the *real* API (not a mock) for the model-call class; exercise the specced non-happy-paths. Genuinely un-automatable surfaces (e.g. live camera capture) are explicitly designated manual and surfaced to the stakeholder rather than falsely passed.
- **Acceptance Criteria:**
  - [ ] A build that crashes on load fails the gate.
  - [ ] A wrong-model or bad-LLM-call at runtime fails the gate.
  - [ ] Manual-only checks are flagged, not silently skipped.

### 2.3 Edge Cases & Failure Handling

| Scenario | Expected Behavior | Signal |
|----------|-------------------|--------|
| Rework budget exhausted on a red criterion | Release turn, mark phase escalated-pending-human | Notification hook + phase-close report |
| Agent "fixes" a red gate by weakening a test / stubbing behavior | Resolution recorded with fix-method; synthesizer down-weights it below persistence threshold; verifier (no edit tools) catches stubs against behavior tests | Incident record flag: `fix_method=suspect` |
| Cross-layer feature broken while each layer reports done | Parent criterion stays `due`+red until end-to-end verifier passes at the completing phase | Gate block at the completing phase |
| Dead session mid-project | Resume from `IMPLEMENTATION_PLAN.md` + ledger state + `origin_session` provenance | Plan file is the resumability anchor |
| Skill fails to trigger inside plan mode | Orchestrator explicitly delegates/invokes rather than relying on ambient skill-triggering during plan mode | Design note, not a runtime failure |
| Bad consolidation run | Input store never mutated; output reviewed/discarded; global promotions gated | Review-first on promotions |

---

## 3. Data Architecture

### 3.1 Core Entities

#### Entity: Coverage Ledger (embedded in IMPLEMENTATION_PLAN.md)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| criterion_id | string | PK | Acceptance criterion from the source spec |
| sub_obligations[] | list | ≥1 | Each: `{id, owning_phase, proving_test, status}` |
| status | enum | derived | `pending` \| `due` \| `green` — pure AND over sub-obligations + due-gate |
| owning_phases | list | derived | Union of sub-obligation phases (defines the `due` transition) |
| is_cross_cutting | bool | — | True when sub-obligations span >1 phase |

#### Entity: Incident Record (append-only incident log)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | uuid | PK | |
| criterion_id | string | FK | The criterion the stop was against |
| phase | string | not null | Owning phase |
| symptom | text | not null | What the gate observed |
| diagnosis | text | not null | Root cause |
| resolution | text | not null | How it was fixed |
| fix_method | enum | not null | `real_fix` \| `suspect` (weakened test / stub) — feeds scoring |
| time_to_resolve | int | not null | Minutes; a scoring input |
| cross_cutting | bool | not null | Scoring input (breadth) |
| project_specific | bool | not null | Scoring input (generalizability) |
| created_at | timestamptz | not null | |

> The incident log is **append-only, structured, and never wired into live recall.** It is synthesizer input only. Free prose is prohibited — the score depends on the structured fields.

#### Entity: Memory Record (MCP store — unchanged from existing system)

Existing schema retained: frontmatter (`name`, `description`, `metadata.{type, scope, domain, sensitivity, source_project, origin_session, created}`) + body with `[[links]]`. `description` is load-bearing (recall ranks on it). `scope: global` is gate-enforced secret/PII-free.

#### Relationships

```
SourceSpec --[decomposed into]--> AcceptanceCriteria
AcceptanceCriterion --[splits into]--> SubObligation(s)
SubObligation --[owned by exactly one]--> Phase
Phase --[emits]--> IncidentRecord(s)
IncidentRecord(s) --[synthesized into]--> MemoryRecord(s)
MemoryRecord --[links to]--> MemoryRecord   (cross-project knowledge graph)
```

### 3.2 Data / Control Flow

```
┌────────────────────────── TIER 1 (once) ──────────────────────────┐
 SourceSpec ─▶ requirements-synthesizer ─▶ digest + criteria
                                            │
              researcher ─▶ docs/briefs     │
              architect  ─▶ layer decomposition + dependency graph ─▶ docs/ADRs
                                            ▼
                          orchestrator builds COVERAGE LEDGER
                                            ▼
                          IMPLEMENTATION_PLAN.md  ──▶  STAKEHOLDER APPROVES
└────────────────────────────────────────────────────────────────────┘
                                            │
┌────────────────────── TIER 2 (per phase) ─┼───────────────────────┐
 SessionStart injects ledger+memories ─▶ test-writer ─▶ CODE
                                            ▼
                        TEST ▶ REFACTOR ▶ TEST
                                            ▼
        Stop hook ─▶ VERIFIER (owned + due criteria) + SMOKE
                     red ─▶ bounded rework ─▶ (exhausted) escalate
                     green ─▶ COMMIT ─▶ INCIDENT-CAPTURE (append)
└────────────────────────────────────────────────────────────────────┘
                                            │
        (batch) synthesizer ◀── incident log + MCP store
                └─▶ new curated store (dedup/score/route) ─▶ auto-apply project /
                                                             review-first global
```

### 3.3 Validation Rules (enforced as gates, not conventions)

| Point | Rule | On Violation |
|-------|------|--------------|
| Memory write | No secret/PII in `global` scope; redact-at-rest; auto-escalate sensitivity | Block (existing gate) |
| Model/API call | Model ∈ approved set; not a Covered Model under ZDR | Block, exit 2 (PreToolUse) |
| Phase close | All owned sub-obligations green; all now-due criteria pass end-to-end | Block turn-end (Stop hook) |
| Incident record | All structured fields present; `fix_method` set | Reject append |
| Global promotion | Human review-first | Held until approved |

---

## 4. Integration Points

### 4.1 External Systems

#### Integration: Custom MCP Memory Server

- **Type:** MCP server (stdio), registered at user scope (available in every project)
- **Direction:** Bidirectional
- **Tools:** `memory_search`, `memory_write` (gated), `memory_promote` (propose-only), `memory_reindex`, `memory_status`
- **Rationale for keeping it over native auto-memory:** native `MEMORY.md` is per-repo and machine-local — the exact fragmentation ("couldn't see across folders") that motivated the custom system. Cross-project hybrid recall + the sensitivity gate are differentiators neither native auto-memory nor Managed Agents provide on this surface.

#### Integration: Claude Code Hooks (settings.json)

- **Type:** Lifecycle enforcement; project-scoped, git-shared
- **Handlers used:** Command, Prompt, and **Agent** (a verifier subagent as a gate)
- See §6.1 (verifier) and §2.2 (gates) for the full hook map.

#### Integration Seam (future): Claude Managed Agents — Dreaming / Outcomes

- **Status:** Not used at runtime. Mirrored in design; adoption seams retained.
- **Mapping:** Outcomes (rubric + independent grader in its own context + bounded iteration) → the coverage ledger + verifier + bounded rework. Dreaming (non-destructive async consolidation over ≤100 curated sessions) → the synthesizer. Adopt only if these reach the Claude Code surface *and* ZDR constraints permit.

### 4.2 Internal Dependencies

| Dependency | Purpose | Criticality |
|------------|---------|-------------|
| Custom MCP Memory Server (already deployed and functioning)
| `docs/` (research briefs, ADRs, architecture reviews) | Durable rationale + resumability context | High |
| IMPLEMENTATION_PLAN.md | Plan + ledger + resumability anchor | Critical |

---

## 5. Non-Functional Requirements

### 5.1 Performance & Throughput

| Metric | Target | Measurement |
|--------|--------|-------------|
| Wall-clock per phase | Reduce vs baseline (prior run: 4 foundation phases ≈ 8h, 4 later ≈ 2h) | CCWAP per-phase timing |
| First-pass UAT rate | Trend upward across the multi-project trial | Recorded per project |
| Rework time | Trend downward | Gate-stop → resolution deltas |

**Speed levers.** With Opus selected for all agents (stakeholder decision; other models underperform and the cost delta is small), model-routing is *not* a lever. Wall-clock reduction must come from: parallelizing the compressible reads (research fan-out), the doubled Claude Code rate limits + removal of peak-hour throttling, prompt caching, and — pending confirmation by the warm-start experiment (§11) — the memory-warming effect.

### 5.2 Security

- **Memory:** `global` scope gate-enforced secret/PII-free; secrets redacted at rest; sensitivity auto-escalates; pre-commit hook as belt-and-suspenders.
- **Config:** Covered Models blocked under ZDR by the config-conformance guard.
- **Constraint:** Zero-Data-Retention accounts cannot use Claude Managed Agents — a hard reason the orchestration/consolidation layer stays on the Claude Code surface.
- **Subagent tool-scoping is a security control:** the researcher has no memory-write tool; the verifier has no edit tools. Boundaries are enforced by configuration, not by hoping the model behaves.

### 5.3 Reliability & Recovery

- **Resumability:** `IMPLEMENTATION_PLAN.md` + ledger state + `origin_session` provenance let a dead session resume from the last completed phase rather than restarting. (Native plan-mode plan files are session-ephemeral; this durable artifact is the fix.)
- **Consolidation safety:** non-destructive (input store never mutated; output reviewable/discardable).

### 5.4 Scalability

- **Cross-project:** the MCP store is the mechanism by which knowledge compounds across builds; the always-on global index stays lean (one line per global memory), full bodies fetched on demand.
- **Store growth:** batch consolidation keeps the store high-signal as it grows; the incident log grows unbounded but is offline synthesizer-input, never loaded into live recall.

---

## 6. Technical Specifications

### 6.1 Subagent Roster

All agents: fixed harness (YAML frontmatter + system-prompt body + **tool allowlist** + model), **Opus**, routed by `description`, fed a task-specific prompt via the Agent tool at delegation. Thin by design — accumulated knowledge is recalled from the MCP store at runtime, not baked into the prompt (the prior hand-rolled agents' learnings are already distilled into the store).

| Agent | Purpose | Tools | Writes to | Why it exists |
|-------|---------|-------|-----------|---------------|
| **requirements-synthesizer** | Compress the spec to a working/phase digest; emit the acceptance-criteria list | Read-only | (returns to orchestrator) | Context firewall for the giant spec; reads fan out, orchestrator owns the ledger write |
| **researcher** | Investigate genuine unknowns at architecture time | Read, web/search; **no memory-write** | `docs/` briefs | Isolation compresses many sources to a brief; no-write tool makes "research never writes to memory" structural |
| **architect** (rebuilt sr-architect-review) | Produce the architectural-layer phase decomposition + dependency graph; review the plan | Read + analysis | `docs/` ADRs + decomposition | Owns the phasing decision (it is an architecture decision); gotcha-dense architectural judgment |
| **test-writer** (rebuilt unit-test-writer) | Derive behavior-level tests from ledger sub-obligations — interactions, negatives, degenerate/stub cases | Read, test-write | Test files | Encoding "what would a stub/degenerate impl do, and does a test catch it" is durable specialization; preloaded with the test-conventions skill |
| **verifier** *(new — the Outcomes insight)* | Independently adjudicate each owned sub-obligation + now-due criterion, in its own context, uninfluenced by the coder | Read + test-execution; **no edit** | (returns verdict to Stop hook) | The component claiming "done" cannot be the one judging it; no-edit tools prevent fixing-to-pass |
| **synthesizer** *(Dreaming-equivalent)* | Batch, non-destructive consolidation over the incident log + MCP store: dedup, drop-stale, score, route; surface global-promotion candidates | Read + memory-write (gated) | New curated store (proposal) | Cross-session pattern-finding a single phase can't see; preloaded with the incident-schema skill |

**Orchestrator** = the main Claude Code session. Runs the per-phase build loop; holds plan + ledger + test surface continuously; writes the ledger and (via consolidation) memory. Deliberately not a subagent — this is the coupled state.

### 6.2 Enforcement — Hook Map (settings.json, project-scoped, git-shared)

| Hook Event | Matcher | Handler | Action | Disease addressed |
|------------|---------|---------|--------|-------------------|
| SessionStart | — | Command | Query MCP store; inject ledger state + relevant memories (this *is* the SCAN step) | Context loss |
| PreToolUse | model/API calls | Command | Config-conformance: reject non-approved / Covered model, exit 2 | 3b (config) |
| Stop | — | Agent (verifier) | Adjudicate owned sub-obligations + now-due criteria; red → block turn-end with reason; N+1 → release + escalate | 1, 2 (false-done, drift) |
| (Agent handler within Stop) | — | Agent | Real-build smoke: boot headless, real-API round-trip, non-happy-paths | 4 (runtime) |
| PostToolUse | Write\|Edit | Command | Format + lint hygiene | Hygiene |
| pre-commit (git) | — | Command | Memory-gate re-run + optional ledger-green assertion before phase commit | Security + close integrity |

### 6.3 Project Structure (the workflow ships as a portable tree)

```
<any-project>/
├── .claude/
│   ├── CLAUDE.md                 # THIN: pointer + a few "always" rules only
│   ├── rules/                    # modular, path-scoped instructions
│   ├── agents/                   # the six subagent definitions
│   ├── skills/
│   │   ├── keystone/             # the one orchestrating /-command (sequences all tiers)
│   │   ├── test-conventions/     # preloaded into test-writer
│   │   ├── adr-format/           # preloaded into architect
│   │   └── incident-schema/      # preloaded into synthesizer + incident-capture
│   └── settings.json             # the hook map (§6.2)
├── docs/                         # research briefs, ADRs, architecture reviews
├── IMPLEMENTATION_PLAN.md        # two-tier plan + coverage ledger (resumability anchor)
└── .incidents/log.jsonl          # append-only incident log (synthesizer input only)
# + MCP memory server registered at user scope (cross-project)
```

### 6.4 Configuration Layer

- **Thin CLAUDE.md + `.claude/rules/`** carry only what must be in every session (a few "always" rules, the pointer to the workflow). Multi-step procedure lives in skills; path-specific guidance in rules; enforcement in hooks. This respects the native "context, not enforcement" split.
- **The workflow's identity lives in the `.claude/` tree + the MCP store**, both git-versioned markdown — the stakeholder's "markdown is source of truth, index is a disposable cache" principle applied to the workflow itself. Whatever the CLAUDE.md successor format becomes, the pointer is regenerable and nothing load-bearing moves.

---

## 7. Testing Requirements (the workflow's own methodology)

### 7.1 Test Strategy

Test-first, derived from acceptance criteria, is preserved from the proven loop and sharpened:

| Type | Focus | Owner |
|------|-------|-------|
| Unit / behavior | Each sub-obligation, including **interactions and negative/degenerate cases** (the seed-bug and stub classes) | test-writer, adjudicated by verifier |
| Integration / end-to-end | Each cross-cutting criterion at its `due` phase (the journal-populates-graph class) | verifier, at the completing phase |
| Real-build smoke | Boot, real-API, non-happy-paths (the crash-on-load / wrong-model-at-runtime class) | Agent-handler hook |
| Static conformance | Fixed constants: model identity, retention flags, enums | PreToolUse guard |

### 7.2 Coverage Requirement

Coverage is defined by the ledger, not a percentage: **every acceptance criterion's sub-obligations must be owned, tested, and green before its parent closes.** Un-owned criteria are a hard failure surfaced at Tier-1 approval.

### 7.3 Test Data

Behavior tests must include the degenerate/adversarial inputs that a stub or over-fitted implementation would pass (e.g. a fixed-seed check paired with a *distinct-outputs* check, so over-satisfying one requirement can't hide breaking another).

---

## 8. Deployment & Operations

### 8.1 "Deployment" of the Workflow

The workflow is the portable `.claude/` tree (§6.3) plus the user-scope MCP registration. Installed into a project, invoked by the single `/keystone` command. Versioned and git-shared; portable across projects.

### 8.2 Monitoring & Observability

| Aspect | Approach | Signal |
|--------|----------|--------|
| Per-phase cost/time | CCWAP | Wall-clock + cost per phase |
| Memory utilization | Recall hits actually used per phase | Isolates the memory effect (§11) |
| Rework | Gate-stop count + resolution time per phase | Trends the disease-1/2 fix |
| Escalations | Notification hook + phase-close report | Queued for stakeholder attention |

### 8.3 Source Control

Git, trunk-based. Code committed per phase after the gate passes; the `.claude/` tree and markdown memory store versioned; the derived index gitignored and rebuildable.

---

## 9. Documentation Requirements

| Document | Audience | Contents |
|----------|----------|----------|
| IMPLEMENTATION_PLAN.md | Orchestrator + stakeholder | Two-tier plan + coverage ledger; regenerated/updated per phase |
| docs/ADRs | Future maintainers | Architecture decisions, incl. the layer decomposition rationale |
| docs/research briefs | Orchestrator | Validated-later hypotheses (never memory until validated) |
| Workflow README | Stakeholder / collaborators | How to install and invoke `/keystone`; the tier model; the gate semantics |

---

## 10. Constraints & Risks

### 10.1 Constraints

| Constraint | Impact | Mitigation |
|------------|--------|------------|
| Opus for all agents | Model-routing unavailable as a speed lever | Speed from concurrency + rate limits + memory-warming |
| ZDR requirements (healthcare work) | Managed Agents (Dreaming/Outcomes native) off-table | Mirror on Claude Code surface; retain seams |
| Native plan mode is ephemeral + non-uniform | Can't rely on it for durability/uniformity | Durable, uniform IMPLEMENTATION_PLAN.md |
| Skills may not trigger inside plan mode | Ambient skill-triggering unreliable during planning | Orchestrator delegates explicitly |

### 10.2 Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Rework games the gate (weakens test / stubs) | M | H | `fix_method` scoring down-weight + verifier has no edit tools |
| Cross-cutting criterion false-greens | M | H | Conjunction ledger + `due` state + end-to-end verifier at completing phase |
| Hard-stop deadlocks | L | H | Bounded rework + escalate on exhaustion |
| Over-elaboration degrades what already worked | M | M | Immature loop hit 100%; add only disease-justified machinery; every component traces to a disease or principle |
| Confounded speed diagnosis (complexity vs memory) | — | M | Warm-start natural experiment (§11) |

### 10.3 Assumptions

| Assumption | If False |
|------------|----------|
| **Phases are architectural-layer-scoped, agent-scoped, variable count per project** (corrected from an earlier one-per-feature assumption) | Re-derive gate frequency and escalation cadence |
| Aurelia is a representative worked example of target complexity | Re-calibrate the ledger/verifier load |
| The stakeholder's spec quality is the dominant first-pass variable | Shift emphasis from loop to the upstream requirements-gathering skill |

---

## 11. Success Criteria

### 11.1 Acceptance Criteria (the workflow itself)

- [ ] Across a multi-project trial, first-pass UAT rate is recorded per project and trends upward relative to the pre-Keystone baseline.
- [ ] No acceptance criterion silently ships unmet: every criterion is owned in the ledger and gated at its completing phase.
- [ ] No stub or wrong-constant survives to UAT (verifier + config guard + smoke catch them earlier).
- [ ] A cross-cutting feature broken across layers is caught at the completing phase, not at aggregate UAT (the journal-populates-graph regression cannot recur).
- [ ] Rework is bounded and escalates rather than looping or shipping red.
- [ ] Memory metrics recorded per project: memories gathered (count), memory quality (stakeholder-rated), recall utilization per phase.

### 11.2 The Memory-Effect Experiment (isolating the 8h/2h question)

- [ ] Run later projects against a **warm** cross-project store; compare their *early-phase* wall-clock to a **cold**-start project's early phases, holding project complexity roughly constant. Systematically faster warm early-phases isolate the memory effect from complexity front-loading — and double as ROI evidence for the cross-project store specifically.
- [ ] Instrument per phase via CCWAP: wall-clock, cost, recall-utilization, rework-count, and a complexity proxy (LoC / criteria-count / new-vs-reused patterns).

### 11.3 Definition of Done (workflow build)

- [ ] All six subagents defined to the fixed-harness pattern with correct tool-scoping and Opus.
- [ ] Hook map implemented and firing (SessionStart, PreToolUse guard, Stop-verifier, smoke, PostToolUse, pre-commit).
- [ ] Coverage ledger with `pending`/`due`/`green` states embedded in IMPLEMENTATION_PLAN.md; two-tier plan generation working.
- [ ] Synthesizer (batch, non-destructive, scored/routed, review-first global) operating over the incident log.
- [ ] `/keystone` single-command orchestration sequencing both tiers + consolidation.
- [ ] Portable `.claude/` tree + MCP registration; thin CLAUDE.md.
- [ ] Validated on ≥1 real project against the acceptance criteria above; stakeholder sign-off.

### 11.4 Out of Scope (Explicit)

Re-platforming to Claude Managed Agents (mirrored, not adopted, for now); native `MEMORY.md` as the primary store (rejected — fragmentation); model-routing (Opus chosen); a mandatory per-phase human approval gate (replaced by escalation-on-exception); the incident log as a live-recall source (synthesizer input only).

---

## Appendix A: Diseases → Checks Traceability (the architecture in one table)

| Disease (observed failure) | Mechanism | Structural check | Enforced by |
|----------------------------|-----------|------------------|-------------|
| 1. False "done" (code-shaped ≠ requirement satisfied; stubs reported complete) | Completion claimed from output existing | Coverage ledger; "done" = owned criteria green, adjudicated by an independent verifier | Stop hook + verifier |
| 2. Silent coverage gaps / requirements drift | No criterion→code→test mapping | Ledger: every criterion's sub-obligations owned + tracked; unowned = visible | Ledger + Tier-1 approval |
| 3a. Tests green but requirement fails (test encodes one side of a tension) | Test covers one requirement, not its interaction | Behavior-level tests from criteria incl. interactions/negatives/degenerate cases | test-writer + verifier |
| 3b. Wrong constant (model, retention flag) mocked away | Mocks don't check constants | Static conformance assertion | PreToolUse guard |
| 4. Runtime-only failure (crash on load, dead camera, bad live call) | Harness can't reach the running system | Real-build smoke: boot + real-API + non-happy-paths | Agent-handler hook |
| (cross-cutting amplifier) Feature broken across layers while each layer reports done | Horizontal phasing; no phase owns integration | Conjunction-of-sub-obligations + `due` state + end-to-end verifier at completing phase | Ledger + Stop hook |

## Appendix B: Reference Materials

| Resource | Location | Purpose |
|----------|----------|---------|
| Claude Code memory docs (CLAUDE.md, auto-memory, rules) | code.claude.com/docs/en/memory | "Context not enforcement"; MEMORY.md limits; rules |
| Claude Code hooks reference | code.claude.com/docs/en/hooks | Stop/PreToolUse/Agent-handler enforcement; exit-2 semantics |
| Claude Code subagents | code.claude.com/docs/en/sub-agents | Fixed-harness format; description-routing; tool-scoping; fork mode |
| Claude Code skills | code.claude.com/docs/en/skills | Folder-as-slash-command; preload-into-subagent; invocation knob |
| Managed Agents — Dreams / Outcomes | platform.claude.com/docs/en/managed-agents | Design mirrored (not adopted); ZDR-incompatible; adoption seam |
| Distributed Memory System (this stakeholder's) | Provided docs | The MCP store; scopes; gate; hybrid recall |
| Aurelia requirements | Provided docs | Worked example of target complexity; source of the disease taxonomy |

---

**Document Approval**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Stakeholder | Jonathan Rapisarda | 2026-07-19 | ☑ Approved |
| BSA | Claude | 2026-07-19 | ☑ Generated |
