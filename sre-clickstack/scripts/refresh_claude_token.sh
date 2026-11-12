#!/usr/bin/env bash
# Copy this Mac's current Claude Code OAuth access token (Keychain) into Nerve's
# config.local.yaml and hot-reload Nerve. The Keychain token lives ~8 h and is
# refreshed by Claude Code itself; long unattended runs (repeat.sh) call this
# before every loop. Never prints the token.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CFG="$ROOT/vendor/nerve/config.local.yaml"
tok=$(security find-generic-password -s 'Claude Code-credentials' -w |
      python3 -c 'import json,sys;print(json.load(sys.stdin)["claudeAiOauth"]["accessToken"])')
TOK="$tok" python3 - "$CFG" <<'EOF'
import os, re, sys
p = sys.argv[1]; s = open(p).read(); t = os.environ["TOK"]
new = re.sub(r'^claude_oauth_token:.*$', lambda m: f'claude_oauth_token: "{t}"', s, flags=re.M)
if new == s and 'claude_oauth_token:' not in s:
    new = f'claude_oauth_token: "{t}"\n' + s
changed = new != s
open(p, "w").write(new)
print("token updated" if changed else "token unchanged")
EOF
"$ROOT/vendor/nerve/.venv/bin/nerve" reload >/dev/null 2>&1 || true
