#!/usr/bin/env python3
"""summarize.py A.json B.json [--md]: per-query ratio table B/A (median latency, read_rows), totals, hash diff."""

import json
import sys


def load(p):
    d = json.load(open(p))
    return d, {q["n"]: q for q in d["queries"]}


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    a, qa = load(a_path)
    b, qb = load(b_path)
    print(f"A = {a['run_id']} ({a['set']}, {a['started_utc']})   B = {b['run_id']} ({b['set']}, {b['started_utc']})\n")
    print("| q | A ms | B ms | B/A time | A read_rows | B read_rows | B/A rows | hash |")
    print("|---|---|---|---|---|---|---|---|")
    diff = []
    for n in sorted(set(qa) | set(qb)):
        x, y = qa.get(n, {}), qb.get(n, {})
        am, bm = x.get("median_ms"), y.get("median_ms")
        ar, br = x.get("read_rows"), y.get("read_rows")
        t = f"{bm / am:.2f}" if am and bm is not None else "-"
        r = f"{br / ar:.2f}" if ar and br is not None else "-"
        same = x.get("result_hash") == y.get("result_hash")
        if not same:
            diff.append(n)
        print(f"| {n} | {am} | {bm} | {t} | {ar} | {br} | {r} | {'=' if same else 'DIFF'} |")
    ta, tb = a["totals"]["total_median_ms"], b["totals"]["total_median_ms"]
    print(f"\ntotal_median_ms: A {ta}  B {tb}  B/A {tb / ta:.2f}" if ta and tb else "")
    print(f"p95_median_ms:   A {a['totals']['p95_median_ms']}  B {b['totals']['p95_median_ms']}")
    print(f"result hashes differing: {diff if diff else 'none'}")


if __name__ == "__main__":
    main()
