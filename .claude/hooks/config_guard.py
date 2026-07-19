#!/usr/bin/env python3
"""Config-conformance guard — PreToolUse entrypoint (WORKFLOW_SPEC §6.2).

Blocks a Write/Edit/Bash that would introduce a non-approved or Covered model id,
BEFORE it lands. Static enforcement of constants that mocked tests never catch.

Contract (PreToolUse):
  - stdin: JSON with tool_name, tool_input, cwd, ...
  - block:  exit 2, reason on stderr (fed back to the model)
  - allow:  exit 0

Wire in .claude/settings.json:
  "PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
                  "hooks": [{"type": "command",
                             "command": "python \"${CLAUDE_PROJECT_DIR}/.claude/hooks/config_guard.py\""}]}]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keystone_gate import config_guard as cg  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0  # can't parse — don't block on our own error

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    root = payload.get("cwd") or "."

    violations = cg.check_tool_call(tool_name, tool_input, root)
    if violations:
        sys.stderr.write(cg.format_reason(violations) + "\n")
        return 2  # block the tool call
    return 0


if __name__ == "__main__":
    sys.exit(main())
