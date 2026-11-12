#!/usr/bin/env bash
# render-prompts.sh: write runnable copies of sre-clickstack/prompts/*.md to sre-clickstack/prompts/local/ (gitignored).
#
# The files in prompts/ are kept exactly as the agents received them. They hard-code the incident timeline path of
# the original checkout ($HOME/Research/nerve-experiments/demo/evidence/timeline.log), which does not exist in a fresh
# clone. The copies point at the file that sregym_ctl.py actually writes: <this clone>/sre-clickstack/runs/timeline.log.
#
#   bash sre-clickstack/scripts/render-prompts.sh
set -euo pipefail
DEMO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$DEMO/prompts/local"
mkdir -p "$OUT"
for f in "$DEMO"/prompts/*.md; do
  sed "s|\$HOME/Research/nerve-experiments/demo/evidence/timeline.log|$DEMO/runs/timeline.log|g" "$f" > "$OUT/$(basename "$f")"
done
echo "rendered $(ls "$OUT" | wc -l | tr -d ' ') prompts into $OUT (timeline: $DEMO/runs/timeline.log)"
