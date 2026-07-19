"""Keystone ledger CLI — deterministic phase open/close + status.

Gives the orchestrator concrete commands instead of hand-editing JSON (fewer
errors, and the ledger→state→gate bridge is exercised the same way every time).

Reads `.keystone/ledger.json` — the machine-readable coverage ledger:

    {
      "phase_order": ["P1", "P2", "P3"],
      "budget": 3,
      "criteria": [ {"id","text","sub_obligations":[...],"e2e_test"?}, ... ],
      "completed_phases": [],
      "integration_verified": []
    }

Commands:
    open-phase  <P>            write .keystone/state.json so the gate verifies P's
                              owned + now-due obligations
    close-phase <P> [--integration AC-2 ...]
                              mark P complete (and any e2e criteria verified),
                              clear the active phase
    status                    ledger summary + coverage problems + per-criterion state

    python .claude/keystone_gate/cli.py --root . status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keystone_gate import ledger as L  # noqa: E402


def _kdir(root: str) -> Path:
    d = Path(root) / ".keystone"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_ledger(root: str) -> dict:
    return json.loads((_kdir(root) / "ledger.json").read_text(encoding="utf-8"))


def _save_ledger(root: str, led: dict) -> None:
    (_kdir(root) / "ledger.json").write_text(json.dumps(led, indent=2), encoding="utf-8")


def _save_state(root: str, state: dict) -> None:
    (_kdir(root) / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def open_phase(root: str, phase: str) -> list:
    led = _load_ledger(root)
    if phase not in led.get("phase_order", []):
        raise SystemExit(f"unknown phase '{phase}' (not in phase_order)")
    obligations = L.phase_obligations(led["criteria"], phase, led["phase_order"])
    budget = led.get("budget", 3)
    _save_state(root, {
        "active_phase": phase,
        "budget": budget,
        # provenance carried into state -> incidents (which feature/doc this is):
        "feature": led.get("feature", ""),
        "source_spec": led.get("source_spec", ""),
        "phases": {
            phase: {
                "attempt": 0,
                "budget": budget,
                "status": "in_progress",
                "first_red_ts": None,
                "symptom": "",
                "obligations": obligations,
            }
        },
    })
    return obligations


def close_phase(root: str, phase: str, integration=None) -> dict:
    led = _load_ledger(root)
    completed = set(led.get("completed_phases", []))
    completed.add(phase)
    led["completed_phases"] = sorted(completed)
    verified = set(led.get("integration_verified", []))
    verified.update(integration or [])
    led["integration_verified"] = sorted(verified)
    _save_ledger(root, led)

    state_file = _kdir(root) / "state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["active_phase"] = None
        if phase in state.get("phases", {}):
            state["phases"][phase]["status"] = "closed"
        _save_state(root, state)
    return led


def archive(root: str) -> str:
    """Feature complete (or switching features): move the active ledger to
    .keystone/archive/<feature>.ledger.json and clear the active run, so the next
    `/keystone <doc>` starts clean. Non-destructive — the ledger is preserved under
    its feature name (provenance). One active feature at a time."""
    led = _load_ledger(root)
    feature = led.get("feature") or "unnamed-feature"
    archive_dir = _kdir(root) / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{feature}.ledger.json"
    dest.write_text(json.dumps(led, indent=2), encoding="utf-8")
    for f in (_kdir(root) / "ledger.json", _kdir(root) / "state.json"):
        if f.exists():
            f.unlink()
    return str(dest)


def status(root: str) -> dict:
    led = _load_ledger(root)
    completed = set(led.get("completed_phases", []))
    verified = set(led.get("integration_verified", []))
    return {
        "feature": led.get("feature", ""),
        "source_spec": led.get("source_spec", ""),
        "summary": L.ledger_summary(led["criteria"], completed, verified),
        "problems": L.validate_coverage(led["criteria"], led.get("phase_order")),
        "criteria": [
            {
                "id": c["id"],
                "status": L.criterion_status(c, completed, verified),
                "cross_cutting": L.is_cross_cutting(c),
            }
            for c in led["criteria"]
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="keystone-ledger")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    op = sub.add_parser("open-phase")
    op.add_argument("phase")
    cp = sub.add_parser("close-phase")
    cp.add_argument("phase")
    cp.add_argument("--integration", nargs="*", default=[])
    sub.add_parser("archive")
    sub.add_parser("status")

    args = ap.parse_args(argv)
    if args.cmd == "open-phase":
        print(json.dumps(open_phase(args.root, args.phase), indent=2))
    elif args.cmd == "close-phase":
        close_phase(args.root, args.phase, args.integration)
        print(json.dumps(status(args.root), indent=2))
    elif args.cmd == "archive":
        print(f"archived -> {archive(args.root)}")
    else:
        print(json.dumps(status(args.root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
