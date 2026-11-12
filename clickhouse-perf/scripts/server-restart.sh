#!/usr/bin/env bash
# server-restart.sh : restart the server container so that in-memory server state (uncompressed cache, mark cache,
# query condition cache, memory held by earlier sessions) is cleared before a run. Data stays on disk.
# Added 2026-11-11 after server memory state was found to carry over between runs (FINDINGS §4).
# The restart command is host-specific: set BENCH_RESTART_CMD (default: restart the local container ch-v4).
set -euo pipefail
cd "$(dirname "$0")"
${BENCH_RESTART_CMD:-docker restart ch-v4} >/dev/null
for i in $(seq 120); do curl -sf http://127.0.0.1:18123/ping >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:18123/ping >/dev/null || { echo "server not reachable on 127.0.0.1:18123" >&2; exit 1; }
./ch.sh "SELECT 'server_state', uptime() AS uptime_s, (SELECT value FROM system.metrics WHERE metric='UncompressedCacheBytes') AS uncompressed_cache_bytes, (SELECT value FROM system.metrics WHERE metric='MarkCacheBytes') AS mark_cache_bytes FORMAT TSV"
