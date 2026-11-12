#!/usr/bin/env bash
# inject.sh: the fault. Recreate bench.hits with the wrong sorting key ORDER BY (EventTime), swap it in, and drop
# the good copy from bench (the good state survives only in the hidden _snap.hits_good). Records the DDL.
set -euo pipefail
cd "$(dirname "$0")/.."
# New output goes to $OUT (default runs/, gitignored). evidence/ holds the recorded runs and is not written.
OUT=${OUT:-runs}; mkdir -p "$OUT/fault"
python3 - <<'PY' > $OUT/fault/hits_bad.sql
import re
s = open("scripts/create_hits.sql").read()
s = s[s.index("CREATE TABLE bench.hits"):]
s = s.replace("CREATE TABLE bench.hits", "CREATE TABLE bench.hits_bad", 1)
s = re.sub(r",\s*PRIMARY KEY \([^)]*\)\s*\)", "\n)", s)
s = s.replace("ENGINE = MergeTree", "ENGINE = MergeTree\nORDER BY (EventTime)", 1)
s = re.sub(r"--[^\n]*", "", s).strip().rstrip(";")
print(s + ";")
PY
{
  echo "-- fault injected $(date -u +%FT%TZ)"
  cat $OUT/fault/hits_bad.sql
  echo "INSERT INTO bench.hits_bad SELECT * FROM bench.hits;"
  echo "EXCHANGE TABLES bench.hits AND bench.hits_bad;"
  echo "DROP TABLE bench.hits_bad SYNC;   -- the good copy; it survives only in _snap.hits_good"
} > $OUT/fault/ddl.sql
./scripts/ch.sh "DROP TABLE IF EXISTS bench.hits_bad SYNC"
./scripts/ch.sh < $OUT/fault/hits_bad.sql
t0=$(date +%s)
./scripts/ch.sh "INSERT INTO bench.hits_bad SELECT * FROM bench.hits SETTINGS max_insert_threads = 4"
echo "insert_s=$(( $(date +%s) - t0 ))"
[ "$(./scripts/ch.sh 'SELECT count() FROM bench.hits_bad')" = "$(./scripts/ch.sh 'SELECT count() FROM bench.hits')" ]
./scripts/ch.sh "EXCHANGE TABLES bench.hits AND bench.hits_bad"
./scripts/ch.sh "DROP TABLE bench.hits_bad SYNC"
t0=$(date +%s); until [ "$(./scripts/ch.sh "SELECT count() FROM system.merges WHERE database='bench'")" = 0 ]; do sleep 10; done
echo "merge_wait_s=$(( $(date +%s) - t0 ))"
./scripts/state.sh
