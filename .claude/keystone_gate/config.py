"""Gate configuration — single source of truth for the tuning knobs."""

# Rework attempts that BLOCK before the gate releases-and-escalates.
# Attempts 1..N block; attempt N+1 releases the turn as escalated-pending-human.
DEFAULT_BUDGET = 3

# Relative paths inside a target project (the portable `.claude/` tree installs
# alongside these; state + logs are per-project runtime data).
STATE_DIR = ".keystone"
STATE_FILE = "state.json"
VERDICT_FILE = "verdict.json"          # spike verifier seam (real verifier replaces this)
INCIDENT_LOG = ".incidents/log.jsonl"  # append-only; synthesizer input only (spec §3.1)
ESCALATION_LOG = ".keystone/escalations.jsonl"
