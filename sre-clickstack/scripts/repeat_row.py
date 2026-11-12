"""Append one row to runs/repeats/results.csv from a collected loop folder.

    python3 sre-clickstack/scripts/repeat_row.py --run-id rep1-B --kind B --dir sre-clickstack/runs/repeats/rep1-B

c1_value / c2_value are recomputed by the harness (not the verifier) over the 300 s before the
verdict: synthetic-user error rate (%) and p95 (ms) of load-generator Client spans. The verifier's
own numbers stay in verdict-iter*.json.
"""

import argparse
import csv
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent


def query(sql: str):  # stdlib only (system python3, no matplotlib)
    e = dict(
        line.split("=", 1)
        for line in (DEMO / ".env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    url = f"http://{e['CLICKHOUSE_HOST']}:{e['CLICKHOUSE_PORT']}/?" + urllib.parse.urlencode(
        {"user": e["CLICKHOUSE_USER"], "password": e["CLICKHOUSE_PASSWORD"], "default_format": "JSONEachRow"}
    )
    with urllib.request.urlopen(urllib.request.Request(url, data=sql.encode()), timeout=60) as r:
        return [json.loads(line) for line in r.read().decode().splitlines() if line]


CSV = DEMO / "runs" / "repeats" / "results.csv"
FIELDS = [
    "run_id",
    "kind",
    "verdict",
    "oracle",
    "iterations",
    "t_loop_start",
    "t_mitigation",
    "t_verdict",
    "loop_minutes",
    "cost_usd",
    "c1_value",
    "c2_value",
    "verifier_queries_count",
    "notes",
]


def iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc) if s else None


def fmt(t):
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--kind", required=True, choices=["B", "C"])
    ap.add_argument("--dir", required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    d = Path(a.dir)
    notes = [a.note] if a.note else []

    st = json.loads((d / "loop-final.json").read_text()) if (d / "loop-final.json").exists() else None
    loop = (st or {}).get("loop", {})
    vatt = [x for x in (st or {}).get("attempts", []) if x["role"] == "verifier" and x.get("verdict")]
    last_v = vatt[-1] if vatt else None
    verdict = ""
    if last_v:
        v = last_v["verdict"]
        v = json.loads(v) if isinstance(v, str) else v
        verdict = v.get("verdict", "")
    if not st:
        notes.append("no loop-final.json")
    else:
        notes.append(
            f"status={loop.get('status')}"
            + (f" reason={loop.get('failure_reason')}" if loop.get("failure_reason") else "")
        )
        notes.append(" ".join(f"{c['id']}:{c.get('last_status')}" for c in loop.get("criteria", [])))
        if len(vatt) > 1:
            first = vatt[0]["verdict"]
            first = json.loads(first) if isinstance(first, str) else first
            notes.append(f"iter1 verdict={first.get('verdict')}: {first.get('summary', '')[:160]}")

    oracle = ""
    of = d / "sregym-oracle.txt"
    if of.exists():
        m = re.search(r'"success":\s*(true|false)', of.read_text())
        oracle = "success" if m and m.group(1) == "true" else "failure" if m else "unknown"

    t_mit = ""
    sf = d / "STATE.md"
    if sf.exists():
        ms = re.findall(r"MITIGATION_TS_UTC[`*: ]+(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d)", sf.read_text())
        t_mit = ms[-1].replace("T", " ") if ms else ""

    t0 = iso(loop.get("created_at"))
    tv = iso(last_v["settled_at"]) if last_v else None
    minutes = round((tv - t0).total_seconds() / 60, 1) if t0 and tv else ""

    c1 = c2 = ""
    if tv:
        u = fmt(tv)
        r = query(f"""SELECT round(100 * countIf(StatusCode = 'Error') / count(), 2) err,
                             round(quantile(0.95)(Duration) / 1e6, 1) p95_ms
                      FROM otel_traces WHERE ServiceName = 'load-generator' AND SpanKind = 'Client'
                        AND Timestamp >= toDateTime('{u}', 'UTC') - INTERVAL 300 SECOND
                        AND Timestamp < toDateTime('{u}', 'UTC')""")
        if r:
            c1, c2 = r[0]["err"], r[0]["p95_ms"]

    nq = 0
    for f in d.glob("verifier-leg-*.md"):
        nq += len(re.findall(r"\*\*tool `[^`]*run_query[^`]*`\*\*", f.read_text()))

    row = {
        "run_id": a.run_id,
        "kind": a.kind,
        "verdict": verdict,
        "oracle": oracle,
        "iterations": loop.get("iteration", ""),
        "t_loop_start": fmt(t0),
        "t_mitigation": t_mit,
        "t_verdict": fmt(tv),
        "loop_minutes": minutes,
        "cost_usd": round(float(loop.get("spent_usd") or 0), 2),
        "c1_value": c1,
        "c2_value": c2,
        "verifier_queries_count": nq,
        "notes": "; ".join(n for n in notes if n),
    }
    new = not CSV.exists()
    CSV.parent.mkdir(parents=True, exist_ok=True)
    with CSV.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(json.dumps(row))


if __name__ == "__main__":
    main()
