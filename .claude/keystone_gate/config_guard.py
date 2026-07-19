"""Config-conformance guard — static enforcement of fixed constants that mocked
tests never catch (WORKFLOW_SPEC §2.2, disease 3b).

The gate and verifier prove *behavior*; they do not catch a wrong *constant* —
a non-approved model id, or a Covered Model (Fable 5 / Mythos 5) written into
code where Zero-Data-Retention applies. Mocks mock those away. This guard scans
content on the WRITE path (a PreToolUse hook over Write/Edit/Bash) and blocks the
edit before it ever lands. Fail-closed, single source of truth for the allowlist.

The approved set + the ZDR flag are configurable in ONE place: `.keystone/models.json`
    { "approved": ["claude-opus-4-8", ...], "zdr": true }
falling back to the defaults below.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# The approved model set — the single source of truth (override in models.json).
DEFAULT_APPROVED = {
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
}

# Covered Models: ZDR-incompatible. Blocked when zdr is true, regardless of the
# allowlist (a hard constraint, not a preference).
COVERED_MODELS = {"claude-fable-5", "claude-mythos-5"}

# Match real Claude MODEL IDS only — the known families — so product/name strings
# like "claude-code", "claude-api", "claude.ai" do NOT false-positive.
CLAUDE_MODEL = re.compile(
    r"\bclaude-(?:opus|sonnet|haiku|fable|mythos|instant|\d)[a-z0-9]*(?:-[a-z0-9]+)*",
    re.IGNORECASE,
)


def load_policy(root: str) -> tuple[set, bool]:
    f = Path(root) / ".keystone" / "models.json"
    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))
        approved = {m.lower() for m in data.get("approved", DEFAULT_APPROVED)}
        zdr = bool(data.get("zdr", True))
        return approved, zdr
    return set(DEFAULT_APPROVED), True


def scan(text: str, approved: set | None = None, zdr: bool = True,
         covered: set = COVERED_MODELS) -> list:
    """Return a list of (model_id, reason) violations found in `text`."""
    if not text:
        return []
    approved = {m.lower() for m in (approved if approved is not None else DEFAULT_APPROVED)}
    covered = {m.lower() for m in covered}
    violations = []
    for token in {m.lower() for m in CLAUDE_MODEL.findall(text)}:
        if zdr and token in covered:
            violations.append((token, "covered-model-under-zdr"))
        elif token not in approved:
            violations.append((token, "non-approved-model"))
    return sorted(violations)


# Which tool inputs carry model-bearing content, and where.
def extract_text(tool_name: str, tool_input: dict) -> str:
    if not isinstance(tool_input, dict):
        return ""
    if tool_name in ("Write",):
        return str(tool_input.get("content", ""))
    if tool_name in ("Edit",):
        return str(tool_input.get("new_string", ""))
    if tool_name in ("MultiEdit",):
        return "\n".join(str(e.get("new_string", "")) for e in tool_input.get("edits", []))
    if tool_name in ("NotebookEdit",):
        return str(tool_input.get("new_source", ""))
    if tool_name in ("Bash",):
        return str(tool_input.get("command", ""))
    return ""


def is_keystone_project(root: str) -> bool:
    """A project opts into Keystone (and its guards) by having a `.keystone/` dir —
    created when `/keystone` runs Tier 1. This lets the hooks be installed at USER
    scope (active everywhere) while staying dormant in non-Keystone projects."""
    return (Path(root) / ".keystone").is_dir()


def check_tool_call(tool_name: str, tool_input: dict, root: str = ".") -> list:
    if not is_keystone_project(root):
        return []  # dormant outside Keystone projects — safe for a user-scope install
    approved, zdr = load_policy(root)
    return scan(extract_text(tool_name, tool_input), approved=approved, zdr=zdr)


def format_reason(violations: list) -> str:
    # Keep this message ASCII-only: it is written to stderr, which is cp1252 on
    # Windows consoles, where non-ASCII (an em-dash) mangles to a replacement char.
    lines = ["Config-conformance guard blocked this edit - disallowed model id(s):"]
    for model, reason in violations:
        if reason == "covered-model-under-zdr":
            lines.append(f"  - {model}: Covered Model (ZDR-incompatible) - not permitted here.")
        else:
            lines.append(f"  - {model}: not in the approved model set.")
    lines.append("Approved set is the single source of truth in .keystone/models.json.")
    return "\n".join(lines)
