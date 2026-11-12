#!/usr/bin/env bash
# Start ClickStack all-in-one on the host with:
#   - a known OTLP ingestion key (INGESTION_API_KEY bootstrap path of the AIO image)
#   - a read-only ClickHouse user `nerve_ro` reachable from the host on :8123
#     (the image's `default` user is restricted to 127.0.0.1 inside the container)
# Secrets live in sre-clickstack/.env (generated on first run).
# Ports are published on 127.0.0.1 only (CLICKSTACK_BIND). On Docker Desktop the kind cluster still reaches OTLP
# :4318 through host.docker.internal, which forwards to the Mac's loopback. On Linux, loopback-published ports
# are not reachable from containers: set CLICKSTACK_BIND to the kind network gateway (`docker network inspect kind`,
# IPAM gateway) and pass the same address to tee-collector.py --endpoint. nerve_ro accepts any source address inside the container (connections
# arrive from the Docker gateway, not from loopback); it is read-only and has a random password.
set -euo pipefail
DEMO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEMO"

if [[ ! -f .env ]]; then
  cat > .env <<EOF
CLICKSTACK_INGESTION_API_KEY=$(uuidgen | tr A-Z a-z)
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=nerve_ro
CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)
EOF
  chmod 600 .env
fi
set -a; source .env; set +a
BIND="${CLICKSTACK_BIND:-127.0.0.1}"
HYPERDX_PORT="${HYPERDX_PORT:-8080}"   # host port for the HyperDX UI (set in sre-clickstack/.env if 8080 is taken)

mkdir -p clickstack/users.d
cat > clickstack/users.d/nerve_ro.xml <<EOF
<clickhouse>
  <profiles>
    <nerve_ro_profile>
      <readonly>2</readonly>
      <max_execution_time>60</max_execution_time>
      <max_result_rows>10000</max_result_rows>
      <result_overflow_mode>break</result_overflow_mode>
    </nerve_ro_profile>
  </profiles>
  <users>
    <nerve_ro>
      <password>${CLICKHOUSE_PASSWORD}</password>
      <networks><ip>::/0</ip></networks>
      <profile>nerve_ro_profile</profile>
      <quota>default</quota>
      <grants>
        <query>GRANT SELECT ON default.*</query>
        <query>GRANT SELECT ON system.*</query>
        <query>GRANT SHOW ON *.*</query>
      </grants>
    </nerve_ro>
  </users>
</clickhouse>
EOF

docker rm -f clickstack >/dev/null 2>&1 || true
docker run -d --name clickstack \
  -p "$BIND:8123:8123" -p "$BIND:${HYPERDX_PORT}:8080" -p "$BIND:4317:4317" -p "$BIND:4318:4318" \
  -e FRONTEND_URL="http://localhost:${HYPERDX_PORT}" \
  -e INGESTION_API_KEY="${CLICKSTACK_INGESTION_API_KEY}" \
  -v "$DEMO/clickstack/users.d/nerve_ro.xml:/etc/clickhouse-server/users.d/nerve_ro.xml:ro" \
  clickhouse/clickstack-all-in-one@sha256:6804421d79acea32cf42c93171df0e82df081a0c96af3f3743e91d6185d26a54 >/dev/null

echo -n "waiting for ClickHouse"
for _ in $(seq 1 90); do
  if curl -sf "http://localhost:8123/?user=${CLICKHOUSE_USER}&password=${CLICKHOUSE_PASSWORD}" --data 'SELECT 1' >/dev/null; then
    echo " ok"; break
  fi
  echo -n .; sleep 2
done
curl -s "http://localhost:8123/?user=${CLICKHOUSE_USER}&password=${CLICKHOUSE_PASSWORD}" --data 'SELECT version(), currentUser()'
echo "HyperDX UI: http://localhost:${HYPERDX_PORT}  (create a UI user on first visit)"
