#!/usr/bin/env bash
# Load ClickBench hits (100 partitioned parquet files, 99 997 497 rows) into bench.hits (official DDL).
set -euo pipefail
cd "$(dirname "$0")"
./ch.sh "DROP TABLE IF EXISTS bench.hits SYNC"
python3 apply_sql.py create_hits.sql
t0=$(date +%s)
./ch.sh "INSERT INTO bench.hits SELECT * FROM file('clickbench/hits_*.parquet') SETTINGS max_insert_threads = 4"
echo "load_s=$(( $(date +%s) - t0 ))"
./ch.sh "SELECT count(), formatReadableSize(sum(bytes_on_disk)), count() FROM system.parts WHERE database='bench' AND table='hits' AND active" 
