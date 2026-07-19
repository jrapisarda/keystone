"""Tests for the remaining enforcement hooks: SessionStart injection, pre-commit
close-integrity, PostToolUse formatter plumbing, and the smoke runner.

    python spike/tests/test_hooks.py
    pytest spike/tests/test_hooks.py
"""

import json
import sys
import tempfile
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[2] / ".claude"
sys.path.insert(0, str(CLAUDE))
sys.path.insert(0, str(CLAUDE / "hooks"))

import post_edit  # noqa: E402
import pre_commit  # noqa: E402
import session_start  # noqa: E402
from keystone_gate import smoke  # noqa: E402

LEDGER = {
    "phase_order": ["P1", "P2"],
    "budget": 3,
    "completed_phases": ["P1"],
    "integration_verified": [],
    "criteria": [
        {"id": "AC-1", "sub_obligations": [{"id": "a", "owning_phase": "P1", "proving_test": "t::x"}]},
        {"id": "AC-2", "sub_obligations": [{"id": "a", "owning_phase": "P2", "proving_test": "t::y"}]},
    ],
}


def _project(state=None):
    root = Path(tempfile.mkdtemp())
    (root / ".keystone").mkdir()
    (root / ".keystone" / "ledger.json").write_text(json.dumps(LEDGER), encoding="utf-8")
    if state is not None:
        (root / ".keystone" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return str(root)


# --------------------------------------------------------------------------- #
# SessionStart injection
# --------------------------------------------------------------------------- #
def test_session_start_none_without_ledger():
    assert session_start.build_context(tempfile.mkdtemp()) is None


def test_session_start_reports_ledger_and_active_phase():
    root = _project(state={"active_phase": "P2", "phases": {"P2": {"status": "in_progress"}}})
    ctx = session_start.build_context(root)
    assert "1/2 criteria green" in ctx          # P1 complete -> AC-1 green
    assert "Active phase: P2" in ctx and "gate is armed" in ctx


# --------------------------------------------------------------------------- #
# pre-commit close integrity
# --------------------------------------------------------------------------- #
def test_precommit_allows_when_no_active_phase():
    ok, _ = pre_commit.check(_project(state={"active_phase": None, "phases": {}}))
    assert ok is True


def test_precommit_blocks_in_progress_phase():
    ok, msg = pre_commit.check(_project(state={"active_phase": "P2", "phases": {"P2": {"status": "in_progress"}}}))
    assert ok is False and "in_progress" in msg


def test_precommit_allows_closed_phase():
    ok, _ = pre_commit.check(_project(state={"active_phase": "P2", "phases": {"P2": {"status": "closed"}}}))
    assert ok is True


def test_precommit_opt_out():
    root = _project(state={"active_phase": "P2", "phases": {"P2": {"status": "in_progress"}}})
    (Path(root) / ".keystone" / "hooks.json").write_text(
        json.dumps({"require_green_commit": False}), encoding="utf-8")
    ok, _ = pre_commit.check(root)
    assert ok is True


# --------------------------------------------------------------------------- #
# PostToolUse formatter plumbing
# --------------------------------------------------------------------------- #
def test_post_edit_noop_without_config():
    assert post_edit.build_command(tempfile.mkdtemp(), "a.ts") is None


def test_post_edit_builds_command_with_file():
    root = tempfile.mkdtemp()
    Path(root, ".keystone").mkdir()
    Path(root, ".keystone", "hooks.json").write_text(
        json.dumps({"format_command": "ruff format {file}"}), encoding="utf-8")
    cmd = post_edit.build_command(root, "lib/x.py")
    assert cmd.startswith("ruff format ") and "x.py" in cmd


# --------------------------------------------------------------------------- #
# smoke runner
# --------------------------------------------------------------------------- #
def _smoke_project(cfg):
    root = Path(tempfile.mkdtemp())
    (root / ".keystone").mkdir()
    (root / ".keystone" / "smoke.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(root)


def test_smoke_all_pass():
    root = _smoke_project({"commands": [{"name": "build", "cmd": "x"}, {"name": "boot", "cmd": "y"}]})
    r = smoke.run_smoke(root, runner=lambda rt, c: (0, "ok", ""))
    assert r["ok"] is True and r["failing"] == ""


def test_smoke_reports_first_failure():
    root = _smoke_project({"commands": [{"name": "build", "cmd": "x"}, {"name": "boot", "cmd": "y"}]})

    def runner(rt, c):
        return (0, "ok", "") if c == "x" else (1, "", "crashed on load")

    r = smoke.run_smoke(root, runner=runner)
    assert r["ok"] is False and r["failing"] == "boot"
    assert "crashed on load" in r["commands"][1]["detail"]


def test_smoke_surfaces_manual_not_silently_passed():
    root = _smoke_project({"commands": [], "manual": ["live camera capture"]})
    r = smoke.run_smoke(root, runner=lambda rt, c: (0, "", ""))
    assert r["needs_manual"] is True and "live camera capture" in r["manual"]


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
