"""Render the incident timeline from ClickStack as a PNG (evidence screenshot substitute).

    uv run --with matplotlib python sre-clickstack/scripts/plot_timeline.py --since "2026-11-09 22:25:00" --out sre-clickstack/evidence/timeline.png

Panels: synthetic-user (load-generator Client) error rate, its p95 latency, and
frontend-proxy server spans/min. Vertical lines from sre-clickstack/runs/timeline.log (else evidence/timeline.log)
(inject_done, recover_done) and any extra --mark "label=YYYY-MM-DD HH:MM:SS".
"""

import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

DEMO = Path(__file__).resolve().parent.parent


def env():
    out = {}
    for line in (DEMO / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


def query(sql: str):
    e = env()
    url = f"http://{e['CLICKHOUSE_HOST']}:{e['CLICKHOUSE_PORT']}/?" + urllib.parse.urlencode(
        {"user": e["CLICKHOUSE_USER"], "password": e["CLICKHOUSE_PASSWORD"], "default_format": "JSONEachRow"}
    )
    with urllib.request.urlopen(urllib.request.Request(url, data=sql.encode())) as r:
        return [json.loads(line) for line in r.read().decode().splitlines() if line]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="UTC 'YYYY-MM-DD HH:MM:SS'")
    ap.add_argument("--until", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="astronomy-shop incident — telemetry from ClickStack")
    ap.add_argument("--mark", action="append", default=[], help="label=YYYY-MM-DD HH:MM:SS")
    a = ap.parse_args()
    until = f"toDateTime('{a.until}', 'UTC')" if a.until else "now()"
    since = f"toDateTime('{a.since}', 'UTC')"

    lg = query(f"""
        SELECT toString(toStartOfInterval(Timestamp, INTERVAL 30 SECOND)) t,
               count() n, round(100 * countIf(StatusCode = 'Error') / count(), 2) err,
               round(quantile(0.95)(Duration) / 1e6, 1) p95
        FROM otel_traces WHERE ServiceName = 'load-generator' AND SpanKind = 'Client'
          AND Timestamp >= {since} AND Timestamp < {until}
        GROUP BY t ORDER BY t""")
    fp = query(f"""
        SELECT toString(toStartOfInterval(Timestamp, INTERVAL 30 SECOND)) t, count() * 2 per_min
        FROM otel_traces WHERE ServiceName = 'frontend-proxy' AND SpanKind = 'Server'
          AND Timestamp >= {since} AND Timestamp < {until}
        GROUP BY t ORDER BY t""")

    parse = lambda s: dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    marks = []
    tl = DEMO / "runs" / "timeline.log"  # new runs; fall back to the recorded timeline
    if not tl.exists():
        tl = DEMO / "evidence" / "timeline.log"
    if tl.exists():
        for line in tl.read_text().splitlines():
            ev = json.loads(line)
            if ev["event"] in ("inject_done", "recover_done") and ev["ts_utc"] >= a.since:
                marks.append((ev["event"].replace("_done", ""), parse(ev["ts_utc"])))
    for m in a.mark:
        label, ts = m.split("=", 1)
        marks.append((label, parse(ts)))

    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    axes[0].plot([parse(r["t"]) for r in lg], [r["err"] for r in lg], color="#c0392b")
    axes[0].set_ylabel("synthetic-user\nerror rate %")
    axes[1].plot([parse(r["t"]) for r in lg], [r["p95"] for r in lg], color="#8e44ad")
    axes[1].set_ylabel("synthetic-user\np95 ms (log)")
    axes[1].set_yscale("log")
    # fill gaps (no spans) with zeros for the volume panel
    fp_map = {parse(r["t"]): r["per_min"] for r in fp}
    xs = sorted({parse(r["t"]) for r in lg} | set(fp_map))
    axes[2].plot(xs, [fp_map.get(x, 0) for x in xs], color="#2471a3")
    axes[2].set_ylabel("frontend-proxy\nserver spans/min")
    palette = {"inject": "#c0392b", "recover": "#27ae60"}
    for ax in axes:
        ax.grid(alpha=0.3)
        for label, ts in marks:
            ax.axvline(ts, color=palette.get(label, "#2c3e50"), ls="--", lw=1)
    for label, ts in marks:
        axes[0].annotate(label, (ts, axes[0].get_ylim()[1]), rotation=90, va="top", ha="right", fontsize=8)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[2].set_xlabel("UTC")
    fig.suptitle(a.title)
    fig.tight_layout()
    fig.savefig(a.out, dpi=120)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
