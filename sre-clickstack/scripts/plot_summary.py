"""Page-one figure: the three runs side by side, from ClickStack telemetry.

    uv run --with matplotlib python sre-clickstack/scripts/plot_summary.py --out sre-clickstack/evidence/summary.png

Columns: Run A (diagnose only), Run B (fixed + verified), Run C (restart-only, rejected).
Rows: synthetic-user error rate (load-generator Client spans), frontend-proxy server spans/min.
Markers: inject, mitigation/restart, verifier verdict (or diagnosis delivered for Run A).
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_timeline import query

RUNS = [
    {
        "title": "Run A — open loop (diagnose only)",
        "since": "2026-11-09 22:56:00",
        "until": "2026-11-09 23:06:30",
        "marks": [
            ("inject", "2026-11-09 23:01:00", "#c0392b"),
            ("diagnosed,\nno action", "2026-11-09 23:05:19", "#7f8c8d", "right", 70),
        ],
        "verdict": "correct root cause in 102 s\nincident still active",
    },
    {
        "title": "Run B — closed loop (fixed + verified)",
        "since": "2026-11-09 22:56:00",
        "until": "2026-11-09 23:44:00",
        "marks": [
            ("inject", "2026-11-09 23:01:00", "#c0392b"),
            ("mitigation", "2026-11-09 23:06:37", "#2471a3"),
            ("verifier PASS", "2026-11-09 23:42:39", "#27ae60"),
        ],
        "verdict": "PASS 5/5 criteria\nSREGym oracle: success",
    },
    {
        "title": "Run C — restart-only fix (rejected)",
        "since": "2026-11-09 23:39:00",
        "until": "2026-11-09 23:56:30",
        "marks": [
            ("inject", "2026-11-09 23:44:38", "#c0392b"),
            ("rollout restart", "2026-11-09 23:45:26", "#2471a3"),
            ("verifier FAIL", "2026-11-09 23:55:01", "#8e1b10"),
        ],
        "verdict": "FAIL: 89 % errors, p95 14.9 s\nSREGym oracle: failure",
    },
]


def series(since: str, until: str):
    s, u = f"toDateTime('{since}', 'UTC')", f"toDateTime('{until}', 'UTC')"
    lg = query(f"""
        SELECT toString(toStartOfInterval(Timestamp, INTERVAL 30 SECOND)) t,
               round(100 * countIf(StatusCode = 'Error') / count(), 2) err
        FROM otel_traces WHERE ServiceName = 'load-generator' AND SpanKind = 'Client'
          AND Timestamp >= {s} AND Timestamp < {u} GROUP BY t ORDER BY t""")
    fp = query(f"""
        SELECT toString(toStartOfInterval(Timestamp, INTERVAL 30 SECOND)) t, count() * 2 per_min
        FROM otel_traces WHERE ServiceName = 'frontend-proxy' AND SpanKind = 'Server'
          AND Timestamp >= {s} AND Timestamp < {u} GROUP BY t ORDER BY t""")
    p = lambda x: dt.datetime.strptime(x[:19], "%Y-%m-%d %H:%M:%S")
    err = [(p(r["t"]), r["err"]) for r in lg]
    fpm = {p(r["t"]): r["per_min"] for r in fp}
    xs = [x for x, _ in err]
    return err, [(x, fpm.get(x, 0)) for x in xs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    fig, axes = plt.subplots(2, 3, figsize=(17, 7), sharey="row", gridspec_kw={"width_ratios": [1, 2.6, 1.6]})
    p = lambda x: dt.datetime.strptime(x, "%Y-%m-%d %H:%M:%S")
    for col, run in enumerate(RUNS):
        err, fpm = series(run["since"], run["until"])
        top, bot = axes[0][col], axes[1][col]
        top.plot([x for x, _ in err], [y for _, y in err], color="#c0392b", lw=1.6)
        bot.plot([x for x, _ in fpm], [y for _, y in fpm], color="#2471a3", lw=1.6)
        top.set_title(run["title"], fontsize=11, fontweight="bold")
        for ax in (top, bot):
            ax.grid(alpha=0.3)
            ax.set_xlim(p(run["since"]), p(run["until"]))
            for _, ts, color, *_ in run["marks"]:
                ax.axvline(p(ts), color=color, ls="--", lw=1.2)
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        top.set_ylim(-3, 105)
        for i, (label, ts, color, *align) in enumerate(run["marks"]):
            ha = align[0] if align else "left"  # right = text left of the marker (keeps it inside the axes)
            y = align[1] if len(align) > 1 else 102 - i * 14
            top.annotate(
                label,
                (p(ts), y),
                fontsize=8,
                color=color,
                ha=ha,
                xytext=(3 if ha == "left" else -3, 0),
                textcoords="offset points",
                va="top",
            )
        bot.text(
            0.98,
            0.06,
            run["verdict"],
            transform=bot.transAxes,
            ha="right",
            va="bottom",
            fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="#999"),
        )
        bot.set_xlabel("UTC")
    axes[0][0].set_ylabel("synthetic-user\nerror rate %")
    axes[1][0].set_ylabel("frontend-proxy\nserver spans / min")
    fig.suptitle(
        "One incident, three handlings — SREGym env_variable_shadowing · Nerve review loop · ClickStack telemetry",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(a.out, dpi=130)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
