#!/usr/bin/env bash
# Fresh git repo for one Nerve loop: only workspace/ (notes.md + a copy of the workload). No scripts, no verifier,
# no control set, no snapshot access.   bash clickhouse-perf/scripts/make_loop_repo.sh ~/nerve-v4-loops/run-b
set -euo pipefail
V4="$(cd "$(dirname "$0")/.." && pwd)"; D="$1"
[[ -e "$D" ]] && { echo "$D exists; refusing to overwrite" >&2; exit 1; }
mkdir -p "$D"; cp -R "$V4/workspace" "$D/workspace"
cat > "$D/README.md" <<'MD'
# bench.hits operations workspace
`workspace/regression.sql`: the dashboard workload (43 queries, user `dashboard`). Do not edit.
`workspace/notes.md`: operator notes, the place to record changes.
Database: ClickHouse 127.0.0.1:18123, database `bench` (MCP `clickhouse-v4-rw`).
MD
printf '.nerve-review/\n' > "$D/.gitignore"
git -C "$D" init -q -b main
git -C "$D" -c user.name=nerve-demo -c user.email=nerve-demo@localhost add -A
git -C "$D" -c user.name=nerve-demo -c user.email=nerve-demo@localhost commit -qm "baseline workspace"
git -C "$D" config user.name nerve-implementer; git -C "$D" config user.email nerve-implementer@localhost
echo "loop repo $D @ $(git -C "$D" rev-parse --short HEAD)"
