#!/usr/bin/env python3
"""envcheck_verdict.py REPLAY.json [--ref DIR] [--out FILE]: is the server in the reference state? (rule v2)

Compares one regression replay taken right after `reset.sh faulted` with the reference `post-fault` replay.
Exit 0 = clean, 1 = not clean, 2 = bad input. Prints measured value, reference and tolerance for every check.

Rule v2 (written in the release audit, after the recorded runs; it reuses the case's existing noise floors):
  - q23 is excluded from every check and reported for information only. Its `post-fault` repeats were still
    warming the page cache (6911 / 1366 / 889 / 354 ms), so the reference value for q23 is not a steady state
    (FINDINGS §4).
  - regression total without q23 within max(baseline relative spread, 10 %) of the reference;
  - target total without q23 within the same kind of band, from the target spread;
    (the 10 % floor is the one criteria v2 already uses for C1: max(mean + spread, 1.10 x mean))
  - every other query within C2's per-query limit, applied to the reference: max(1.3 x ref, ref + 50 ms).
Rule v1 (the original envcheck.sh) compared totals including q23 with the bare spreads, 1.15 % and 2.84 %. The
recorded verdicts in evidence/envcheck/*.verdict.json use v1 and all say clean: false; the operator judged the
server clean by hand, excluding q23 (FINDINGS §4). They are kept as recorded.

This detects carried-over server state of the size seen in the contaminated runs (whole workload 57.9 s against
10.8 s); it is not a fine-grained performance test.
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CASE = os.path.dirname(HERE)
EXCLUDED = 23
FLOOR = 0.10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument(
        "--ref",
        default=os.path.join(CASE, "evidence"),
        help="directory with baseline.json and post-fault.json (default: the recorded evidence/)",
    )
    ap.add_argument("--out", help="write the verdict JSON here")
    a = ap.parse_args()
    try:
        b = json.loads(Path(a.ref, "baseline.json").read_text())
        post = json.loads(Path(a.ref, "post-fault.json").read_text())
        r = json.loads(Path(a.replay).read_text())
    except (OSError, ValueError) as e:
        print(f"envcheck: cannot read input: {e}", file=sys.stderr)
        return 2
    pq = {q["n"]: q for q in post["queries"]}
    rq = {q["n"]: q for q in r["queries"]}
    if set(pq) != set(rq) or any(rq[n].get("error") for n in rq):
        print(f"envcheck: replay has errors or a different query set ({len(rq)} vs {len(pq)})", file=sys.stderr)
        return 2
    keep = sorted(n for n in pq if n != EXCLUDED)
    tgt = [n for n in b["target"] if n != EXCLUDED]
    checks = []

    def band(name, measured, ref, spread_rel):
        tol = max(spread_rel, FLOOR)
        checks.append(
            {
                "check": name,
                "measured_ms": measured,
                "reference_ms": ref,
                "tolerance_pct": round(100 * tol, 2),
                "delta_pct": round(100 * (measured - ref) / ref, 2),
                "ok": abs(measured - ref) <= tol * ref,
            }
        )

    band(
        "regression total without q23",
        sum(rq[n]["median_ms"] for n in keep),
        sum(pq[n]["median_ms"] for n in keep),
        b["regression_total_spread_ms"] / b["regression_total_mean_ms"],
    )
    band(
        "target total without q23",
        sum(rq[n]["median_ms"] for n in tgt),
        sum(pq[n]["median_ms"] for n in tgt),
        b["target_spread_ms"] / b["target_mean_ms"],
    )
    slow = []
    for n in keep:
        ref, m = pq[n]["median_ms"], rq[n]["median_ms"]
        lim = max(1.3 * ref, ref + 50)
        if m > lim:
            slow.append({"q": n, "measured_ms": m, "reference_ms": ref, "limit_ms": round(lim, 1)})
    checks.append({"check": "per query (C2 limit vs reference), q23 excluded", "violations": slow, "ok": not slow})
    q23 = {
        "measured_ms": rq[EXCLUDED]["median_ms"],
        "reference_ms": pq[EXCLUDED]["median_ms"],
        "baseline_ms": b["per_query"][str(EXCLUDED)]["baseline_ms"],
    }
    clean = all(c["ok"] for c in checks)
    v = {
        "rule": "v2",
        "replay": os.path.abspath(a.replay),
        "reference": os.path.abspath(a.ref),
        "clean": clean,
        "checks": checks,
        "q23_informational": q23,
    }
    for c in checks:
        if "measured_ms" in c:
            print(
                f"{'ok  ' if c['ok'] else 'FAIL'} {c['check']}: {c['measured_ms']} ms vs {c['reference_ms']} ms "
                f"({c['delta_pct']:+.2f} %, tolerance ±{c['tolerance_pct']} %)"
            )
        else:
            print(
                f"{'ok  ' if c['ok'] else 'FAIL'} {c['check']}: {len(c['violations'])} violation(s)"
                + "".join(
                    f"\n     q{s['q']}: {s['measured_ms']} > {s['limit_ms']} ms (reference {s['reference_ms']})"
                    for s in c["violations"]
                )
            )
    print(
        f"info q23: {q23['measured_ms']} ms (reference {q23['reference_ms']}, baseline {q23['baseline_ms']}); not checked"
    )
    print("clean" if clean else "NOT CLEAN: do not start a run on this server state")
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        Path(a.out).write_text(json.dumps(v, indent=1))
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
