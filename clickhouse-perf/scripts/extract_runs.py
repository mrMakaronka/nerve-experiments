#!/usr/bin/env python3
"""extract_runs.py: per-run, per-query warm medians straight from system.query_log (operator view, v4admin).

For every regression replay of the demo (log_comment in RUNS), takes QueryFinish rows with query_id
'<run>-qNN-rR', drops r1 and computes the median of r2..r4 per query, the same rule replay.py uses. Also reads
read_rows. Writes $OUT/runs-summary.json (default runs/). The recorded evidence/runs-summary.json, which the figures are
drawn from, was produced this way from the bench server's query_log.
Hidden control runs (ctl-*) are summarised as totals and hash equality only (query text stays private).
"""

import json
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "..", os.environ.get("OUT", "runs"))
os.makedirs(EV, exist_ok=True)

# (log_comment, label, group). Groups: baseline, fault, contaminated (server state carried over), clean, envcheck.
RUNS = [
    ("base-1", "baseline 1", "baseline"), ("base-2", "baseline 2", "baseline"), ("base-3", "baseline 3", "baseline"),
    ("post-fault", "post-fault", "fault"), ("nc-dry", "10b dry run", "fault"),
    ("ver-rvl-4e86c126-iter1", "B v1 verify 1", "contaminated"),
    ("ver-rvl-4e86c126-iter2", "B v1 verify 2", "contaminated"),
    ("ver-rvl-b7ac3e2e-iter1", "B v2 verify 1", "contaminated"),
    ("ver-rvl-b6b4f1ab-iter1", "C (1st) verify 1", "contaminated"),
    ("ver-rvl-b6b4f1ab-iter2", "C (1st) verify 2", "contaminated"),
    ("envcheck-1", "env check 1", "envcheck"),
    ("ver-rvl-6d45d1fc-iter1", "B clean verify 1", "clean"),
    ("envcheck-2", "env check 2", "envcheck"),
    ("ver-ec38122d-iter1", "C clean verify 1", "clean"),
    ("ver-rvl-ec38122d-iter2", "C clean verify 2", "clean"),
    ("envcheck-3", "env check 3", "envcheck"),
]


def ch(sql):
    out = subprocess.run([os.path.join(HERE, "ch.sh"), sql], capture_output=True, text=True, check=True).stdout
    return [ln.split("\t") for ln in out.splitlines() if ln]


def main():
    extra = [tuple(a.split("=", 2)) for a in sys.argv[1:]]  # extra runs: log_comment=label=group
    runs = RUNS + [e for e in extra if len(e) == 3]
    out = {"rule": "median of r2..r4 per query from system.query_log QueryFinish", "runs": []}
    for lc, label, group in runs:
        rows = ch(f"SELECT query_id, query_duration_ms, read_rows, user FROM system.query_log "
                  f"WHERE type = 'QueryFinish' AND log_comment = '{lc}' AND query_id LIKE '{lc}-q%-r%' FORMAT TSV")
        per = {}
        users = set()
        for qid, ms, rr, user in rows:
            q, r = qid[len(lc) + 1:].split("-")
            per.setdefault(int(q[1:]), {})[int(r[1:])] = (int(ms), int(rr))
            users.add(user)
        if not per:
            print(f"skip {lc}: no rows", file=sys.stderr)
            continue
        med = {n: statistics.median(v[r][0] for r in (2, 3, 4) if r in v) for n, v in per.items()}
        rr = {n: int(statistics.median(v[r][1] for r in (2, 3, 4) if r in v)) for n, v in per.items()}
        out["runs"].append({"log_comment": lc, "label": label, "group": group, "users": sorted(users),
                            "n_queries": len(per), "total_ms": sum(med.values()),
                            "median_ms": {str(k): med[k] for k in sorted(med)},
                            "read_rows": {str(k): rr[k] for k in sorted(rr)}})
        print(f"{lc:28s} {label:20s} n={len(per)} total={sum(med.values()):.0f} users={sorted(users)}")
    json.dump(out, open(os.path.join(EV, "runs-summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
