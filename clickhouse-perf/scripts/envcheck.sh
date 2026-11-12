#!/usr/bin/env bash
# envcheck.sh RUN_ID : after `reset.sh faulted`, one regression replay (x4) as dashboard, judged by
# scripts/envcheck_verdict.py (rule v2: q23 excluded, totals within max(spread, 10 %), per query within C2's limit).
# Exit 0 = clean, 1 = not clean: do not start a run. Output: $OUT/envcheck/RUN_ID.json and .verdict.json,
# $OUT defaults to runs/ (gitignored). The reference is $REF/{baseline,post-fault}.json, default the recorded
# evidence/; a new reproduction with its own baseline sets REF=runs.
# The recorded evidence/envcheck/ files were written by rule v1 and are kept as they were (FINDINGS §4).
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -eq 1 ] || { echo "usage: $0 RUN_ID" >&2; exit 2; }
OUT=${OUT:-runs}; REF=${REF:-evidence}; mkdir -p "$OUT/envcheck"
python3 scripts/replay.py --creds ~/nerve-demo-private/v4/creds-operator.env --set regression --repeat 4 \
  --run-id "$1" --out "$OUT/envcheck/$1.json" | tail -1
python3 scripts/envcheck_verdict.py "$OUT/envcheck/$1.json" --ref "$REF" --out "$OUT/envcheck/$1.verdict.json"
