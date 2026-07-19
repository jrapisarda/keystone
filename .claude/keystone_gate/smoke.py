"""Real-build smoke runner (WORKFLOW_SPEC §2.2, disease 4).

Catches runtime-only failures that unit/integration tests structurally cannot
reach: boot the real production build, hit the REAL api (not a mock), traverse a
specced non-happy-path. Inherently project-specific, so the commands live in
`.keystone/smoke.json`:

    { "commands": [ {"name": "build", "cmd": "npm run build"},
                    {"name": "boot",  "cmd": "node scripts/smoke.mjs"} ],
      "manual":   ["live camera capture"] }

The verifier invokes this for runtime-bearing phases; a failing command is a red
verdict. Genuinely un-automatable checks (e.g. live camera) are surfaced as
MANUAL and handed to the stakeholder — never silently passed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def load_config(root: str) -> dict:
    f = Path(root) / ".keystone" / "smoke.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def run_smoke(root: str, runner=None) -> dict:
    cfg = load_config(root)
    commands = cfg.get("commands", [])
    manual = cfg.get("manual", [])
    runner = runner or _default_runner

    results = []
    ok = True
    failing = ""
    for c in commands:
        name = c.get("name") or str(c.get("cmd", ""))[:24]
        try:
            rc, out, err = runner(root, c["cmd"])
        except Exception as e:  # noqa: BLE001
            rc, out, err = 1, "", repr(e)
        passed = rc == 0
        results.append({
            "name": name,
            "passed": passed,
            "detail": "" if passed else (err or out or "")[-300:],
        })
        if not passed and ok:
            ok, failing = False, name

    return {
        "ok": ok,
        "failing": failing,
        "detail": "" if ok else f"smoke check '{failing}' failed",
        "commands": results,
        "manual": manual,            # surfaced to the human, never auto-passed
        "needs_manual": bool(manual),
    }


def _default_runner(root, cmd):
    p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout, p.stderr
