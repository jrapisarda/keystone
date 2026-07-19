#!/usr/bin/env python3
"""PostToolUse hygiene hook — run a configured formatter after Write/Edit.

Non-blocking (always exit 0): formatting is hygiene, never a gate. Opt-in and
project-specific, so the command lives in `.keystone/hooks.json`:
    {"format_command": "npx prettier --write"}   # {file} is appended, or use {file}
No config -> no-op. This intentionally does nothing unless a project asks for it,
because running the wrong formatter is worse than running none.

    "PostToolUse": [{"matcher": "Write|Edit|MultiEdit",
      "hooks": [{"type": "command",
        "command": "python \"${CLAUDE_PROJECT_DIR}/.claude/hooks/post_edit.py\""}]}]
"""

import json
import shlex
import subprocess
import sys
from pathlib import Path


def build_command(root: str, file_path: str):
    cfg = Path(root) / ".keystone" / "hooks.json"
    if not (file_path and cfg.exists()):
        return None
    try:
        fmt = json.loads(cfg.read_text(encoding="utf-8")).get("format_command")
    except Exception:  # noqa: BLE001
        return None
    if not fmt:
        return None
    if "{file}" in fmt:
        return fmt.replace("{file}", shlex.quote(file_path))
    return f"{fmt} {shlex.quote(file_path)}"


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    root = payload.get("cwd") or "."
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    cmd = build_command(root, file_path)
    if cmd:
        try:
            subprocess.run(cmd, shell=True, cwd=root, capture_output=True, timeout=60)
        except Exception:  # noqa: BLE001
            pass  # hygiene never blocks
    return 0


if __name__ == "__main__":
    sys.exit(main())
