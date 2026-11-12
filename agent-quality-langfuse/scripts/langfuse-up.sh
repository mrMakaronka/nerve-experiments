#!/usr/bin/env bash
# Self-hosted Langfuse (official docker compose from vendor/langfuse) for demo-v3.
#   - random secrets instead of the compose file's "# CHANGEME" defaults, kept in agent-quality-langfuse/.env (gitignored)
#   - every port bound to 127.0.0.1 (override file), headless init of org/project/API keys/UI user
#   bash agent-quality-langfuse/scripts/langfuse-up.sh       # UI: http://localhost:3000
set -euo pipefail
V3="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$V3/.." && pwd)"   # repo root; vendor/ lives here (PINS.md)
LF="$ROOT/vendor/langfuse"
ENVF="$V3/.env"
export PATH="$HOME/.docker/bin:/opt/homebrew/bin:$PATH"
LF_SHA=4fe6ebf6a04191f90e89cdff646535cce2a9c46d   # PINS.md
[[ -d "$LF" ]] || { git clone -q https://github.com/langfuse/langfuse "$LF" && git -C "$LF" checkout -q "$LF_SHA"; }
touch "$ENVF"; chmod 600 "$ENVF"

add() { grep -q "^$1=" "$ENVF" || echo "$1=$2" >> "$ENVF"; }
rnd() { openssl rand -hex "${1:-16}"; }
add LANGFUSE_HOST http://localhost:3000
add LANGFUSE_PUBLIC_KEY "pk-lf-$(rnd 12)"
add LANGFUSE_SECRET_KEY "sk-lf-$(rnd 16)"
add LANGFUSE_UI_EMAIL demo@nerve.local
add LANGFUSE_UI_PASSWORD "$(rnd 12)"
for v in SALT NEXTAUTH_SECRET POSTGRES_PASSWORD CLICKHOUSE_PASSWORD MINIO_ROOT_PASSWORD REDIS_AUTH; do add "LF_$v" "$(rnd 16)"; done
add LF_ENCRYPTION_KEY "$(rnd 32)"
set -a; source "$ENVF"; set +a

export SALT="$LF_SALT" NEXTAUTH_SECRET="$LF_NEXTAUTH_SECRET" ENCRYPTION_KEY="$LF_ENCRYPTION_KEY"
export POSTGRES_PASSWORD="$LF_POSTGRES_PASSWORD" DATABASE_URL="postgresql://postgres:${LF_POSTGRES_PASSWORD}@postgres:5432/postgres"
export CLICKHOUSE_PASSWORD="$LF_CLICKHOUSE_PASSWORD" REDIS_AUTH="$LF_REDIS_AUTH"
export MINIO_ROOT_PASSWORD="$LF_MINIO_ROOT_PASSWORD"
export LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY="$LF_MINIO_ROOT_PASSWORD" LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY="$LF_MINIO_ROOT_PASSWORD" LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY="$LF_MINIO_ROOT_PASSWORD"
export LANGFUSE_INIT_ORG_ID=nerve-demo LANGFUSE_INIT_ORG_NAME="Nerve demo" \
       LANGFUSE_INIT_PROJECT_ID=text2sql LANGFUSE_INIT_PROJECT_NAME="text2sql" \
       LANGFUSE_INIT_PROJECT_PUBLIC_KEY="$LANGFUSE_PUBLIC_KEY" LANGFUSE_INIT_PROJECT_SECRET_KEY="$LANGFUSE_SECRET_KEY" \
       LANGFUSE_INIT_USER_EMAIL="$LANGFUSE_UI_EMAIL" LANGFUSE_INIT_USER_NAME=demo LANGFUSE_INIT_USER_PASSWORD="$LANGFUSE_UI_PASSWORD"

cat > "$V3/scripts/langfuse-localhost.override.yml" <<'EOF'
# demo-v3: bind every published port to localhost only.
services:
  langfuse-web:
    ports: !override ["127.0.0.1:3000:3000"]
  langfuse-worker:
    ports: !override ["127.0.0.1:3030:3030"]
  langfuse-ai-gateway:
    ports: !override ["127.0.0.1:3031:3031"]
  minio:
    ports: !override ["127.0.0.1:9090:9000", "127.0.0.1:9091:9001"]
  clickhouse:
    ports: !override ["127.0.0.1:18123:8123", "127.0.0.1:19000:9000"]
EOF
docker compose -p langfuse -f "$LF/docker-compose.yml" -f "$V3/scripts/langfuse-localhost.override.yml" up -d
echo -n "waiting for Langfuse"
for _ in $(seq 1 120); do
  curl -sf http://localhost:3000/api/public/health >/dev/null && { echo " ok"; break; }
  echo -n .; sleep 3
done
curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" http://localhost:3000/api/public/projects | head -c 300; echo
echo "Langfuse UI: http://localhost:3000  (user $LANGFUSE_UI_EMAIL, password in agent-quality-langfuse/.env)"
