"""Deterministic proof of the gate state machine — the spike's core deliverable.

These tests answer the one open empirical question: *does the mechanism hold?*
They exercise `decide()` with no session, no subprocess, no disk — just the pure
function and an injected clock/uuid — so every branch of block / release /
escalate is proven exhaustively and reproducibly.

Runnable two ways:
    python spike/tests/test_gate_core.py      # zero-dependency self-runner
    pytest spike/tests/test_gate_core.py      # standard collection
"""

import sys
from pathlib import Path

# Import the portable package from the `.claude/` tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from keystone_gate.core import (  # noqa: E402
    ALLOW,
    BLOCK,
    CLOSED,
    ESCALATE,
    ESCALATED,
    IN_PROGRESS,
    decide,
)

T0 = 1_000_000.0            # base timestamp (seconds)
MIN = 60.0                  # one minute
COUNTER = {"n": 0}


def _uuid():
    COUNTER["n"] += 1
    return f"uuid-{COUNTER['n']}"


def red(failing="crit-A green?", detail="criterion A is not satisfied"):
    return {"ok": False, "failing": failing, "detail": detail}


def green():
    return {"ok": True}


# --------------------------------------------------------------------------- #
# 1. Normal turns are never gated.
# --------------------------------------------------------------------------- #
def test_no_active_phase_allows():
    d = decide({}, red(), now_ts=T0)
    assert d.action == ALLOW
    assert d.incident is None


def test_active_phase_none_allows_even_with_red_verdict():
    d = decide({"active_phase": None}, red(), now_ts=T0)
    assert d.action == ALLOW


# --------------------------------------------------------------------------- #
# 2. Green on the first check: allow, close, no incident (no stop ever happened).
# --------------------------------------------------------------------------- #
def test_green_first_try_closes_without_incident():
    d = decide({"active_phase": "p1"}, green(), now_ts=T0)
    assert d.action == ALLOW
    assert d.incident is None
    assert d.state["phases"]["p1"]["status"] == CLOSED


# --------------------------------------------------------------------------- #
# 3. A single red within budget blocks and hands back the reason.
# --------------------------------------------------------------------------- #
def test_single_red_blocks_with_reason():
    d = decide({"active_phase": "p1"}, red(detail="tests red: journal graph empty"),
               now_ts=T0)
    assert d.action == BLOCK
    assert "journal graph empty" in d.reason
    ph = d.state["phases"]["p1"]
    assert ph["attempt"] == 1
    assert ph["status"] == IN_PROGRESS
    assert d.incident is None            # not resolved yet -> nothing logged


def test_missing_verdict_counts_as_red():
    d = decide({"active_phase": "p1"}, None, now_ts=T0)
    assert d.action == BLOCK
    assert "verifier-did-not-run" in d.reason or "verifier" in d.reason.lower()


# --------------------------------------------------------------------------- #
# 4. The full arc across successive stops — the money test.
#    Proves the DURABLE counter: state is threaded call-to-call exactly as the
#    hook would persist and reload it between Stop invocations.
# --------------------------------------------------------------------------- #
def test_block_block_block_then_escalate():
    state = {"active_phase": "p1", "budget": 3}
    # three reds -> three blocks
    for i in range(1, 4):
        d = decide(state, red(), now_ts=T0 + i * MIN, session_id="s1", uuid_factory=_uuid)
        assert d.action == BLOCK, f"attempt {i} should block"
        assert d.state["phases"]["p1"]["attempt"] == i
        assert d.incident is None
        state = d.state

    # fourth red (budget+1) -> release + escalate, exactly one incident
    d = decide(state, red(), now_ts=T0 + 4 * MIN, session_id="s1", uuid_factory=_uuid)
    assert d.action == ESCALATE
    assert d.state["phases"]["p1"]["status"] == ESCALATED
    inc = d.incident
    assert inc is not None
    assert inc["event"] == "escalated"
    assert inc["resolution"] == "escalated-pending-human"
    assert inc["fix_method"] == "unresolved"
    assert inc["attempts"] == 4
    assert inc["phase"] == "p1"
    assert inc["session_id"] == "s1"
    # first red at T0+1min, escalation at T0+4min -> 3 minutes
    assert inc["time_to_resolve"] == 3


def test_incident_carries_feature_provenance():
    state = {"active_phase": "p1", "budget": 1, "feature": "aurelia-astrology"}
    state = decide(state, red(), now_ts=T0).state          # attempt 1 -> block
    d = decide(state, red(), now_ts=T0 + MIN)              # attempt 2 -> escalate + incident
    assert d.incident is not None
    assert d.incident["feature"] == "aurelia-astrology"    # provenance at scale


def test_escalated_phase_is_not_regated():
    state = {"active_phase": "p1", "budget": 1}
    state = decide(state, red(), now_ts=T0).state          # attempt 1 -> block
    state = decide(state, red(), now_ts=T0).state          # attempt 2 -> escalate
    assert state["phases"]["p1"]["status"] == ESCALATED
    d = decide(state, red(), now_ts=T0)                    # further stops pass through
    assert d.action == ALLOW
    assert d.incident is None


# --------------------------------------------------------------------------- #
# 5. Rework that actually fixes the problem: red -> green closes with an incident
#    that records the resolution and how long it took.
# --------------------------------------------------------------------------- #
def test_red_then_green_closes_with_resolved_incident():
    state = {"active_phase": "p1", "budget": 3}
    d = decide(state, red(failing="crit-A"), now_ts=T0 + 1 * MIN,
               session_id="s2", uuid_factory=_uuid)
    assert d.action == BLOCK
    state = d.state

    d = decide(state, green(), now_ts=T0 + 3 * MIN, session_id="s2", uuid_factory=_uuid)
    assert d.action == ALLOW
    assert d.state["phases"]["p1"]["status"] == CLOSED
    inc = d.incident
    assert inc is not None
    assert inc["event"] == "phase_closed"
    assert inc["resolution"] == "verifier-passed"
    assert inc["fix_method"] == "real_fix"
    assert inc["symptom"] == "crit-A"           # captured from the first red
    assert inc["attempts"] == 1
    assert inc["time_to_resolve"] == 2          # T0+1min red -> T0+3min green


def test_two_reds_then_green_within_budget():
    state = {"active_phase": "p1", "budget": 3}
    for i in range(1, 3):
        d = decide(state, red(), now_ts=T0 + i * MIN)
        assert d.action == BLOCK
        state = d.state
    d = decide(state, green(), now_ts=T0 + 3 * MIN)
    assert d.action == ALLOW
    assert d.incident["attempts"] == 2
    assert d.state["phases"]["p1"]["status"] == CLOSED


# --------------------------------------------------------------------------- #
# 6. Input is never mutated (pure function contract).
# --------------------------------------------------------------------------- #
def test_input_state_not_mutated():
    original = {"active_phase": "p1", "budget": 3}
    decide(original, red(), now_ts=T0)
    assert original == {"active_phase": "p1", "budget": 3}
    assert "phases" not in original


# --------------------------------------------------------------------------- #
# Zero-dependency self-runner.
# --------------------------------------------------------------------------- #
def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = []
    for t in tests:
        COUNTER["n"] = 0
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures.append((t.__name__, e))
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures.append((t.__name__, e))
            print(f"  ERROR {t.__name__}: {e!r}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run())
