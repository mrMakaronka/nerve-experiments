#!/usr/bin/env bash
# Start the demo-v4 ClickHouse container (pinned image), localhost-only.
# Secrets: ~/nerve-demo-private/v4/.env (CH_*_PASSWORD), users.d with the admin hash in the same dir
# (scripts/init-private.sh creates both). The recorded runs used a 16 GB container on a dedicated host (FINDINGS §1);
# CH_MEMORY overrides it, e.g. CH_MEMORY=14g on a laptop. Results under another limit are not comparable.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
P=~/nerve-demo-private/v4
IMAGE=clickhouse/clickhouse-server:26.8.36.3@sha256:d426d2f612e1e189c90f9a3f8dcd85a03c6851273833817a296bb327e63aa7a7
DATA=${CLICKBENCH_DATA:-$HOME/clickbench-data}
if docker ps -a --format '{{.Names}}' | grep -qx ch-v4; then docker start ch-v4 >/dev/null; else
  docker run -d --name ch-v4 \
    --memory "${CH_MEMORY:-16g}" --ulimit nofile=262144:262144 -e CLICKHOUSE_DO_NOT_CHOWN=1 \
    -p 127.0.0.1:18123:8123 -p 127.0.0.1:19000:9000 \
    -v ch-v4-data:/var/lib/clickhouse \
    -v "$HERE/ch/config.d/v4.xml:/etc/clickhouse-server/config.d/v4.xml:ro" \
    -v "$P/ch-users.d/admin.xml:/etc/clickhouse-server/users.d/admin.xml:ro" \
    -v "$DATA:/data/clickbench:ro" \
    "$IMAGE" >/dev/null
fi
for i in $(seq 60); do curl -sf http://127.0.0.1:18123/ping >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:18123/ping
