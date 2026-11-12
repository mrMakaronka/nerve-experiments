#!/usr/bin/env bash
# One-command setup for the closed-loop demo (macOS + Docker Desktop, ≥16 GB given to Docker).
#
#   bash sre-clickstack/scripts/up.sh            # everything: clone, kind, ClickStack, SREGym app, tee, Nerve
#   SKIP_KIND=1 bash sre-clickstack/scripts/up.sh   # reuse an existing kind cluster
#   bash sre-clickstack/scripts/up.sh --dry-run  # check prerequisites + current state, print what each step would do
#
# Idempotent-ish: safe to re-run; each step skips work already done.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"      # repo root (contains sre-clickstack/ and vendor/)
DEMO="$ROOT/sre-clickstack"
VENDOR="$ROOT/vendor"
NERVE_WS="${NERVE_WS:-$HOME/nerve-demo-workspace}"
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:$HOME/.docker/bin:$PATH"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
DRY=""; [[ "${1:-}" == "--dry-run" ]] && DRY=1
# act CMD...: run a state-changing command, or just print it under --dry-run
act() { if [[ -n "$DRY" ]]; then printf '   would run: %s\n' "$*"; else "$@"; fi; }

step "0. prerequisites"
for t in docker kubectl kind helm uv node git; do command -v "$t" >/dev/null || { echo "missing: $t (brew install kind helm node@22 uv)"; exit 1; }; done
mem=$(docker info --format '{{.MemTotal}}'); (( mem > 15000000000 )) || { echo "Docker Desktop needs ≥16 GB memory (has $((mem/1024/1024)) MiB)"; exit 1; }
command -v codex >/dev/null || act npm i -g @openai/codex@0.164.0

