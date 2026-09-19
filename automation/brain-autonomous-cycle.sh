#!/usr/bin/env bash
set -euo pipefail

ROOT="${MARKETHQ_REPO_ROOT:-/opt/markethq}"
PYTHON="${MARKETHQ_PYTHON:-$ROOT/.venv/bin/python}"
LOG_DIR="$ROOT/brain_operational_cycle_results"
mkdir -p "$LOG_DIR"

cd "$ROOT"

# The VPS timer owns scheduling. This wrapper runs the single research-only
# autonomous entrypoint; the Python cycle optionally calls the full Next.js
# orchestrator when MARKETHQ_AUTONOMOUS_ORCHESTRATOR_URL is configured.
# It never places broker orders, enables live execution, mutates the main repo,
# creates PRs, or merges code.
export MARKETHQ_AUTONOMOUS_CYCLE_SOURCE="tuemcloud-systemd"
export MARKETHQ_RESEARCH_ONLY="true"
export MARKETHQ_EXECUTION_ENABLED="false"

"$PYTHON" "$ROOT/brain_runtime_contract_v1.py"
exec "$PYTHON" "$ROOT/brain_operational_cycle_v1.py"
