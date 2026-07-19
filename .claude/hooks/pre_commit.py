#!/usr/bin/env python3
"""Keystone pre-commit check — don't commit an un-verified phase (spec §6.2).

Close integrity: a phase is committed only AFTER the gate greens it (Tier-2
step 7), so at commit time the active phase must be closed (or there is no active
phase). If a phase is still `in_progress`, this blocks the commit — you'd be
committing work the gate never certified. Escalated phases ARE allowed to commit
(the escalation is the honest record).

Opt out per project with `.keystone/hooks.json`: {"require_green_commit": false}.

Install as a git hook:  cp .claude/hooks/pre_commit.py .git/hooks/pre-commit
(or call it from an existing pre-commit). Exits 1 to block the commit.
"""

import json
import sys
from pathlib import Path


def check(root: str):
    """Return (ok, message). ok=False blocks the commit."""
    hooks_cfg = Path(root) / ".keystone" / "hooks.json"
    if hooks_cfg.exists():
        try:
            if json.loads(hooks_cfg.read_text(encoding="utf-8")).get("require_green_commit", True) is False:
                return True, ""
        except Exception:  # noqa: BLE001
            pass

    state_file = Path(root) / ".keystone" / "state.json"
    if not state_file.exists():
        return True, ""
    try:
        sd = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return True, ""

    active = sd.get("active_phase")
    if not active:
        return True, ""
    status = sd.get("phases", {}).get(active, {}).get("status", "in_progress")
    if status == "in_progress":
        return False, (
            f"Keystone: phase '{active}' is still in_progress — the gate has not "
            f"certified it. Let the verifier green it before committing, or "
            f"opt out with .keystone/hooks.json require_green_commit=false."
        )
    return True, ""


def main() -> int:
    ok, message = check(".")
    if not ok:
        sys.stderr.write(message + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
