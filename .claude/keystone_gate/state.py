"""Keystone gate — the only module that touches the filesystem.

Everything here is thin I/O around JSON files rooted at the target project's
`cwd`. The interesting logic lives in `core.decide()`; this module just loads
what it needs, persists what changed, and appends resolved incidents.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config


def _path(root: str, rel: str) -> Path:
    return Path(root) / Path(*rel.split("/"))


def load_state(root: str) -> dict:
    f = _path(root, f"{config.STATE_DIR}/{config.STATE_FILE}")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def save_state(root: str, state: dict) -> None:
    f = _path(root, f"{config.STATE_DIR}/{config.STATE_FILE}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_verdict(root: str):
    """Spike verifier seam.

    Reads a verdict control file so tests (and the human, during a live spike)
    can drive red/green deterministically. The real verifier subagent replaces
    exactly this function — nothing else in the gate changes.
    """
    f = _path(root, f"{config.STATE_DIR}/{config.VERDICT_FILE}")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return None


def _append_jsonl(root: str, rel: str, record: dict) -> None:
    f = _path(root, rel)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_incident(root: str, incident: dict) -> None:
    _append_jsonl(root, config.INCIDENT_LOG, incident)


def append_escalation(root: str, incident: dict) -> None:
    _append_jsonl(root, config.ESCALATION_LOG, incident)
