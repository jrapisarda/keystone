"""Proves the real Stop-hook I/O contract end to end.

Unlike test_gate_core (pure logic), this drives the actual entrypoint the way
Claude Code will: JSON on stdin, a `cwd` pointing at a scratch project, the
verdict + state on disk — and asserts the exact stdout decision shape plus the
side effects (state persisted, incident appended).

    python spike/tests/test_gate_hook.py
    pytest spike/tests/test_gate_hook.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / ".claude" / "hooks" / "stop_gate.py"


def _run(root: Path, payload: dict):
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"hook exited {proc.returncode}: {proc.stderr}"
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def _write(root: Path, rel: str, obj: dict):
    f = root / Path(*rel.split("/"))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(obj), encoding="utf-8")


def test_hook_blocks_on_red():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, ".keystone/state.json", {"active_phase": "p1", "budget": 3})
        _write(root, ".keystone/verdict.json",
               {"ok": False, "failing": "crit-A", "detail": "criterion A red"})

        out = _run(root, {"cwd": str(root), "session_id": "s1",
                          "stop_hook_active": False, "hook_event_name": "Stop"})

        assert out.get("decision") == "block"
        assert "criterion A red" in out.get("reason", "")
        # counter persisted for the next invocation
        state = json.loads((root / ".keystone" / "state.json").read_text(encoding="utf-8"))
        assert state["phases"]["p1"]["attempt"] == 1


def test_hook_allows_on_green_and_is_silent():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, ".keystone/state.json", {"active_phase": "p1", "budget": 3})
        _write(root, ".keystone/verdict.json", {"ok": True})

        out = _run(root, {"cwd": str(root), "session_id": "s1",
                          "stop_hook_active": False, "hook_event_name": "Stop"})

        assert out == {}, f"green should emit nothing, got {out!r}"


def test_hook_escalates_after_budget_and_writes_incident():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, ".keystone/state.json", {"active_phase": "p1", "budget": 2})
        _write(root, ".keystone/verdict.json",
               {"ok": False, "failing": "crit-A", "detail": "still red"})

        payload = {"cwd": str(root), "session_id": "s9",
                   "stop_hook_active": False, "hook_event_name": "Stop"}

        assert _run(root, payload).get("decision") == "block"   # attempt 1
        payload["stop_hook_active"] = True
        assert _run(root, payload).get("decision") == "block"   # attempt 2
        out = _run(root, payload)                               # attempt 3 -> escalate

        assert out.get("decision") != "block"
        assert out.get("continue") is True
        assert "escalated" in out.get("hookSpecificOutput", {}).get("additionalContext", "").lower()

        log = (root / ".incidents" / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(log) == 1, f"exactly one resolved incident expected, got {len(log)}"
        inc = json.loads(log[0])
        assert inc["resolution"] == "escalated-pending-human"
        assert inc["fix_method"] == "unresolved"
        assert inc["attempts"] == 3

        esc = (root / ".keystone" / "escalations.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(esc) == 1


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
