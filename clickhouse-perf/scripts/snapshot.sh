#!/usr/bin/env bash
# snapshot.sh good|faulted : hard-link the current bench.hits parts into _snap.hits_<name> (no copy).
# _snap is invisible to nerve_rw / nerve_verify / dashboard (no grants).
set -euo pipefail
cd "$(dirname "$0")"; n=$1
./ch.sh "DROP TABLE IF EXISTS _snap.hits_$n SYNC"
./ch.sh "CREATE TABLE _snap.hits_$n AS bench.hits"
./ch.sh "ALTER TABLE _snap.hits_$n ATTACH PARTITION tuple() FROM bench.hits"
./ch.sh "SELECT '_snap.hits_$n', count(), sum(rows), formatReadableSize(sum(bytes_on_disk)), cityHash64(groupArraySorted(100000)(hash_of_all_files)) FROM system.parts WHERE database = '_snap' AND table = 'hits_$n' AND active"
