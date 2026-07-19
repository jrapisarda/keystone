"""Tests for the ledger CLI — the deterministic ledger->state->gate bridge.

    python spike/tests/test_cli.py
    pytest spike/tests/test_cli.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from keystone_gate import cli  # noqa: E402

LEDGER = {
    "phase_order": ["P1", "P2", "P3"],
    "budget": 3,
    "completed_phases": [],
    "integration_verified": [],
    "criteria": [
        {"id": "AC-1", "text": "single", "sub_obligations": [
            {"id": "a", "owning_phase": "P2", "proving_test": "t::x"}]},
        {"id": "AC-2", "text": "cross", "e2e_test": "t::e2e", "sub_obligations": [
            {"id": "a", "owning_phase": "P2", "proving_test": "t::a"},
            {"id": "b", "owning_phase": "P3", "proving_test": "t::b"}]},
    ],
}


def _project():
    root = tempfile.mkdtemp()
    (Path(root) / ".keystone").mkdir()
    (Path(root) / ".keystone" / "ledger.json").write_text(json.dumps(LEDGER), encoding="utf-8")
    return root


def test_open_phase_writes_state_with_obligations():
    root = _project()
    cli.open_phase(root, "P3")
    state = json.loads((Path(root) / ".keystone" / "state.json").read_text(encoding="utf-8"))
    assert state["active_phase"] == "P3"
    ph = state["phases"]["P3"]
    assert ph["attempt"] == 0 and ph["status"] == "in_progress"
    ids = {o["id"] for o in ph["obligations"]}
    assert "AC-2/b" in ids and "AC-2::e2e" in ids   # P3 owns b AND completes AC-2's e2e


def test_open_unknown_phase_errors():
    root = _project()
    try:
        cli.open_phase(root, "P9")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_close_phase_advances_ledger_and_status():
    root = _project()
    cli.open_phase(root, "P2")
    cli.close_phase(root, "P2")
    # AC-1 (single, P2) is green; AC-2 (cross) still pending (P3 not done)
    s = cli.status(root)
    by = {c["id"]: c["status"] for c in s["criteria"]}
    assert by["AC-1"] == "green"
    assert by["AC-2"] == "pending"
    # active phase cleared
    state = json.loads((Path(root) / ".keystone" / "state.json").read_text(encoding="utf-8"))
    assert state["active_phase"] is None


def test_full_run_to_all_green_requires_e2e():
    root = _project()
    cli.open_phase(root, "P2"); cli.close_phase(root, "P2")
    cli.open_phase(root, "P3")
    # close P3 WITHOUT declaring the e2e verified -> AC-2 is only `due`, not green
    cli.close_phase(root, "P3")
    due = {c["id"]: c["status"] for c in cli.status(root)["criteria"]}
    assert due["AC-2"] == "due"
    assert cli.status(root)["summary"]["all_green"] is False
    # now record the integration verify -> green
    cli.close_phase(root, "P3", integration=["AC-2"])
    assert cli.status(root)["summary"]["all_green"] is True


def test_status_reports_coverage_problems():
    root = tempfile.mkdtemp()
    (Path(root) / ".keystone").mkdir()
    bad = dict(LEDGER, criteria=[{"id": "AC-9", "sub_obligations": []}])
    (Path(root) / ".keystone" / "ledger.json").write_text(json.dumps(bad), encoding="utf-8")
    assert any("unowned" in p for p in cli.status(root)["problems"])


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
