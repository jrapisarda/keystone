# Installing Keystone

## The mental model: engine vs. runtime

Keystone has two kinds of pieces, and only one of them is per-project.

| | What | Where it can live |
|---|---|---|
| **Engine** (shareable) | hooks, the `keystone_gate` package, the six agents, the skills, the hook wiring | per-project **or** user-scope (once, for all projects) |
| **Runtime** (always per-project) | `.keystone/ledger.json`, `.keystone/state.json`, `.incidents/log.jsonl`, `IMPLEMENTATION_PLAN.md` | inside each project — a project's ledger is inherently its own |

So "install" only ever refers to the **engine**. The runtime is created by
`/keystone` when you actually run a build. This is why scaling to "install once"
works: the engine is identical everywhere; only the ledger differs.

**Prerequisites:** Python on `PATH`; the `memory` MCP server already registered
at user scope (it is). Nothing else.

---

## Mode A — per-project (start here, for the first dogfood)

Isolated and explicit. Copy the tree into the target project:

```bash
# from the target project root (e.g. mystical-aura-ai)
cp -r /c/testprojects/keystone/.claude/agents        .claude/agents
cp -r /c/testprojects/keystone/.claude/skills        .claude/skills
cp -r /c/testprojects/keystone/.claude/hooks         .claude/hooks
cp -r /c/testprojects/keystone/.claude/keystone_gate .claude/keystone_gate
# merge the hook map into the project's .claude/settings.json (see that file)
```

The project's `.claude/settings.json` hooks use `${CLAUDE_PROJECT_DIR}/.claude/...`,
so they resolve within the project. Verify: open Claude Code in the project and
run `python .claude/keystone_gate/cli.py --root . status` (it'll say the ledger
isn't built yet — that's correct until `/keystone` runs Tier 1).

Nothing engages until `/keystone` creates `.keystone/`. Safe to sit dormant.

---

## Mode B — user-scope (scale: install once, active everywhere)

Put the engine at user scope so **every** project can use it with no per-project
copy. The hooks stay **dormant in non-Keystone projects** (they no-op unless the
project has a `.keystone/` dir), so this is safe to turn on globally.

**1. Agents + skills → `~/.claude/` (symlink so repo updates propagate).**

```bash
# Windows (Developer Mode or admin) — mklink; or just copy if you prefer
cmd //c mklink /D "%USERPROFILE%\.claude\skills\keystone"          "C:\testprojects\keystone\.claude\skills\keystone"
cmd //c mklink /D "%USERPROFILE%\.claude\skills\incident-schema"   "C:\testprojects\keystone\.claude\skills\incident-schema"
cmd //c mklink /D "%USERPROFILE%\.claude\skills\adr-format"        "C:\testprojects\keystone\.claude\skills\adr-format"
cmd //c mklink /D "%USERPROFILE%\.claude\skills\test-conventions"  "C:\testprojects\keystone\.claude\skills\test-conventions"
# the six agents:
for a in verifier architect test-writer requirements-synthesizer researcher synthesizer; do
  cmd //c mklink "%USERPROFILE%\.claude\agents\$a.md" "C:\testprojects\keystone\.claude\agents\$a.md"
done
```

(Plain `cp` works too — you just re-copy after a repo update.)

**2. Hooks → merge into `~/.claude/settings.json`, pointing at the repo (absolute
paths, NOT `${CLAUDE_PROJECT_DIR}`).** The hook scripts read the invoking project's
`cwd` from their stdin payload, so they operate on the *current* project while
living once at the repo:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [
      {"type": "command", "command": "python \"C:/testprojects/keystone/.claude/hooks/session_start.py\"", "timeout": 20}]}],
    "PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash", "hooks": [
      {"type": "command", "command": "python \"C:/testprojects/keystone/.claude/hooks/config_guard.py\"", "timeout": 20}]}],
    "PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [
      {"type": "command", "command": "python \"C:/testprojects/keystone/.claude/hooks/post_edit.py\"", "timeout": 60}]}],
    "Stop": [{"hooks": [
      {"type": "command", "command": "python \"C:/testprojects/keystone/.claude/hooks/stop_gate.py\"", "timeout": 120}]}]
  }
}
```

> Merge these INTO your existing `~/.claude/settings.json` `hooks` object — do not
> overwrite the file (it holds your permissions/env). If a `hooks` key already
> exists, add these event arrays alongside what's there.

**Why this is safe globally** — dormancy is built in:

- **Stop gate** → allows the turn unless `.keystone/state.json` has an open phase.
- **config-guard** → returns clean unless the project has a `.keystone/` dir.
- **SessionStart / PostToolUse / pre-commit** → no-op without their `.keystone/*` inputs.

So in a normal, non-Keystone project you won't notice the hooks at all. They wake
up only where you've run `/keystone`.

---

## Recommended sequence

1. **Mode A into Aurelia** and run the first dogfood. Validate the loop end-to-end
   (and confirm the live verifier-subagent runner — ADR-0001's open item).
2. Once it's proven on one real project, **promote to Mode B** so you never install
   per-project again.

Don't make the hooks global until they've earned it on one project — that's the
same "validate before you trust it" discipline the workflow itself enforces.
