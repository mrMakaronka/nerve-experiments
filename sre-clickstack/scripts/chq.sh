#!/usr/bin/env bash
# Run a SQL string (arg) or file (-f path) against ClickStack as nerve_ro. Pretty output.
set -euo pipefail
DEMO="$(cd "$(dirname "$0")/.." && pwd)"; set -a; source "$DEMO/.env"; set +a
URL="http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/?user=${CLICKHOUSE_USER}&password=${CLICKHOUSE_PASSWORD}&default_format=${FMT:-PrettyCompact}"
if [[ "${1:-}" == "-f" ]]; then curl -s "$URL" --data-binary @"$2"; else curl -s "$URL" --data-binary "$1"; fi
