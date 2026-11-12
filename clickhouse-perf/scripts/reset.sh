#!/usr/bin/env bash
# reset.sh faulted|good : restore bench.hits from the hidden snapshot (hard links), drop everything the implementer
# may have created (extra tables, projections and skip indexes go with the table, settings profiles, roles),
# re-apply users/grants/profiles from grants.sql.tmpl, print the state fingerprint.
# Since 2026-11-11 (after Run B v1 / v2 / C): first restarts the server so in-memory caches do not carry over
# between runs (server state is part of the reset, not only data). Validate with envcheck.sh before a run.
set -euo pipefail
cd "$(dirname "$0")"; n=$1; [ "$n" = good ] || [ "$n" = faulted ] || { echo "usage: reset.sh faulted|good"; exit 2; }
echo "reset to $n at $(date -u +%FT%TZ)"
./server-restart.sh
for t in $(./ch.sh "SELECT name FROM system.tables WHERE database = 'bench'"); do ./ch.sh "DROP TABLE bench.\`$t\` SYNC"; echo "dropped bench.$t"; done
for p in $(./ch.sh "SELECT name FROM system.settings_profiles WHERE storage = 'local_directory' AND name != 'dashboard_profile'"); do ./ch.sh "DROP SETTINGS PROFILE \`$p\`"; echo "dropped profile $p"; done
for r in $(./ch.sh "SELECT name FROM system.roles WHERE storage = 'local_directory'"); do ./ch.sh "DROP ROLE \`$r\`"; echo "dropped role $r"; done
python3 apply_sql.py grants.sql.tmpl >/dev/null
./ch.sh "CREATE TABLE bench.hits AS _snap.hits_$n"
./ch.sh "ALTER TABLE bench.hits ATTACH PARTITION tuple() FROM _snap.hits_$n"
./state.sh bench.hits
