#!/usr/bin/env python3
"""compare.py --baseline baseline.json --reg RUN.json [--c6 RUN_C6.json]

Deterministic arithmetic for the pinned criteria, from replay.py output files only:
  C1  total warm median ms of the target queries (taken from the regression run) <= baseline c1_threshold_ms
  C2  every regression query: median_ms <= max(1.3 x baseline_ms, baseline_ms + 50); read_rows > 2 x baseline flagged
  C6  every c6 twin result hash == baseline hash (excluded twins listed in baseline.json are skipped)
Also prints the exec user and the replay.py sha256 recorded in each run file (C4/C7 inputs).
"""

import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--reg", required=True)
    ap.add_argument("--c6")
    a = ap.parse_args()
    b = json.load(open(a.baseline))
    reg = json.load(open(a.reg))
    q = {x["n"]: x for x in reg["queries"]}
    out = {"run_id": reg["run_id"], "set": reg["set"], "exec_user": reg["exec_user"],
           "replay_py_sha256": reg["replay_py_sha256"], "query_log_rows": reg["query_log_rows"],
           "merge_wait": reg["merge_wait"], "errors": [x["n"] for x in reg["queries"] if x["error"]],
           "log_users": sorted({x.get("log_user") for x in reg["queries"] if x.get("log_user")})}

    tgt = b["target"]
    tgt_ms = [q[n]["median_ms"] for n in tgt]
    total = sum(v for v in tgt_ms if v is not None) if None not in tgt_ms else None
    out["C1"] = {"target_queries": tgt, "target_total_ms": total, "threshold_ms": b["c1_threshold_ms"],
                 "baseline_target_mean_ms": b["target_mean_ms"], "baseline_target_spread_ms": b["target_spread_ms"],
                 "post_fault_target_total_ms": b.get("post_fault_target_total_ms"),
                 "per_query_ms": dict(zip(map(str, tgt), tgt_ms)),
                 "met": total is not None and total <= b["c1_threshold_ms"]}

    viol, flags, rows = [], [], []
    for n_str, pb in b["per_query"].items():
        n = int(n_str)
        x = q.get(n, {})
        ms, rr = x.get("median_ms"), x.get("read_rows")
        limit = pb["c2_limit_ms"]
        ratio = (ms / pb["baseline_ms"]) if ms is not None and pb["baseline_ms"] else None
        rr_ratio = (rr / pb["read_rows"]) if rr is not None and pb["read_rows"] else None
        rows.append({"q": n, "ms": ms, "baseline_ms": pb["baseline_ms"], "limit_ms": limit,
                     "ratio": None if ratio is None else round(ratio, 3),
                     "read_rows": rr, "read_rows_ratio": None if rr_ratio is None else round(rr_ratio, 3)})
        if ms is None or ms > limit:
            viol.append(n)
        if rr_ratio is not None and rr_ratio > 2:
            flags.append(n)
    out["C2"] = {"violations": viol, "read_rows_gt_2x_flagged": flags, "met": not viol, "per_query": rows,
                 "total_median_ms": reg["totals"]["total_median_ms"],
                 "baseline_total_mean_ms": b["regression_total_mean_ms"]}

    if a.c6:
        c6 = json.load(open(a.c6))
        mism, missing = [], []
        for n_str, h in b["c6_hashes"].items():
            got = next((x for x in c6["queries"] if x["n"] == int(n_str)), None)
            if got is None or got["result_hash"] is None:
                missing.append(int(n_str))
            elif got["result_hash"] != h:
                mism.append({"q": int(n_str), "baseline": h, "got": got["result_hash"]})
        out["C6"] = {"run_id": c6["run_id"], "checked": len(b["c6_hashes"]), "excluded": b["c6_excluded"],
                     "mismatches": mism, "missing": missing, "met": not mism and not missing,
                     "replay_py_sha256": c6["replay_py_sha256"]}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
