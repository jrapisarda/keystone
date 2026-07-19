"""Keystone gate — pure decision logic (the load-bearing core).

`decide()` is a pure function of (state, verdict, clock). No I/O, no globals,
no wall-clock read — the caller injects `now_ts`. This is what lets the state
machine that gates every phase be exhaustively unit-tested in isolation, which
is the whole point of the spike: prove the mechanism holds before building the
workflow on top of it.

State machine (WORKFLOW_SPEC §2.2 "The Gate"):

    no active phase            -> ALLOW     (normal turns are never gated)
    phase already resolved     -> ALLOW     (status closed | escalated)
    verifier GREEN             -> ALLOW     (close phase; +incident iff there were reds)
    verifier RED, attempt<=N   -> BLOCK     (hand the failing item back to the model)
    verifier RED, attempt==N+1 -> ESCALATE  (release the turn, mark escalated-pending-human)

The budget N makes the loop deadlock-safe: rework is bounded, and exhaustion
escalates rather than looping forever or shipping red. `attempt` lives in the
durable state file, so the counter survives across successive Stop invocations
— that persistence is what makes "attempts 1..N" meaningful at all.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from . import config

# Decision actions
ALLOW = "allow"
BLOCK = "block"
ESCALATE = "escalate"

# Phase statuses
IN_PROGRESS = "in_progress"
CLOSED = "closed"
ESCALATED = "escalated"


@dataclass
class Verdict:
    """The verifier's judgement of the active phase's owned obligations."""

    ok: bool
    failing: str = ""
    detail: str = ""

    @classmethod
    def coerce(cls, v) -> "Verdict":
        if isinstance(v, cls):
            return v
        if not v:
            # A phase is active but no verdict was produced. That is not "pass":
            # it means we cannot confirm done, so it counts as red.
            return cls(
                ok=False,
                failing="verifier-did-not-run",
                detail="No verifier verdict was produced for the active phase.",
            )
        return cls(
            ok=bool(v.get("ok", False)),
            failing=str(v.get("failing", "")),
            detail=str(v.get("detail", "")),
        )


@dataclass
class Decision:
    action: str                       # ALLOW | BLOCK | ESCALATE
    reason: str = ""                  # fed back to the model on BLOCK
    message: str = ""                 # human/system note on ESCALATE
    state: dict = field(default_factory=dict)
    incident: Optional[dict] = None   # written to the append-only log by the caller


def _phase(state: dict, name: str) -> dict:
    phases = state.setdefault("phases", {})
    return phases.setdefault(
        name,
        {
            "attempt": 0,
            "budget": state.get("budget", config.DEFAULT_BUDGET),
            "status": IN_PROGRESS,
            "first_red_ts": None,
            "symptom": "",
        },
    )


def _incident(
    ph: dict,
    phase_name: str,
    resolution: str,
    fix_method: str,
    event: str,
    now_ts: float,
    session_id: str,
    uuid_factory: Callable[[], object],
) -> dict:
    """Assemble a complete Incident Record (spec §3.1).

    The record is only ever appended at resolution (green close or escalation),
    so the append-only log is never mutated — the in-flight incident is
    accumulated in `state` first, then written once, whole.
    """
    first = ph.get("first_red_ts")
    if first is None:
        first = now_ts
    ttr_minutes = int(round((now_ts - first) / 60.0))
    return {
        "id": str(uuid_factory()),
        "criterion_id": ph.get("symptom", "") or "unknown",
        "phase": phase_name,
        "symptom": ph.get("symptom", ""),
        "diagnosis": "",  # filled by the synthesizer / rework capture later
        "resolution": resolution,
        "fix_method": fix_method,
        "time_to_resolve": ttr_minutes,
        "cross_cutting": False,
        "project_specific": True,
        "created_at": datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat(),
        "attempts": ph.get("attempt", 0),
        "session_id": session_id or "",
        "event": event,
    }


def decide(
    state: Optional[dict],
    verdict,
    now_ts: float,
    session_id: str = "",
    uuid_factory: Callable[[], object] = uuid.uuid4,
) -> Decision:
    """Pure gate decision. Returns a Decision carrying the NEW state."""
    state = dict(state) if state else {}
    # deep-ish copy of the phases map so callers never see mutation of the input
    state["phases"] = {k: dict(v) for k, v in state.get("phases", {}).items()}

    active = state.get("active_phase")
    if not active:
        return Decision(ALLOW, state=state)

    ph = _phase(state, active)

    if ph["status"] in (CLOSED, ESCALATED):
        # Already resolved this phase — do not re-gate (the orchestrator moves
        # `active_phase` forward when the next phase opens).
        return Decision(ALLOW, state=state)

    v = Verdict.coerce(verdict)

    if v.ok:
        had_reds = ph["attempt"] > 0
        ph["status"] = CLOSED
        incident = None
        if had_reds:
            incident = _incident(
                ph, active, "verifier-passed", "real_fix",
                "phase_closed", now_ts, session_id, uuid_factory,
            )
        return Decision(ALLOW, state=state, incident=incident)

    # --- RED ---
    ph["attempt"] += 1
    if ph["first_red_ts"] is None:
        ph["first_red_ts"] = now_ts
        ph["symptom"] = v.failing or v.detail or "unspecified-failure"

    if ph["attempt"] <= ph["budget"]:
        reason = v.detail or v.failing or "Owned acceptance criteria are not yet green."
        return Decision(BLOCK, reason=reason, state=state)

    # attempt == budget + 1  ->  release the turn, escalate for a human
    ph["status"] = ESCALATED
    incident = _incident(
        ph, active, "escalated-pending-human", "unresolved",
        "escalated", now_ts, session_id, uuid_factory,
    )
    message = (
        f"Phase '{active}' exhausted its rework budget "
        f"({ph['budget']} attempts) and was released as escalated-pending-human."
    )
    return Decision(ESCALATE, message=message, state=state, incident=incident)
