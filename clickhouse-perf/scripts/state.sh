#!/usr/bin/env bash
# state.sh [db.table]: fingerprint of a table state: DDL hash, rows, active parts, bytes, multiset hash of part contents,
# plus projections, skip indexes, extra tables in bench, and dashboard's profile. Used to prove Run C starts from the faulted snapshot.
set -euo pipefail
cd "$(dirname "$0")"; t=${1:-bench.hits}; db=${t%%.*}; tb=${t#*.}
ddl=$(./ch.sh "SELECT replaceRegexpOne(create_table_query, '^CREATE TABLE [^ ]+ ', '') FROM system.tables WHERE database='$db' AND name='$tb'")
echo "ddl_sha256=$(printf %s "$ddl" | shasum -a 256 | cut -c1-16)"
echo "sorting_key=$(./ch.sh "SELECT sorting_key FROM system.tables WHERE database='$db' AND name='$tb'")"
./ch.sh "SELECT 'rows=' || toString(sum(rows)), 'parts=' || toString(count()), 'bytes=' || toString(sum(bytes_on_disk)), 'parts_content_hash=' || toString(cityHash64(groupArraySorted(100000)(hash_of_all_files))) FROM system.parts WHERE database='$db' AND table='$tb' AND active FORMAT TSV" | tr '\t' '\n'
echo "projections=$(./ch.sh "SELECT groupArray(name) FROM system.projections WHERE database='$db' AND table='$tb'")"
echo "skip_indexes=$(./ch.sh "SELECT groupArray(name) FROM system.data_skipping_indices WHERE database='$db' AND table='$tb'")"
if [ "$db" = bench ]; then
  echo "bench_tables=$(./ch.sh "SELECT groupArray(name) FROM (SELECT name FROM system.tables WHERE database='bench' ORDER BY name)")"
  echo "settings_profiles=$(./ch.sh "SELECT groupArray(name) FROM (SELECT name FROM system.settings_profiles ORDER BY name)")"
  echo "dashboard_profile=$(./ch.sh "SHOW CREATE SETTINGS PROFILE dashboard_profile" | sed 's/^CREATE SETTINGS PROFILE //')"
  echo "dashboard_user=$(./ch.sh "SHOW CREATE USER dashboard" | sed -E "s/IDENTIFIED WITH [a-z0-9_]+( BY '[^']*')?//")"
fi
