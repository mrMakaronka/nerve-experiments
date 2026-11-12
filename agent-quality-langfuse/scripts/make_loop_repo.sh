#!/usr/bin/env bash
# Fresh git repo for one Nerve loop: only the baseline workspace/ (no agent code, no oracle).
#   bash agent-quality-langfuse/scripts/make_loop_repo.sh ~/nerve-v3-loops/run-b
set -euo pipefail
V3="$(cd "$(dirname "$0")/.." && pwd)"; D="$1"
[[ -e "$D" ]] && { echo "$D exists; refusing to overwrite" >&2; exit 1; }
mkdir -p "$D"; cp -R "$V3/workspace" "$D/workspace"
cat > "$D/README.md" <<'MD'
# text2sql agent workspace
`workspace/` is everything the text2sql agent reads at prompt-assembly time:
`prompt.md` (instructions), `schema_notes.md` (live-schema notes), `skills/*.md` (extra guidance).
Scores and traces: Langfuse project `text2sql` (MCP `langfuse-tools`).
MD
git -C "$D" init -q -b main
git -C "$D" -c user.name=nerve-demo -c user.email=nerve-demo@localhost add -A
git -C "$D" -c user.name=nerve-demo -c user.email=nerve-demo@localhost commit -qm "baseline workspace"
git -C "$D" config user.name nerve-implementer; git -C "$D" config user.email nerve-implementer@localhost
echo "loop repo $D @ $(git -C "$D" rev-parse --short HEAD)"
