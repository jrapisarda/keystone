#!/usr/bin/env python3
"""SessionStart hook — inject current ledger state as context (the SCAN step).

Non-blocking: emits a one-line ledger summary + active-phase note so a resumed
session picks up where the last one left off (resumability anchor, spec §5.3).
Global memory recall is already handled by the always-on distributed-memory
index; this adds the project-local ledger state on top.

    "SessionStart": [{"hooks": [{"type": "command",
      "command": "python \"${CLAUDE_PROJECT_DIR}/.claude/hooks/session_start.py\""}]}]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keystone_gate import cli  # noqa: E402


def build_context(root: str):
    led = Path(root) / ".keystone" / "ledger.json"
    if not led.exists():
        return None  # not a Keystone project, or not initialized yet
    try:
        st = cli.status(root)
    except Exception:  # noqa: BLE001
        return None
    s = st["summary"]
    parts = [
        f"Keystone ledger: {s['green']}/{s['total']} criteria green, "
        f"{s['due']} due, {s['pending']} pending ({s['cross_cutting']} cross-cutting)."
    ]
    state_file = Path(root) / ".keystone" / "state.json"
    if state_file.exists():
        try:
            sd = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            sd = {}
        active = sd.get("active_phase")
        if active:
            status = sd.get("phases", {}).get(active, {}).get("status", "in_progress")
            parts.append(f"Active phase: {active} ({status}); the gate is armed.")
    if st["problems"]:
        parts.append(f"{len(st['problems'])} coverage problem(s) open — see `cli.py status`.")
    return " ".join(parts)


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    ctx = build_context(payload.get("cwd") or ".")
    if ctx:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": ctx,
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
