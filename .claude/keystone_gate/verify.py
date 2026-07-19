"""Verdict providers — the swappable seam between the gate and the verifier.

The gate (`core.decide`) only needs a verdict dict `{ok, failing, detail}`.
*How* that verdict is produced is deliberately behind an interface, so the
risky, environment-specific part — invoking the independent verifier subagent
— is isolated, swappable, and **fails closed**. Two providers ship:

  - StaticFileProvider : reads .keystone/verdict.json (tests, manual spikes, or
                         a verdict pre-supplied by another hook). Zero cost.
  - SubagentProvider   : invokes the `verifier` subagent, parses its structured
                         verdict, writes it to the seam for the audit trail.

Select with env `KEYSTONE_VERIFIER` = static | subagent  (default: static).

Why a command provider and not the native `type:"agent"` Stop handler yet: the
agent-handler is currently experimental, whereas shelling out is stable today.
The whole point of this interface is that swapping to the native handler later
touches ONE function (`_default_runner`) and nothing else. See
docs/adr-0001-verifier-seam.md.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from . import config
from . import state as st

# A verdict we could not produce is RED, never a silent pass (Principle 1).
FAIL_CLOSED = {
    "ok": False,
    "failing": "verifier-error",
    "detail": "The verifier could not produce a verdict; failing closed.",
    "obligations": [],
}


def get_provider(env=None):
    env = env if env is not None else os.environ
    kind = (env.get("KEYSTONE_VERIFIER") or "static").strip().lower()
    if kind == "subagent":
        return SubagentProvider()
    return StaticFileProvider()


class StaticFileProvider:
    """Reads a verdict from disk. Used by tests, manual spikes, and any setup
    where another step already produced the verdict."""

    name = "static"

    def produce(self, root, phase, obligations):
        return st.load_verdict(root)  # may be None -> decide() treats as red


class SubagentProvider:
    """Invokes the independent verifier subagent and returns its verdict.

    `runner(root, prompt) -> (returncode, stdout, stderr)` is injectable so the
    parsing / fail-closed / prompt logic is testable without a live session.
    """

    name = "subagent"

    def __init__(self, runner=None):
        self._runner = runner or _default_runner

    def produce(self, root, phase, obligations):
        prompt = build_verifier_prompt(phase, obligations)
        try:
            rc, out, err = self._runner(root, prompt)
        except Exception as e:  # noqa: BLE001 — any failure is a red, not a crash
            return dict(FAIL_CLOSED, detail=f"verifier invocation raised: {e!r}")
        if rc != 0:
            return dict(FAIL_CLOSED, detail=f"verifier exited {rc}: {(err or '')[:500]}")
        verdict = parse_verdict(out)
        if verdict is None:
            return dict(FAIL_CLOSED, detail="verifier output was not parseable JSON")
        _write_verdict(root, verdict)  # audit trail; also feeds incident `detail`
        return verdict


def build_verifier_prompt(phase, obligations) -> str:
    lines = [
        f"You are adjudicating phase '{phase}' at the Keystone gate.",
        "Independently verify whether EVERY owned sub-obligation below genuinely",
        "passes. Run the tests yourself; inspect for stubs, weakened tests, and",
        "wrong constants. Do not trust any reported result — reproduce it.",
        "",
        "Owned sub-obligations:",
    ]
    for o in obligations or []:
        lines.append(f"  - [{o.get('id', '?')}] {o.get('text', '')}")
    if not obligations:
        lines.append("  (none supplied — this itself is a fail: you cannot certify nothing)")
    lines += [
        "",
        "Return ONLY the JSON verdict object, no prose:",
        '{"ok": <bool>, "failing": "<first failing id or empty>", '
        '"detail": "<concrete, actionable>", '
        '"obligations": [{"id": "<id>", "pass": <bool>, "evidence": "<observed>"}]}',
    ]
    return "\n".join(lines)


def parse_verdict(text):
    """Extract a verdict dict from verifier output.

    Tolerant of: raw JSON, ```json fenced blocks, prose around the object, and
    the `claude -p --output-format json` envelope (verdict nested in `result`).
    Returns None if nothing verdict-shaped is found.
    """
    def _try(s, depth=0):
        if not s or depth > 3:
            return None
        for cand in _json_candidates(s):
            try:
                d = json.loads(cand)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(d, dict):
                if "ok" in d:
                    return _normalize(d)
                # claude CLI envelope: {"type":"result","result":"<text>", ...}
                inner = d.get("result")
                if isinstance(inner, str):
                    r = _try(inner, depth + 1)
                    if r:
                        return r
        return None

    return _try(text)


def _normalize(d):
    return {
        "ok": bool(d.get("ok", False)),
        "failing": str(d.get("failing", "")),
        "detail": str(d.get("detail", "")),
        "obligations": d.get("obligations", []) or [],
    }


def _json_candidates(text):
    text = (text or "").strip()
    if not text:
        return
    yield text
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        yield m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        yield text[start:end + 1]


def _default_runner(root, prompt):
    """Invoke the verifier via the Claude CLI.

    NOTE (single point of live uncertainty): the exact flag to FORCE the
    `verifier` subagent is confirmed only against a live session. It is kept
    here, in one place, so correcting it is a one-line change; everything above
    fails closed if this returns non-zero or unparseable output.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    proc = subprocess.run(
        cmd, cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=110
    )
    return proc.returncode, proc.stdout, proc.stderr


def _write_verdict(root, verdict):
    f = Path(root) / config.STATE_DIR / config.VERDICT_FILE
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
