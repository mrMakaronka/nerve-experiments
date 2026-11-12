#!/usr/bin/env bash
# baseline.sh: frozen baseline as user dashboard: regression x3 (x4 repeats each), c6 twins x1, hidden control x1.
set -euo pipefail
cd "$(dirname "$0")/.."; P=~/nerve-demo-private/v4; C=$P/creds-operator.env
# New output goes to $OUT (default runs/, gitignored). evidence/ holds the recorded runs and is not written.
OUT=${OUT:-runs}; mkdir -p "$OUT/build"
./scripts/state.sh > $OUT/build/baseline-state.txt
for i in 1 2 3; do python3 scripts/replay.py --creds $C --set regression --repeat 4 --run-id base-$i --out $OUT/base-$i.json; done
python3 scripts/replay.py --creds $C --set c6 --run-id base-c6 --out $OUT/base-c6.json
CH_CONTROL_SQL=$P/control.sql python3 scripts/replay.py --creds $C --set control --repeat 4 --run-id ctl-base --out $P/ctl-base.json
./scripts/state.sh > $OUT/build/baseline-state-after.txt
diff $OUT/build/baseline-state.txt $OUT/build/baseline-state-after.txt && echo "state unchanged during baseline"
