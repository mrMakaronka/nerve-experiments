#!/usr/bin/env python3
"""Generate queries/regression_c6.sql: deterministic twins of the 43 regression queries, for result hashes only.

Mechanical rules (original brief, "c6 twins"):
  1. a query with ORDER BY gets every selected column appended as a tie-breaker (positional: ORDER BY <orig>, 1, 2, ..., k;
     for SELECT * the column names from DESCRIBE bench.hits), so LIMIT/OFFSET returns a deterministic set;
  2. a GROUP BY ... LIMIT without ORDER BY gets ORDER BY over all selected columns;
  3. float aggregates (AVG) are wrapped in round(x, 6).
Queries without ORDER BY/LIMIT are copied unchanged. The transform log goes to queries/regression_c6.log.
"""

import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
Q = os.path.join(HERE, "..", "queries")


def split_top_level_commas(s):
    out, depth, cur, quote = [], 0, "", None
    for ch in s:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    out.append(cur)
    return [x.strip() for x in out]


def wrap_avg(sql):
    # AVG(<expr with at most one nested paren level>) -> round(AVG(...), 6)
    return re.sub(r"\bAVG\(((?:[^()]|\([^()]*\))*)\)", r"round(AVG(\1), 6)", sql)


def main():
    cols = subprocess.run([os.path.join(HERE, "ch.sh"), "SELECT name FROM system.columns WHERE database = 'bench' "
                           "AND table = 'hits' ORDER BY position"], capture_output=True, text=True, check=True).stdout.split()
    lines = [ln.strip().rstrip(";") for ln in open(os.path.join(Q, "regression.sql")) if ln.strip()]
    twins, log = [], []
    for i, q in enumerate(lines, 1):
        m = re.match(r"(?is)^SELECT (.*?) FROM hits(.*)$", q)
        select_list, rest = m.group(1), m.group(2)
        n_sel = len(split_top_level_commas(select_list))
        tie = ", ".join(cols) if select_list.strip() == "*" else ", ".join(str(k) for k in range(1, n_sel + 1))
        rules = []
        t = q
        lim = re.search(r"(?i)\sLIMIT\s", t)
        if re.search(r"(?i)\sORDER BY\s", t):
            # insert the tie-breaker right before LIMIT (or at the end)
            if lim:
                t = t[:lim.start()] + f", {tie}" + t[lim.start():]
            else:
                t = t + f", {tie}"
            rules.append("tie-breaker")
        elif lim and re.search(r"(?i)\sGROUP BY\s", t):
            t = t[:lim.start()] + f" ORDER BY {tie}" + t[lim.start():]
            rules.append("order-by-added")
        t2 = wrap_avg(t)
        if t2 != t:
            rules.append("round-avg")
        twins.append(t2 + ";")
        log.append(f"{i}\t{','.join(rules) or 'unchanged'}")
    open(os.path.join(Q, "regression_c6.sql"), "w").write("\n".join(twins) + "\n")
    open(os.path.join(Q, "regression_c6.log"), "w").write(
        "# query\trules applied by scripts/make_c6.py\n" + "\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
