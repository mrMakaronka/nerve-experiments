#!/usr/bin/env bash
# demo-v3 bring-up: Langfuse + agent venv + splits + baselines + fault + post-fault. Idempotent per step.
#   bash agent-quality-langfuse/up.sh            # needs ANTHROPIC_API_KEY in agent-quality-langfuse/.env or the repo-root .env
#   STEP=fault bash agent-quality-langfuse/up.sh # re-run only from the fault step
set -euo pipefail
V3="$(cd "$(dirname "$0")" && pwd)"; cd "$V3"; PY="$V3/.venv/bin/python"; STEP="${STEP:-all}"
# New runs write under runs/ (gitignored); evidence/ holds the recorded runs and is never written here.
mkdir -p runs
log() { echo "$1 $(date -u +%FT%TZ)" >> runs/timeline.log; echo ">> $1"; }

if [[ "$STEP" == all ]]; then
  bash scripts/langfuse-up.sh
  [[ -x "$PY" ]] || uv venv -q .venv
  uv pip install -q -p .venv anthropic langfuse mcp matplotlib
  [[ -d ../vendor/bird/dev_20240627/dev_databases/superhero ]] || { echo "unpack BIRD dev into vendor/bird/dev_20240627 first (see README.md)"; exit 1; }
  "$PY" scripts/build_splits.py   # idempotent: compares tracked files, creates only what is missing
  for r in baseline baseline-2 baseline-3; do [[ -f runs/$r.json ]] || "$PY" agent/run.py experiment --run-name $r --workspace workspace; done
  [[ -f runs/oracle-baseline.json ]] || "$PY" agent/run.py oracle --label baseline --workspace workspace
  "$PY" scripts/fill_verifier.py                   # freezes runs/verifier.md from the 3 baselines
fi
log inject_start; "$PY" scripts/inject.py --kind rename; log inject_done
[[ -f runs/post-fault.json ]] || "$PY" agent/run.py experiment --run-name post-fault --workspace workspace
[[ -f runs/oracle-post-fault.json ]] || "$PY" agent/run.py oracle --label post-fault --workspace workspace
mkdir -p ~/nerve-v3-loops
[[ -d ~/nerve-v3-loops/run-b ]] || bash scripts/make_loop_repo.sh ~/nerve-v3-loops/run-b
[[ -d ~/nerve-v3-loops/run-c ]] || bash scripts/make_loop_repo.sh ~/nerve-v3-loops/run-c
echo "ready for Run B / Run C (README.md §3)"
