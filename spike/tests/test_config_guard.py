"""Tests for the config-conformance guard — the wrong-constant disease (3b).

    python spike/tests/test_config_guard.py
    pytest spike/tests/test_config_guard.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from keystone_gate import config_guard as cg  # noqa: E402

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "config_guard.py"


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #
def test_approved_model_passes():
    assert cg.scan('const MODEL = "claude-opus-4-8";') == []


def test_non_approved_model_flagged():
    v = cg.scan('model: "claude-opus-3-5"')
    assert v == [("claude-opus-3-5", "non-approved-model")]


def test_covered_model_blocked_under_zdr():
    v = cg.scan('model = "claude-fable-5"', zdr=True)
    assert v == [("claude-fable-5", "covered-model-under-zdr")]


def test_covered_model_allowed_when_in_approved_and_no_zdr():
    approved = cg.DEFAULT_APPROVED | {"claude-fable-5"}
    assert cg.scan('claude-fable-5', approved=approved, zdr=False) == []


def test_covered_model_still_flagged_if_not_approved_even_without_zdr():
    # zdr off, but fable isn't in the default approved set -> non-approved
    assert cg.scan('claude-fable-5', zdr=False) == [("claude-fable-5", "non-approved-model")]


def test_product_names_do_not_false_positive():
    text = "Install claude-code; see claude.ai/code and the claude-api skill. // claude-agent-sdk"
    assert cg.scan(text) == []


def test_multiple_and_dedup():
    text = 'a="claude-opus-4-8"; b="claude-sonnet-2"; c="claude-sonnet-2"'
    v = cg.scan(text)
    assert v == [("claude-sonnet-2", "non-approved-model")]  # opus-4-8 ok, sonnet-2 once


def test_policy_override_from_models_json():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".keystone").mkdir()
        (root / ".keystone" / "models.json").write_text(
            json.dumps({"approved": ["claude-haiku-4-5"], "zdr": False}), encoding="utf-8")
        approved, zdr = cg.load_policy(str(root))
        assert approved == {"claude-haiku-4-5"} and zdr is False
        # opus is no longer approved under this project policy
        assert cg.scan("claude-opus-4-8", approved=approved, zdr=zdr) == \
            [("claude-opus-4-8", "non-approved-model")]


# --------------------------------------------------------------------------- #
# extract_text per tool
# --------------------------------------------------------------------------- #
def test_extract_text_per_tool():
    assert "x" in cg.extract_text("Write", {"content": "x"})
    assert "y" in cg.extract_text("Edit", {"new_string": "y"})
    assert "z" in cg.extract_text("Bash", {"command": "z"})
    assert cg.extract_text("Read", {"file_path": "f"}) == ""       # non-mutating tool


# --------------------------------------------------------------------------- #
# hook entrypoint (real exit codes)
# --------------------------------------------------------------------------- #
def _run(payload):
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True)


def test_hook_blocks_write_with_bad_model():
    p = _run({"tool_name": "Write", "tool_input": {"content": 'm="claude-opus-9-9"'}, "cwd": "."})
    assert p.returncode == 2
    assert "claude-opus-9-9" in p.stderr


def test_hook_allows_write_with_approved_model():
    p = _run({"tool_name": "Write", "tool_input": {"content": 'm="claude-opus-4-8"'}, "cwd": "."})
    assert p.returncode == 0 and p.stderr == ""


def test_hook_blocks_bash_calling_bad_model():
    p = _run({"tool_name": "Bash", "tool_input": {"command": 'claude -p --model claude-fable-5 hi'}, "cwd": "."})
    assert p.returncode == 2
    assert "claude-fable-5" in p.stderr


def test_hook_ignores_non_mutating_tool():
    p = _run({"tool_name": "Read", "tool_input": {"file_path": "claude-fable-5.txt"}, "cwd": "."})
    assert p.returncode == 0


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
