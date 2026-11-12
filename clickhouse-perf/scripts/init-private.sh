#!/usr/bin/env bash
# init-private.sh : create the operator-only inputs in ~/nerve-demo-private/v4 (mode 700). Never overwrites a file
# that exists; run it once before ch-up.sh. Nothing it writes belongs in the repository.
#   .env                    CH_ADMIN / CH_DASHBOARD / CH_NERVE_RW / CH_NERVE_VERIFY passwords (random)
#                           read by apply_sql.py, ch.sh, fill_verifier.py
#   ch-users.d/admin.xml    the admin user v4admin (sha256 of CH_ADMIN_PASSWORD), mounted by ch-up.sh
#   creds-operator.env      replay.py credentials for the operator: runs as dashboard, reads query_log as v4admin
#   control.sql             NOT created. The hidden control set of the recorded runs is private. Write your own:
#                           ClickBench-style SELECTs on bench.hits separated by ';', none of them in
#                           queries/regression.sql (replay.py reads it via CH_CONTROL_SQL; baseline.sh passes it).
set -euo pipefail
P=~/nerve-demo-private/v4
umask 077
mkdir -p "$P/ch-users.d"; chmod 700 ~/nerve-demo-private "$P" "$P/ch-users.d"
pw() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }
keep() { [ -e "$1" ] && { echo "keep  $1"; return 0; }; return 1; }

keep "$P/.env" || {
  { for k in ADMIN DASHBOARD NERVE_RW NERVE_VERIFY; do echo "CH_${k}_PASSWORD=$(pw)"; done; } > "$P/.env"
  echo "wrote $P/.env"; }
set -a; . "$P/.env"; set +a

keep "$P/ch-users.d/admin.xml" || {
  h=$(printf %s "$CH_ADMIN_PASSWORD" | shasum -a 256 | cut -d' ' -f1)
  cat > "$P/ch-users.d/admin.xml" <<XML
<clickhouse>
  <users>
    <default remove="remove"/>
    <v4admin>
      <password_sha256_hex>$h</password_sha256_hex>
      <networks><ip>::/0</ip></networks>
      <profile>default</profile>
      <quota>default</quota>
      <access_management>1</access_management>
      <named_collection_control>1</named_collection_control>
    </v4admin>
  </users>
</clickhouse>
XML
  echo "wrote $P/ch-users.d/admin.xml"; }

keep "$P/creds-operator.env" || {
  printf 'CH_EXEC_USER=dashboard\nCH_EXEC_PASSWORD=%s\nCH_READ_USER=v4admin\nCH_READ_PASSWORD=%s\n' \
    "$CH_DASHBOARD_PASSWORD" "$CH_ADMIN_PASSWORD" > "$P/creds-operator.env"
  echo "wrote $P/creds-operator.env"; }

[ -e "$P/control.sql" ] && echo "keep  $P/control.sql" || echo "TODO  $P/control.sql: write your own hidden control set (see the header of this script)"
chmod 600 "$P/.env" "$P/ch-users.d/admin.xml" "$P/creds-operator.env"
