"""Coverage ledger — the artifact that makes "done" enforceable (WORKFLOW_SPEC §2.2/§3.1).

Every acceptance criterion decomposes into single-owner **sub-obligations**, each
owned by exactly one phase. A parent criterion's status is a pure derivation over
its sub-obligations' phase-completion plus, for cross-cutting criteria, a separate
end-to-end integration check:

    pending : not all owning phases are complete — un-checkable, and that is correct
    due     : the LAST owning phase has landed; now checkable end-to-end
    green   : verified (single-phase: phase greened it; cross-cutting: + e2e verified)

The central fact this encodes: a criterion that spans layers **cannot reach green**
just because each layer is individually done — the integration must be verified at
the completing phase. That is the "journal populates its graph" regression, made
un-shippable.

Everything here is a pure function of (criteria, completed_phases, integration_verified,
phase_order) so the ledger logic is exhaustively testable with no session or disk.
The bridge to the gate is `phase_obligations()`: what the verifier must adjudicate
when a phase closes — exactly the list the orchestrator writes into
`.keystone/state.json` for the verifier to consume.
"""

from __future__ import annotations

from typing import Iterable

PENDING = "pending"
DUE = "due"
GREEN = "green"


def owning_phases(criterion: dict) -> set:
    return {s["owning_phase"] for s in criterion.get("sub_obligations", []) if s.get("owning_phase")}


def is_cross_cutting(criterion: dict) -> bool:
    return len(owning_phases(criterion)) > 1


def is_smoke(criterion: dict) -> bool:
    """A criterion whose truth is only knowable by the real-build smoke gate —
    booting the production build, running migrations against a real DB, and
    driving the running app (Playwright / real API). Such criteria must NOT
    auto-green when their owning phase's unit tests pass; unit tests run against
    mocks/pglite and structurally cannot reach the running system."""
    return bool(criterion.get("smoke", False))


def completing_phase(criterion: dict, phase_order: Iterable[str]):
    """The phase whose completion makes the criterion checkable end-to-end —
    the last of its owning phases in dependency (topological) order."""
    order = list(phase_order)
    ops = owning_phases(criterion)
    ranked = [p for p in order if p in ops]
    return ranked[-1] if ranked else None


def sub_obligation_status(sub: dict, completed_phases: set) -> str:
    return GREEN if sub.get("owning_phase") in completed_phases else PENDING


def criterion_status(criterion: dict, completed_phases: set, integration_verified: set,
                     smoke_verified=frozenset()) -> str:
    """Pure AND over sub-obligation phase-completion, plus the due-gates.

    A single-phase criterion greens when its phase completes (the phase's own
    verifier already checked it). A cross-cutting criterion needs `integration_verified`
    (the end-to-end pass at its completing phase). A **smoke** criterion needs
    `smoke_verified` (the real-build smoke gate) — it never auto-greens on phase
    completion, because unit tests can't reach the running system. A criterion that
    is both requires BOTH gates.
    """
    ops = owning_phases(criterion)
    if not ops:
        return PENDING  # unowned — a coverage bug surfaced by validate_coverage()
    if not ops <= set(completed_phases):
        return PENDING
    gates = []
    if is_cross_cutting(criterion):
        gates.append(criterion["id"] in set(integration_verified))
    if is_smoke(criterion):
        gates.append(criterion["id"] in set(smoke_verified))
    if gates:
        return GREEN if all(gates) else DUE
    return GREEN


def phase_obligations(criteria: list, phase: str, phase_order: Iterable[str]) -> list:
    """What the verifier must adjudicate when `phase` closes — the bridge to the gate.

    - every sub-obligation OWNED by `phase`, and
    - every cross-cutting criterion whose COMPLETING phase is `phase` (its
      end-to-end integration check becomes due exactly here).

    Returned in the `{id, text, proving_test, kind}` shape the verifier prompt and
    `.keystone/state.json` expect.
    """
    order = list(phase_order)
    obligations = []
    for c in criteria:
        for s in c.get("sub_obligations", []):
            if s.get("owning_phase") == phase:
                obligations.append({
                    "id": f"{c['id']}/{s['id']}",
                    "text": s.get("text") or c.get("text", ""),
                    "proving_test": s.get("proving_test"),
                    "kind": "sub_obligation",
                })
        if is_cross_cutting(c) and completing_phase(c, order) == phase:
            obligations.append({
                "id": f"{c['id']}::e2e",
                "text": f"End-to-end integration: {c.get('text', '')}",
                "proving_test": c.get("e2e_test"),
                "kind": "integration",
            })
    return obligations


def validate_coverage(criteria: list, phase_order: Iterable[str] | None = None) -> list:
    """Tier-1 gate: every criterion must be owned, every sub-obligation assigned
    to exactly one existing phase with a named proving test. Returns a list of
    human-readable problems (empty == the ledger is approvable). Unowned criteria
    are surfaced here, never silently forgotten."""
    known = set(phase_order) if phase_order is not None else None
    problems = []
    seen_ids = set()
    for c in criteria:
        cid = c.get("id")
        if not cid:
            problems.append("a criterion has no id")
            continue
        if cid in seen_ids:
            problems.append(f"{cid}: duplicate criterion id")
        seen_ids.add(cid)
        subs = c.get("sub_obligations", [])
        if not subs:
            problems.append(f"{cid}: no sub-obligations — criterion is unowned")
            continue
        for s in subs:
            tag = f"{cid}/{s.get('id', '?')}"
            op = s.get("owning_phase")
            if not op:
                problems.append(f"{tag}: sub-obligation has no owning phase")
            elif known is not None and op not in known:
                problems.append(f"{tag}: owning phase '{op}' is not in the phase decomposition")
            if not s.get("proving_test"):
                problems.append(f"{tag}: no proving test named")
    return problems


def ledger_summary(criteria: list, completed_phases: set, integration_verified: set,
                   smoke_verified=frozenset()) -> dict:
    counts = {PENDING: 0, DUE: 0, GREEN: 0}
    for c in criteria:
        counts[criterion_status(c, completed_phases, integration_verified, smoke_verified)] += 1
    return {
        "total": len(criteria),
        **counts,
        "cross_cutting": sum(1 for c in criteria if is_cross_cutting(c)),
        "smoke": sum(1 for c in criteria if is_smoke(c)),
        "smoke_pending": sum(
            1 for c in criteria
            if is_smoke(c) and criterion_status(c, completed_phases, integration_verified, smoke_verified) != GREEN
        ),
        "all_green": all(
            criterion_status(c, completed_phases, integration_verified, smoke_verified) == GREEN
            for c in criteria
        ),
    }