step "1. clone pinned upstreams into vendor/"
# commits from PINS.md (the ones the recorded runs used)
SREGYM_SHA=ef444ee65f763154c29d0b95f89a4f1e4c2ac2e0; NERVE_SHA=4173725dc2723ee9e3b41c05522f695ba72e6b1d
[[ -d "$VENDOR/SREGym" ]] || { act git clone https://github.com/SREGym/SREGym.git "$VENDOR/SREGym" && act git -C "$VENDOR/SREGym" checkout -q "$SREGYM_SHA" && act git -C "$VENDOR/SREGym" submodule update --init --recursive --depth 1; }
[[ -d "$VENDOR/nerve" ]]  || { act git clone https://github.com/ClickHouse/nerve.git "$VENDOR/nerve" && act git -C "$VENDOR/nerve" checkout -q "$NERVE_SHA"; }

step "2. kind cluster (SREGym setup script)"
if [[ -z "${SKIP_KIND:-}" ]] && ! kubectl --context kind-kind get nodes >/dev/null 2>&1; then
  act bash -c "cd '$VENDOR/SREGym' && bash kind/setup_kind_cluster.sh"
else echo "   kind cluster present (context kind-kind)"
fi
[[ -n "$DRY" ]] || kubectl config use-context kind-kind >/dev/null

step "3. ClickStack all-in-one on the host"
docker ps --format '{{.Names}}' | grep -qx clickstack && echo "   clickstack container running" || act bash "$DEMO/scripts/clickstack-up.sh"

step "4. SREGym observability + astronomy-shop (svelte profile, no agent)"
act bash -c "cd '$VENDOR/SREGym' && uv sync -q"
if ! kubectl -n astronomy-shop get deploy frontend-proxy >/dev/null 2>&1; then
  act bash -c "cd '$VENDOR/SREGym' && SREGYM_PROFILE=svelte uv run python '$DEMO/scripts/sregym_ctl.py' deploy"
else echo "   astronomy-shop deployed"
fi

step "5. tee the observe collector into ClickStack"
act bash -c "cd '$VENDOR/SREGym' && uv run python '$DEMO/scripts/tee-collector.py'"

step "6. Nerve (worker mode) + demo workspace"
if [[ -n "$DRY" ]]; then
  [[ -x "$VENDOR/nerve/.venv/bin/nerve" ]] && echo "   nerve installed" || echo "   would run: uv sync + web build in vendor/nerve"
  [[ -f "$VENDOR/nerve/config.local.yaml" ]] && echo "   nerve configured" || echo "   would run: nerve init (worker, passwordless, UTC) + append nerve-config.yaml"
  echo "   would copy: prompts/nerve-TASK.md + skills -> $NERVE_WS; ~/.codex/auth.json -> ~/.nerve/codex/ (if missing)"
  echo "   would run: nerve start|restart, fetch NERVE_TOKEN into sre-clickstack/.env (if missing)"
  curl -sf localhost:8900/api/auth/status >/dev/null && echo "   nerve currently listening on :8900" || echo "   nerve not running"
  step "dry run done (nothing changed)"; exit 0
fi
cd "$VENDOR/nerve"
[[ -x .venv/bin/nerve ]] || { uv sync --python 3.13 -q; (cd web && npm ci --quiet && npm run build >/dev/null); }
if [[ ! -f config.local.yaml ]]; then
  # Reuse this Mac's Claude Code login (OAuth access token, ~8 h lifetime).
  # For a durable token run `claude setup-token` and export CLAUDE_CODE_OAUTH_TOKEN yourself.
  : "${CLAUDE_CODE_OAUTH_TOKEN:=$(security find-generic-password -s 'Claude Code-credentials' -w | python3 -c 'import json,sys;print(json.load(sys.stdin)["claudeAiOauth"]["accessToken"])')}"
  CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" NERVE_MODE=worker NERVE_WORKSPACE="$NERVE_WS" \
    NERVE_TIMEZONE=UTC NERVE_PASSWORDLESS=1 .venv/bin/nerve init --non-interactive
  cat "$DEMO/nerve-config.yaml" >> config.yaml
  set -a; source "$DEMO/.env"; set +a
  printf '\nmcp_servers:\n  clickhouse:\n    env:\n      CLICKHOUSE_PASSWORD: "%s"\n' "$CLICKHOUSE_PASSWORD" >> config.local.yaml
fi
# workspace files (TASK.md + skills) from the demo repo
# (rendered copy: the timeline path in prompts/ is the original checkout's, see scripts/render-prompts.sh)
bash "$DEMO/scripts/render-prompts.sh"
cp "$DEMO/prompts/local/nerve-TASK.md" "$NERVE_WS/TASK.md"
mkdir -p "$NERVE_WS/skills"
cp -R "$DEMO/skills/"* "$NERVE_WS/skills/"
# the tracked skill names the recorded timeline (evidence/); the installed copy points at the one new runs write
sed -i.bak 's|sre-clickstack/evidence/timeline.log|sre-clickstack/runs/timeline.log|g' "$NERVE_WS/skills/incident-triage/SKILL.md" \
  && rm -f "$NERVE_WS/skills/incident-triage/SKILL.md.bak"
# isolated Codex home for the verifier (reuses your ChatGPT login)
mkdir -p "$HOME/.nerve/codex"; [[ -f "$HOME/.nerve/codex/auth.json" ]] || cp "$HOME/.codex/auth.json" "$HOME/.nerve/codex/auth.json"
.venv/bin/nerve status >/dev/null 2>&1 && .venv/bin/nerve restart || .venv/bin/nerve start
for _ in $(seq 1 30); do curl -sf localhost:8900/api/auth/status >/dev/null && break; sleep 2; done
grep -q '^NERVE_TOKEN=' "$DEMO/.env" || {
  tok=$(curl -s -X POST localhost:8900/api/auth/login -H 'content-type: application/json' -d '{"password":"x"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')
  echo "NERVE_TOKEN=$tok" >> "$DEMO/.env"; }
.venv/bin/nerve codex doctor || true

step "done"
echo "HyperDX UI : http://localhost:$(grep -s ^HYPERDX_PORT= "$DEMO/.env" | cut -d= -f2 || true)" | sed "s|:$|:8080|"
echo "Nerve UI   : http://localhost:8900"
echo "Next       : see sre-clickstack/README.md (inject -> run A -> run B)"
