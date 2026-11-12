#!/usr/bin/env bash
# leakcheck.sh [--allow-loop NAME] : before a loop starts, list places an implementer could read that carry earlier
# runs' solutions. Diagnostic only. Nerve does not restrict the implementer's filesystem (it runs as the operator's
# user), so a clean result means "none of the known places has traces", not that the agent is isolated.
# Exit 0 = nothing found, 1 = traces found (each printed), 2 = usage error. MISSING lines are informational.
#   --allow-loop NAME : the new run's own loop repo ~/nerve-v4-loops/NAME is expected and not reported.
set -uo pipefail
CASE=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$CASE/.." && pwd)
ALLOW=""
if [ "${1:-}" = "--allow-loop" ]; then ALLOW=${2:?--allow-loop needs a name}; shift 2; fi
[ $# -eq 0 ] || { echo "usage: $0 [--allow-loop NAME]" >&2; exit 2; }
found=0
hit() { echo "  FOUND $*"; found=1; }
dir_or_missing() { [ -e "$1" ] && return 0; echo "  MISSING $1 (not checked)"; return 1; }
PATTERN='rvl-4e86c126|rvl-b7ac3e2e|rvl-b6b4f1ab|rvl-6d45d1fc|rvl-ec38122d|hits_fixed|hits_new|hits_faulted_backup|max_threads_min_free|use_uncompressed_cache'

echo "# loop repos (only the new run's repo may exist):"
if dir_or_missing ~/nerve-v4-loops; then
  for d in ~/nerve-v4-loops/*/; do [ -d "$d" ] || continue; [ "$(basename "$d")" = "$ALLOW" ] || hit "$d"; done
fi

echo "# agent scratch in /tmp and \$TMPDIR:"
for t in /tmp "${TMPDIR:-/tmp}"; do
  while IFS= read -r f; do hit "$f"; done < <(find "$t" -maxdepth 1 \( -name 'impl-*' -o -name 'ver-*' -o -name 'exp*' \) 2>/dev/null)
done

echo "# Nerve memory and lessons:"
for m in ~/nerve-demo-workspace/memory ~/.nerve/memu-manual; do
  dir_or_missing "$m" || continue
  while IFS= read -r f; do hit "$f"; done < <(grep -rl -i -E "$PATTERN|bench\.hits" "$m" 2>/dev/null)
done
for m in ~/.nerve/memu-resources/memorize-*; do
  [ -e "$m" ] || { echo "  MISSING ~/.nerve/memu-resources/memorize-* (not checked)"; break; }
  while IFS= read -r f; do hit "$f"; done < <(grep -rl -i -E "$PATTERN|bench\.hits" "$m" 2>/dev/null)
done

echo "# known exposure, reported but not counted:"
n=$(grep -rl -i -E "$PATTERN" "$CASE" --exclude-dir=.git 2>/dev/null | grep -v -c -E "/scripts/leakcheck\.sh$")
echo "  $n files in this checkout ($CASE) name earlier runs or their fixes; evidence/ holds the working fixes."
echo "  The implementer can read them whenever it can read this checkout. Run loops from a repo made by"
echo "  make_loop_repo.sh, and keep the checkout out of the implementer's reach (another user, a container, or"
echo "  a machine without it) if that matters."

if [ $found -eq 0 ]; then echo "leakcheck: nothing found in the places listed above"; else echo "leakcheck: traces found (see FOUND)"; fi
exit $found
