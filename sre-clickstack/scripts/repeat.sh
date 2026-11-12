#!/usr/bin/env bash
# Unattended repeats of the demo-v1 fault (env_variable_shadowing_astronomy_shop):
#   N x [ clean baseline -> inject -> Run B -> oracle -> reset -> clean baseline -> inject -> Run C -> oracle -> reset ]
#
#   bash sre-clickstack/scripts/repeat.sh 3            # BASELINE_MIN=16 by default
#   RUN_ONLY=rep3-C:C bash sre-clickstack/scripts/repeat.sh   # re-run one run
#
# The clean wait is NOT shortened to 10 min: the frozen C1/C2 baseline is the 15 min before
# inject_done, so a shorter wait would put the previous incident inside the baseline window.
# Results: sre-clickstack/runs/repeats/results.csv (+ one folder per run); gitignored. The recorded repeats are in
# evidence/repeats/, which is not written.
set -uo pipefail
# Keep the Mac awake for the whole unattended run (idle sleep froze kind + load generator during Run C2).
# The assertion ends when this script exits.
if [[ -z "${REPEAT_CAFFEINATED:-}" ]] && command -v caffeinate >/dev/null; then
  REPEAT_CAFFEINATED=1 exec caffeinate -is "$0" "$@"
fi
N="${1:-3}"
BASELINE_MIN="${BASELINE_MIN:-16}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEMO="$ROOT/sre-clickstack"; SREGYM="$ROOT/vendor/SREGym"
OUT="$DEMO/runs/repeats"; WS="$DEMO/loop-workspace/repeats"
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:$HOME/.docker/bin:$PATH"
export DEMO_PROBLEM=env_variable_shadowing_astronomy_shop
mkdir -p "$OUT" "$WS"
# runnable prompt copies (the originals in prompts/ hard-code the original checkout's timeline path)
bash "$DEMO/scripts/render-prompts.sh" >/dev/null; P="$DEMO/prompts/local"
log() { printf '[%s] %s\n' "$(date -u '+%F %T')" "$*" | tee -a "$OUT/repeat.log"; }
ctl() { (cd "$SREGYM" && uv run python "$DEMO/scripts/sregym_ctl.py" "$@"); }

wait_healthy() {  # all astronomy-shop pods Ready, max 10 min
  for _ in $(seq 1 60); do
    bad=$(kubectl --context kind-kind -n astronomy-shop get pods --no-headers 2>/dev/null |
          awk '{split($2,a,"/"); if (a[1]!=a[2] || ($3!="Running" && $3!="Completed")) print $1}')
    [[ -z "$bad" ]] && return 0
    sleep 10
  done
  log "WARN: pods not healthy after 10 min: $bad"
}

one_run() {  # $1=run_id $2=kind(B|C)
  local id="$1" kind="$2" dir="$OUT/$1" cwd="$WS/$1"
  mkdir -p "$dir" "$cwd"
  wait_healthy
  log "$id: clean baseline ${BASELINE_MIN} min"
  sleep $((BASELINE_MIN * 60))
  log "$id: inject"
  ctl inject > "$dir/inject.log" 2>&1 || log "$id: inject returned non-zero (see inject.log)"
  # Refresh right before the loop: Claude Code rotates the Keychain token and revokes the old one
  # (rep3-C, first attempt, failed with "OAuth token revoked" after a refresh 16 min earlier).
  bash "$DEMO/scripts/refresh_claude_token.sh" | sed 's/^/  /' | tee -a "$OUT/repeat.log"
  if [[ "$kind" == B ]]; then
    python3 "$DEMO/scripts/nerve_api.py" loop --title "Repeat $id (closed loop)" \
      --goal-file "$P/run-b-goal.md" --verifier-file "$P/run-b-verifier.md" \
      --budget 8 --max-iterations 3 --cwd "$cwd" --out "$dir" --wait > "$dir/loop.log" 2>&1
  else
    python3 "$DEMO/scripts/nerve_api.py" loop --title "Repeat $id (restart-only)" \
      --goal-file "$P/run-c-goal.md" --verifier-file "$P/run-b-verifier.md" \
      --budget 4 --max-iterations 1 --cwd "$cwd" --out "$dir" --wait --abandon-on-park > "$dir/loop.log" 2>&1
  fi
  log "$id: loop settled ($(tail -1 "$dir/loop.log"))"
  ctl oracle > "$dir/sregym-oracle.txt" 2>&1
  log "$id: oracle $(grep -o '"success": [a-z]*' "$dir/sregym-oracle.txt" | head -1)"
  python3 "$DEMO/scripts/repeat_row.py" --run-id "$id" --kind "$kind" --dir "$dir" >> "$OUT/repeat.log" 2>&1 \
    || log "$id: repeat_row failed"
  ctl recover >> "$dir/recover.log" 2>&1 || log "$id: recover returned non-zero"
  kubectl --context kind-kind -n astronomy-shop rollout status deploy/frontend-proxy --timeout=300s >/dev/null 2>&1
}

log "repeat.sh start: N=$N baseline=${BASELINE_MIN}min problem=$DEMO_PROBLEM ${RUN_ONLY:+only=$RUN_ONLY}"
if [[ -n "${RUN_ONLY:-}" ]]; then   # RUN_ONLY=rep3-C:C re-runs a single run
  one_run "${RUN_ONLY%%:*}" "${RUN_ONLY##*:}"
  python3 "$DEMO/scripts/summarize_repeats.py" >> "$OUT/repeat.log" 2>&1 || log "summarize failed"
  log "repeat.sh done"; exit 0
fi
for i in $(seq 1 "$N"); do
  one_run "rep$i-B" B
  one_run "rep$i-C" C
done
python3 "$DEMO/scripts/summarize_repeats.py" >> "$OUT/repeat.log" 2>&1 || log "summarize failed"
log "repeat.sh done"
