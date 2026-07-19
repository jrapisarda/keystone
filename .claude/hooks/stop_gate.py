#!/usr/bin/env python3
"""Keystone Stop-hook gate entrypoint.

Reads the Stop-hook JSON on stdin, consults gate state + the verifier verdict,
runs the pure `decide()` state machine, persists the new state and any resolved
incident, and emits the Claude Code Stop-hook decision on stdout.

Wire in .claude/settings.json:

    "hooks": {
      "Stop": [
        {"hooks": [
          {"type": "command",
           "command": "python \"${CLAUDE_PROJECT_DIR}/.claude/hooks/stop_gate.py\"",
           "timeout": 120}
        ]}
      ]
    }

Contract used (Stop hook):
  - stdin: JSON with session_id, cwd, stop_hook_active, ...
  - block turn-end:  print {"decision":"block","reason":...}   exit 0
  - allow turn-end:  no output                                 exit 0
"""

import json
import sys
import time
from pathlib import Path

# Make the portable `keystone_gate` package importable: it lives beside this
# hook inside the `.claude/` tree, so it travels with the tree when installed
# into any project.  parents[1] == the `.claude/` directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keystone_gate import state as st  # noqa: E402
from keystone_gate.core import ALLOW, BLOCK, ESCALATE, decide  # noqa: E402
from keystone_gate.verify import get_provider  # noqa: E402

# Absolute deadlock backstop: even if the durable counter is somehow reset
# mid-loop, never block past this many consecutive continuations.
HARD_CEILING = 12


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    root = payload.get("cwd") or "."
    session_id = payload.get("session_id", "")
    stop_hook_active = bool(payload.get("stop_hook_active", False))

    state = st.load_state(root)
    active = state.get("active_phase")

    # Dormant: no phase open -> nothing to gate, and nothing to persist. Return
    # WITHOUT writing anything. This is load-bearing for a user-scope install: the
    # Stop hook fires on every turn-end in every project, so it must not create
    # .keystone/ here, or it would silently mark every repo Keystone-managed (and
    # wake the config-guard everywhere).
    if not active:
        return 0

    # A phase is open — produce a FRESH verdict for this close attempt (the
    # provider selects static-file vs. verifier-subagent).
    phase = state.get("phases", {}).get(active, {})
    verdict = get_provider().produce(root, active, phase.get("obligations", []))

    decision = decide(state, verdict, now_ts=time.time(), session_id=session_id)

    # Deadlock backstop, independent of the per-phase budget.
    if decision.action == BLOCK and stop_hook_active:
        active = decision.state.get("active_phase")
        attempt = decision.state.get("phases", {}).get(active, {}).get("attempt", 0)
        if attempt >= HARD_CEILING:
            st.save_state(root, decision.state)
            print(json.dumps({
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": (
                        f"Gate hard-ceiling ({HARD_CEILING}) hit for phase "
                        f"'{active}'; releasing to avoid deadlock."
                    ),
                },
            }))
            return 0

    st.save_state(root, decision.state)
    if decision.incident:
        st.append_incident(root, decision.incident)
        if decision.action == ESCALATE:
            st.append_escalation(root, decision.incident)

    if decision.action == BLOCK:
        print(json.dumps({"decision": "block", "reason": decision.reason}))
        return 0

    if decision.action == ESCALATE:
        print(json.dumps({
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": decision.message,
            },
        }))
        return 0

    # ALLOW — say nothing, let the turn end.
    return 0


if __name__ == "__main__":
    sys.exit(main())
