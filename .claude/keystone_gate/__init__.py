"""Keystone gate — the Stop-hook enforcement core.

`core.decide()` is a pure, side-effect-free state machine; `state.py` is the
only module that touches the filesystem. This split is deliberate: the
load-bearing logic (does the gate block, release, or escalate?) is proven by
unit tests with no Claude Code session, subprocess, or disk in the loop.
"""

__all__ = ["core", "state", "config"]
