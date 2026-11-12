#!/usr/bin/env bash
# negative_control.sh apply : case 10b, the fixed "plausible wrong fix" on the faulted state (no agent):
# a bloom_filter skip index on URL (a column the target filters do not use) + dashboard profile max_threads = 32.
set -euo pipefail
cd "$(dirname "$0")/.."
# New output goes to $OUT (default runs/, gitignored). evidence/ holds the recorded runs and is not written.
OUT=${OUT:-runs}; mkdir -p "$OUT/negative-control"
cat > $OUT/negative-control/applied.sql <<'SQL'
ALTER TABLE bench.hits ADD INDEX idx_url URL TYPE bloom_filter GRANULARITY 4;
ALTER TABLE bench.hits MATERIALIZE INDEX idx_url SETTINGS mutations_sync = 2;
ALTER SETTINGS PROFILE dashboard_profile SETTINGS max_execution_time = 600, max_threads = 32;
SQL
python3 scripts/apply_sql.py $OUT/negative-control/applied.sql --user nerve_rw
./scripts/state.sh
