"""runs/repeats/results.csv -> runs/repeats/summary.md (the directory repeat.sh writes; gitignored)

python3 sre-clickstack/scripts/summarize_repeats.py               # new repeats in runs/repeats/
python3 sre-clickstack/scripts/summarize_repeats.py --historical  # recorded evidence/repeats/, printed only

--historical reads evidence/repeats/ and prints the summary to stdout; it never writes evidence/repeats/summary.md.
"""

import argparse
import csv
import statistics as st
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--historical", action="store_true", help="read the recorded evidence/repeats/ and print only")
args = ap.parse_args()
D = Path(__file__).resolve().parent.parent / ("evidence" if args.historical else "runs") / "repeats"
rows = list(csv.DictReader((D / "results.csv").open()))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def agg(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return "n/a"
    return f"{st.median(v):g} ({min(v):g}–{max(v):g})"


out = [
    "# Repeats: env_variable_shadowing, Run B and Run C × N",
    "",
    "Source: `results.csv` (one row per loop, written by `scripts/repeat_row.py`). Median (min–max).",
    "`c1_value` / `c2_value` are recomputed by the harness over the 300 s before the verdict "
    "(synthetic-user error % / p95 ms); the verifier's own numbers are in each run's `verdict-iter*.json`.",
    "",
    "| kind | runs | loop minutes | cost USD | iterations | c1 err % | c2 p95 ms | verifier queries |",
    "|---|---|---|---|---|---|---|---|",
]
for k in ("B", "C"):
    rs = [r for r in rows if r["kind"] == k]
    out.append(
        f"| {k} | {len(rs)} | {agg(num(r['loop_minutes']) for r in rs)} | {agg(num(r['cost_usd']) for r in rs)} | "
        f"{agg(num(r['iterations']) for r in rs)} | {agg(num(r['c1_value']) for r in rs)} | "
        f"{agg(num(r['c2_value']) for r in rs)} | {agg(num(r['verifier_queries_count']) for r in rs)} |"
    )

out += ["", "## Verdict vs SREGym oracle", ""]
for k, want_v, want_o in (("B", "pass", "success"), ("C", None, "failure")):
    rs = [r for r in rows if r["kind"] == k]
    if k == "B":
        agree = sum(r["verdict"] == "pass" and r["oracle"] == "success" for r in rs)
        out.append(f"- **B:** {agree}/{len(rs)} runs where verifier `pass` and oracle `success` agree.")
    else:
        agree = sum(r["verdict"] in ("fail", "needs_improvement") and r["oracle"] == "failure" for r in rs)
        out.append(
            f"- **C:** {agree}/{len(rs)} runs where verifier rejected (`fail`/`needs_improvement`) and oracle `failure` agree."
        )
    for r in rs:
        ok = (r["verdict"] == "pass") == (r["oracle"] == "success")
        if not ok:
            out.append(
                f"  - disagreement in `{r['run_id']}`: verdict `{r['verdict'] or '—'}`, oracle `{r['oracle'] or '—'}` ({r['notes'][:200]})"
            )

out += ["", "## Runs needing more than one iteration", ""]
multi = [r for r in rows if (num(r["iterations"]) or 0) > 1]
out += [f"- `{r['run_id']}` ({r['kind']}): {r['iterations']} iterations — {r['notes'][:300]}" for r in multi] or [
    "- none"
]

out += [
    "",
    "## All runs",
    "",
    "| run | kind | verdict | oracle | iter | loop min | $ | c1 | c2 | notes |",
    "|---|---|---|---|---|---|---|---|---|---|",
]
out += [
    f"| {r['run_id']} | {r['kind']} | {r['verdict']} | {r['oracle']} | {r['iterations']} | {r['loop_minutes']} | "
    f"{r['cost_usd']} | {r['c1_value']} | {r['c2_value']} | {r['notes'][:120]} |"
    for r in rows
]
if (D / "NOTES.md").exists():
    out += ["", (D / "NOTES.md").read_text()]
if not args.historical:
    (D / "summary.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
