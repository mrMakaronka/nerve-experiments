#!/usr/bin/env python3
"""make_baseline.py: build $OUT/baseline.json from the frozen baseline runs (after target selection).

Inputs ($OUT/, default runs/): base-1.json, base-2.json, base-3.json (regression x4), base-c6.json (twins, hashes),
post-fault.json; queries/target.txt, queries/c6_excluded.txt; $OUT/build/baseline-state.txt (rows, bytes).
C1 threshold (criteria v2, 2026-11-11) = max(mean + spread, 1.10 x mean) of the target total over the three baselines.
v1 was mean + spread only; changed by the operator after Run B v1 (see FINDINGS).
C2 per query: baseline_ms = mean of the three per-run medians; limit = max(1.3 x baseline_ms, baseline_ms + 50).
"""

import hashlib
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
# New output goes to $OUT (default runs/, gitignored). evidence/ holds the recorded runs and is not written.
E = os.path.join(HERE, "..", os.environ.get("OUT", "runs"))
Q = os.path.join(HERE, "..", "queries")


def nums(path):
    if not os.path.exists(path):
        return []
    return [int(ln.split()[0]) for ln in open(path) if ln.strip() and not ln.startswith("#")]


def main():
    base = [json.load(open(os.path.join(E, f"base-{i}.json"))) for i in (1, 2, 3)]
    c6 = json.load(open(os.path.join(E, "base-c6.json")))
    post = json.load(open(os.path.join(E, "post-fault.json")))
    state = dict(ln.strip().split("=", 1) for ln in open(os.path.join(E, "build", "baseline-state.txt")) if "=" in ln)
    target = nums(os.path.join(Q, "target.txt"))
    excluded = nums(os.path.join(Q, "c6_excluded.txt"))
    per = {}
    for n in range(1, 44):
        meds = [next(q for q in b["queries"] if q["n"] == n)["median_ms"] for b in base]
        rr = [next(q for q in b["queries"] if q["n"] == n)["read_rows"] for b in base]
        bm = statistics.mean(meds)
        per[str(n)] = {"median_ms_runs": meds, "baseline_ms": round(bm, 1), "read_rows": int(statistics.median(rr)),
                       "c2_limit_ms": round(max(1.3 * bm, bm + 50), 1)}
    tt = [sum(next(q for q in b["queries"] if q["n"] == n)["median_ms"] for n in target) for b in base]
    mean, spread = statistics.mean(tt), max(tt) - min(tt)
    post_q = {q["n"]: q for q in post["queries"]}
    out = {
        "frozen_utc": base[0]["started_utc"], "runs": [b["run_id"] for b in base],
        "regression_totals_ms": [b["totals"]["total_median_ms"] for b in base],
        "regression_total_mean_ms": round(statistics.mean(b["totals"]["total_median_ms"] for b in base), 1),
        "regression_total_spread_ms": max(b["totals"]["total_median_ms"] for b in base)
        - min(b["totals"]["total_median_ms"] for b in base),
        "target": target, "target_totals_ms": tt, "target_mean_ms": round(mean, 1), "target_spread_ms": spread,
        # criteria v2 (operator, 2026-11-11, after Run B v1): C1 floor as in C2. v1 was mean + spread only.
        "c1_rule": "v2: max(mean + spread, 1.10 x mean)",
        "c1_threshold_v1_ms": round(mean + spread, 1),
        "c1_threshold_ms": round(max(mean + spread, 1.10 * mean), 1),
        "post_fault_run": post["run_id"],
        "post_fault_target_total_ms": sum(post_q[n]["median_ms"] for n in target),
        "post_fault_ratios": {str(n): round(post_q[n]["median_ms"] / per[str(n)]["baseline_ms"], 2)
                              for n in range(1, 44) if per[str(n)]["baseline_ms"]},
        "per_query": per,
        "c6_run": c6["run_id"], "c6_excluded": excluded,
        "c6_hashes": {str(q["n"]): q["result_hash"] for q in c6["queries"] if q["n"] not in excluded},
        "rows": int(state["rows"]), "bytes": int(state["bytes"]), "c3_max_bytes": int(1.5 * int(state["bytes"])),
        "replay_py_sha256": base[0]["replay_py_sha256"],
        "regression_sql_sha256": hashlib.sha256(open(os.path.join(Q, "regression.sql"), "rb").read()).hexdigest(),
    }
    json.dump(out, open(os.path.join(E, "baseline.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_query", "c6_hashes", "post_fault_ratios")}, indent=1))


if __name__ == "__main__":
    main()
