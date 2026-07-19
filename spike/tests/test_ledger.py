"""Proof of the coverage-ledger logic — the pending/due/green state machine and,
above all, the cross-cutting false-green prevention (the "journal populates its
graph" regression made un-shippable).

    python spike/tests/test_ledger.py
    pytest spike/tests/test_ledger.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from keystone_gate.ledger import (  # noqa: E402
    DUE,
    GREEN,
    PENDING,
    completing_phase,
    criterion_status,
    is_cross_cutting,
    ledger_summary,
    owning_phases,
    phase_obligations,
    validate_coverage,
)

ORDER = ["P1", "P2", "P3"]

# A single-phase criterion and a cross-cutting one (spans P2 + P3).
SINGLE = {
    "id": "AC-1",
    "text": "password is hashed with bcrypt",
    "sub_obligations": [
        {"id": "a", "owning_phase": "P2", "proving_test": "t::hash"},
    ],
}
CROSS = {
    "id": "AC-2",
    "text": "journal entry populates the knowledge graph",
    "e2e_test": "t::journal_e2e",
    "sub_obligations": [
        {"id": "a", "owning_phase": "P2", "proving_test": "t::journal_write"},
        {"id": "b", "owning_phase": "P3", "proving_test": "t::graph_store"},
    ],
}
CRITERIA = [SINGLE, CROSS]


# --------------------------------------------------------------------------- #
# derived properties
# --------------------------------------------------------------------------- #
def test_owning_phases_and_cross_cutting():
    assert owning_phases(SINGLE) == {"P2"}
    assert owning_phases(CROSS) == {"P2", "P3"}
    assert not is_cross_cutting(SINGLE)
    assert is_cross_cutting(CROSS)


def test_completing_phase_is_last_owning_in_order():
    assert completing_phase(SINGLE, ORDER) == "P2"
    assert completing_phase(CROSS, ORDER) == "P3"          # last of {P2,P3} in order
    # order matters, not the sub-obligation listing order
    assert completing_phase(CROSS, ["P3", "P2", "P1"]) == "P2"


# --------------------------------------------------------------------------- #
# the status state machine
# --------------------------------------------------------------------------- #
def test_single_phase_pending_until_its_phase_completes():
    assert criterion_status(SINGLE, set(), set()) == PENDING
    assert criterion_status(SINGLE, {"P2"}, set()) == GREEN  # phase verifier checked it e2e


def test_cross_cutting_pending_until_all_phases_done():
    assert criterion_status(CROSS, set(), set()) == PENDING
    assert criterion_status(CROSS, {"P2"}, set()) == PENDING      # only one layer done
    assert criterion_status(CROSS, {"P2", "P3"}, set()) == DUE    # both done, not yet e2e


def test_cross_cutting_cannot_green_without_integration_verify():
    # THE load-bearing invariant: every layer green is NOT enough.
    both_done = {"P2", "P3"}
    assert criterion_status(CROSS, both_done, set()) == DUE
    assert criterion_status(CROSS, both_done, {"AC-2"}) == GREEN
    # and it can't skip straight to green while a layer is still missing
    assert criterion_status(CROSS, {"P2"}, {"AC-2"}) == PENDING


# --------------------------------------------------------------------------- #
# phase_obligations — the bridge to the gate/verifier
# --------------------------------------------------------------------------- #
def test_phase_obligations_owned_subs():
    obs = phase_obligations(CRITERIA, "P2", ORDER)
    ids = {o["id"] for o in obs}
    assert "AC-1/a" in ids            # single-phase sub owned by P2
    assert "AC-2/a" in ids            # cross-cutting sub owned by P2
    # P2 is NOT the completing phase for AC-2, so no e2e obligation here
    assert "AC-2::e2e" not in ids


def test_phase_obligations_fires_e2e_at_completing_phase():
    obs = phase_obligations(CRITERIA, "P3", ORDER)
    ids = {o["id"] for o in obs}
    assert "AC-2/b" in ids            # the P3 sub-obligation
    assert "AC-2::e2e" in ids         # e2e integration check becomes due at P3
    e2e = next(o for o in obs if o["id"] == "AC-2::e2e")
    assert e2e["kind"] == "integration"
    assert e2e["proving_test"] == "t::journal_e2e"


def test_phase_with_no_obligations_is_empty():
    assert phase_obligations(CRITERIA, "P1", ORDER) == []


# --------------------------------------------------------------------------- #
# validate_coverage — the Tier-1 approval gate
# --------------------------------------------------------------------------- #
def test_validate_clean_ledger_has_no_problems():
    assert validate_coverage(CRITERIA, ORDER) == []


def test_validate_flags_unowned_criterion():
    bad = [{"id": "AC-X", "text": "orphan", "sub_obligations": []}]
    problems = validate_coverage(bad, ORDER)
    assert any("unowned" in p for p in problems)


def test_validate_flags_missing_phase_and_test():
    bad = [{
        "id": "AC-Y",
        "sub_obligations": [
            {"id": "a", "owning_phase": "", "proving_test": ""},
            {"id": "b", "owning_phase": "P9", "proving_test": "t::x"},  # unknown phase
        ],
    }]
    problems = validate_coverage(bad, ORDER)
    assert any("no owning phase" in p for p in problems)
    assert any("no proving test" in p for p in problems)
    assert any("not in the phase decomposition" in p for p in problems)


def test_validate_flags_duplicate_ids():
    dup = [SINGLE, dict(SINGLE)]
    assert any("duplicate" in p for p in validate_coverage(dup, ORDER))


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def test_ledger_summary_counts_and_all_green():
    s0 = ledger_summary(CRITERIA, set(), set())
    assert s0["total"] == 2 and s0["pending"] == 2 and s0["cross_cutting"] == 1
    assert s0["all_green"] is False

    s1 = ledger_summary(CRITERIA, {"P2", "P3"}, {"AC-2"})
    assert s1["green"] == 2 and s1["all_green"] is True


# --------------------------------------------------------------------------- #
# smoke criteria — never auto-green on phase completion (the real-build-smoke fix)
# --------------------------------------------------------------------------- #
SMOKE = {"id": "AC-SMOKE-1", "text": "production build boots + real DB migrated", "smoke": True,
         "sub_obligations": [{"id": "a", "owning_phase": "P1", "proving_test": "t::smoke"}]}


def test_smoke_criterion_does_not_autogreen_on_phase_completion():
    # P1 complete but NOT smoke-verified -> DUE, never GREEN (unit tests can't reach the running system)
    assert criterion_status(SMOKE, {"P1"}, set()) == DUE
    assert criterion_status(SMOKE, {"P1"}, set(), smoke_verified={"AC-SMOKE-1"}) == GREEN
    # still pending before the phase completes at all
    assert criterion_status(SMOKE, set(), set(), smoke_verified={"AC-SMOKE-1"}) == PENDING


def test_smoke_and_cross_cutting_requires_BOTH_gates():
    crit = {"id": "AC-X", "smoke": True, "sub_obligations": [
        {"id": "a", "owning_phase": "P1", "proving_test": "t"},
        {"id": "b", "owning_phase": "P2", "proving_test": "t"}]}
    both = {"P1", "P2"}
    assert criterion_status(crit, both, set(), set()) == DUE
    assert criterion_status(crit, both, {"AC-X"}, set()) == DUE      # smoke still missing
    assert criterion_status(crit, both, set(), {"AC-X"}) == DUE      # integration still missing
    assert criterion_status(crit, both, {"AC-X"}, {"AC-X"}) == GREEN  # both gates pass


def test_ledger_summary_tracks_smoke_pending_and_blocks_all_green():
    crits = [SMOKE, {"id": "B", "sub_obligations": [{"id": "a", "owning_phase": "P1", "proving_test": "t"}]}]
    s = ledger_summary(crits, {"P1"}, set(), set())
    assert s["smoke"] == 1 and s["smoke_pending"] == 1 and s["all_green"] is False
    s2 = ledger_summary(crits, {"P1"}, set(), {"AC-SMOKE-1"})
    assert s2["smoke_pending"] == 0 and s2["all_green"] is True


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures.append(t.__name__)
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures.append(t.__name__)
            print(f"  ERROR {t.__name__}: {e!r}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
