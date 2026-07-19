"""Tests for the verdict-provider seam (hermetic — no live Claude session).

Covers the two things that must be right for the gate to trust a verdict:
parsing the verifier's output in every realistic shape, and failing CLOSED
(red) whenever the verifier can't produce a clean verdict.

    python spike/tests/test_verify.py
    pytest spike/tests/test_verify.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from keystone_gate.verify import (  # noqa: E402
    SubagentProvider,
    StaticFileProvider,
    build_verifier_prompt,
    get_provider,
    parse_verdict,
)


# --------------------------------------------------------------------------- #
# parse_verdict — every realistic output shape
# --------------------------------------------------------------------------- #
def test_parse_raw_json():
    v = parse_verdict('{"ok": true, "failing": "", "detail": "all green"}')
    assert v["ok"] is True and v["detail"] == "all green"


def test_parse_fenced_block_with_prose():
    text = 'Here is my verdict:\n```json\n{"ok": false, "failing": "AC1"}\n```\ndone.'
    v = parse_verdict(text)
    assert v["ok"] is False and v["failing"] == "AC1"


def test_parse_claude_output_format_json_envelope():
    envelope = json.dumps({
        "type": "result",
        "result": '{"ok": false, "failing": "AC2", "detail": "graph empty"}',
        "session_id": "x",
    })
    v = parse_verdict(envelope)
    assert v["ok"] is False and v["failing"] == "AC2" and "graph empty" in v["detail"]


def test_parse_prose_wrapped_object():
    v = parse_verdict('The tests fail. {"ok": false, "failing": "AC3"} Fix them.')
    assert v["ok"] is False and v["failing"] == "AC3"


def test_parse_garbage_returns_none():
    assert parse_verdict("no json here at all") is None
    assert parse_verdict("") is None
    assert parse_verdict('{"nope": 1}') is None  # no "ok" key -> not a verdict


def test_parse_normalizes_missing_fields():
    v = parse_verdict('{"ok": true}')
    assert v == {"ok": True, "failing": "", "detail": "", "obligations": []}


# --------------------------------------------------------------------------- #
# SubagentProvider — fail-closed contract
# --------------------------------------------------------------------------- #
def _root():
    return tempfile.mkdtemp()


def test_subagent_success_returns_and_persists_verdict():
    root = _root()
    good = '{"ok": true, "failing": "", "detail": "ok", "obligations": []}'
    prov = SubagentProvider(runner=lambda r, p: (0, good, ""))
    v = prov.produce(root, "p1", [{"id": "AC1", "text": "does X"}])
    assert v["ok"] is True
    # persisted to the seam for the audit trail
    written = json.loads((Path(root) / ".keystone" / "verdict.json").read_text(encoding="utf-8"))
    assert written["ok"] is True


def test_subagent_nonzero_exit_fails_closed():
    prov = SubagentProvider(runner=lambda r, p: (1, "", "boom"))
    v = prov.produce(_root(), "p1", [{"id": "AC1", "text": "x"}])
    assert v["ok"] is False and v["failing"] == "verifier-error"
    assert "1" in v["detail"] or "boom" in v["detail"]


def test_subagent_unparseable_output_fails_closed():
    prov = SubagentProvider(runner=lambda r, p: (0, "I could not run the tests, sorry", ""))
    v = prov.produce(_root(), "p1", [{"id": "AC1", "text": "x"}])
    assert v["ok"] is False and v["failing"] == "verifier-error"


def test_subagent_runner_raises_fails_closed():
    def boom(r, p):
        raise RuntimeError("claude not found")
    v = SubagentProvider(runner=boom).produce(_root(), "p1", [{"id": "AC1", "text": "x"}])
    assert v["ok"] is False and v["failing"] == "verifier-error"
    assert "claude not found" in v["detail"]


def test_subagent_red_verdict_passes_through():
    red = '{"ok": false, "failing": "AC1", "detail": "test asserts nothing"}'
    prov = SubagentProvider(runner=lambda r, p: (0, red, ""))
    v = prov.produce(_root(), "p1", [{"id": "AC1", "text": "x"}])
    assert v["ok"] is False and v["failing"] == "AC1"


# --------------------------------------------------------------------------- #
# prompt building + provider selection
# --------------------------------------------------------------------------- #
def test_prompt_includes_obligations_and_output_contract():
    p = build_verifier_prompt("phase-2", [{"id": "AC1", "text": "journal populates graph"}])
    assert "phase-2" in p
    assert "AC1" in p and "journal populates graph" in p
    assert '"ok"' in p  # the required output shape is spelled out


def test_prompt_flags_empty_obligations_as_fail():
    p = build_verifier_prompt("p1", [])
    assert "cannot certify nothing" in p


def test_get_provider_selection():
    assert get_provider({}).name == "static"
    assert get_provider({"KEYSTONE_VERIFIER": "static"}).name == "static"
    assert get_provider({"KEYSTONE_VERIFIER": "subagent"}).name == "subagent"
    assert get_provider({"KEYSTONE_VERIFIER": "SubAgent"}).name == "subagent"


def test_static_provider_reads_file_or_none():
    root = _root()
    assert StaticFileProvider().produce(root, "p1", []) is None
    (Path(root) / ".keystone").mkdir(parents=True)
    (Path(root) / ".keystone" / "verdict.json").write_text('{"ok": true}', encoding="utf-8")
    assert StaticFileProvider().produce(root, "p1", [])["ok"] is True


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
