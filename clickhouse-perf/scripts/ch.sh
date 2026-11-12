#!/usr/bin/env bash
# ch.sh [--user U] SQL...   run SQL over HTTP as v4admin (default) or a named demo user; reads SQL from stdin if no arg.
set -euo pipefail
set -a; . ~/nerve-demo-private/v4/.env; set +a
U=v4admin; PW=$CH_ADMIN_PASSWORD
if [ "${1:-}" = --user ]; then U=$2; shift 2; v="CH_$(echo "$U" | tr a-z A-Z)_PASSWORD"; PW=${!v}; fi
if [ $# -gt 0 ]; then printf '%s' "$*" ; else cat; fi | curl -sS --fail-with-body -u "$U:$PW" 'http://127.0.0.1:18123/?max_execution_time=3600' --data-binary @-
