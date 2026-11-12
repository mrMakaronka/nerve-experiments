"""demo-v4 figures, drawn only from evidence files (no database access needed).

    uv run --with matplotlib python clickhouse-perf/scripts/plot_v4.py [--out-dir DIR]

Inputs : evidence/runs-summary.json (per-run medians from query_log, scripts/extract_runs.py), evidence/baseline.json,
         evidence/run-*/verdict-iter*.json, evidence/negative-control/verifier/verdict-iter1.json
Outputs: <out-dir>/timeline.png, <out-dir>/per_query.png  (200 dpi, 2200 px wide; style as agent-quality-langfuse);
         --out-dir defaults to runs/ (gitignored). The recorded figures in evidence/ are not overwritten unless
         --out-dir points there.
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter
from matplotlib.lines import Line2D

V4 = Path(__file__).resolve().parent.parent
EV = V4 / "evidence"
_ap = argparse.ArgumentParser()
_ap.add_argument("--out-dir", type=Path, default=V4 / "runs", help="where to write the PNGs (default: runs/)")
OUTD = _ap.parse_args().out_dir
OUTD.mkdir(parents=True, exist_ok=True)
DPI, K = 200, 130 / 200
FS = {"title": 12 * K, "tick": 10 * K, "label": 10 * K, "note": 8 * K, "box": 9 * K}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#dddddd"
PASS, FAIL = "#27ae60", "#8e1b10"
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"  # validated categorical slots 1-4 (dataviz validator)
plt.rcParams.update({"font.size": FS["tick"], "axes.titlesize": FS["title"], "figure.facecolor": "white",
                     "axes.edgecolor": "#999", "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})

base = json.loads((EV / "baseline.json").read_text())
runs = {r["log_comment"]: r for r in json.loads((EV / "runs-summary.json").read_text())["runs"]}
TARGET = base["target"]
C1_V2, C1_V1 = base["c1_threshold_ms"], base["c1_threshold_v1_ms"]


def tgt(lc):
    return sum(runs[lc]["median_ms"][str(n)] for n in TARGET)


def verdict(path):
    return json.loads((EV / path).read_text())["verdict"]


# chronological stages: (log_comment, short label, verdict file or None)
STAGES = [
    ("base-1", "base 1", None), ("base-2", "base 2", None), ("base-3", "base 3", None),
    ("post-fault", "post-fault", None),
    ("ver-rvl-4e86c126-iter1", "B v1 #1", "run-b-v1/verdict-iter1.json"),
    ("ver-rvl-4e86c126-iter2", "B v1 #2", "run-b-v1/verdict-iter2.json"),
    ("ver-rvl-b7ac3e2e-iter1", "B v2 #1", "run-b-v2/verdict-iter1.json"),
    ("ver-rvl-b6b4f1ab-iter1", "C' #1", "run-c-contaminated/verdict-iter1.json"),
    ("ver-rvl-b6b4f1ab-iter2", "C' #2", "run-c-contaminated/verdict-iter2.json"),
    ("envcheck-1", "env check", None),
    ("ver-rvl-6d45d1fc-iter1", "B #1", "run-b/verdict-iter1.json"),
    ("ver-ec38122d-iter1", "C #1", "run-c/verdict-iter1.json"),
    ("ver-rvl-ec38122d-iter2", "C #2", "run-c/verdict-iter2.json"),
    ("ver-rvl-e8bb12b2-iter1", "10b", "negative-control/verifier/verdict-iter1.json"),
]
X = {lc: i for i, (lc, _, _) in enumerate(STAGES)}

# ---- 1. timeline: target total (top) and whole-workload total (bottom), shared x -----------------------------
fig, (ax, bx) = plt.subplots(2, 1, figsize=(11, 6.6), sharex=True, gridspec_kw={"height_ratios": [3, 2], "hspace": 0.08})
xs = list(range(len(STAGES)))
for a in (ax, bx):
    a.set_xlim(-0.6, len(STAGES) - 0.4)
    a.grid(axis="y", color=GRID, lw=0.6)
    a.set_axisbelow(True)
    for lo, hi, col in ((X["ver-rvl-4e86c126-iter1"] - 0.5, X["ver-rvl-b6b4f1ab-iter2"] + 0.5, "#f1e4e1"),
                        (X["envcheck-1"] - 0.5, len(STAGES) - 0.5, "#e6f0e8")):
        a.axvspan(lo, hi, color=col, zorder=0, lw=0)
    a.axvline(X["post-fault"] - 0.5, color=FAIL, ls="--", lw=1.1, zorder=1)
for lo, hi, text in ((X["ver-rvl-4e86c126-iter1"] - 0.5, X["ver-rvl-b6b4f1ab-iter2"] + 0.5,
                      "server memory carried over between runs (contaminated)"),
                     (X["envcheck-1"] - 0.5, len(STAGES) - 0.5, "server restarted before each run (clean)")):
    ax.text((lo + hi) / 2, 1.012, text, transform=ax.get_xaxis_transform(), ha="center", va="bottom",
            fontsize=FS["label"], fontweight="bold", color="#444")

ty = [tgt(lc) for lc, _, _ in STAGES]
ax.plot(xs, ty, color=S1, lw=1.6, marker="o", ms=4.5, zorder=4)
ax.axhline(C1_V2, color=INK2, ls=":", lw=1)
ax.axhline(C1_V1, color=INK2, ls=(0, (1, 3)), lw=0.8)
ax.text(len(STAGES) - 0.45, C1_V2 + 25, f"C1 v2 ≤ {C1_V2:.0f} ms", fontsize=FS["note"], color=INK2, ha="right", va="bottom")
ax.text(len(STAGES) - 0.45, C1_V1 - 25, f"C1 v1 ≤ {C1_V1:.1f} ms", fontsize=FS["note"], color=INK2, ha="right", va="top")
ax.annotate("fault: ORDER BY (EventTime)", (X["post-fault"] - 0.5, 1700), xytext=(-4, 0), textcoords="offset points",
            fontsize=FS["note"], color=FAIL, ha="right", va="center")
ax.annotate("q23 not yet warm in this replay;\nsteady state ≈ 580 (env check)", (X["post-fault"], tgt("post-fault")),
            xytext=(X["post-fault"] - 0.6, 1000), textcoords="data", fontsize=FS["note"], color=INK2, ha="right",
            va="center", arrowprops={"arrowstyle": "-", "color": INK2, "lw": 0.6, "shrinkA": 2, "shrinkB": 4})
for i, v in enumerate(ty):
    ax.annotate(f"{v:.0f}", (i, v), xytext=(0, 6), textcoords="offset points", ha="center", va="bottom",
                fontsize=FS["note"], color=INK)
ax.set_ylim(0, 2300)
ax.set_ylabel("target queries, total warm median (ms)\nq23 q38 q39 q41 q42 q43", fontsize=FS["label"])

ry = [runs[lc]["total_ms"] / 1000 for lc, _, _ in STAGES]
bx.plot(xs, ry, color=S2, lw=1.6, marker="s", ms=4, zorder=4)
bx.set_yscale("log")
bx.set_ylim(5, 90)
bx.set_yticks([5, 8, 10, 20, 50])
bx.set_yticklabels(["5", "8", "10", "20", "50"])
bx.yaxis.set_minor_formatter(NullFormatter())
bx.axhline(base["regression_total_mean_ms"] / 1000, color=INK2, ls=":", lw=1)
bx.text(-0.55, base["regression_total_mean_ms"] / 1000 * 0.92, f"baseline {base['regression_total_mean_ms'] / 1000:.1f} s",
        fontsize=FS["note"], color=INK2, va="top")
for i, v in enumerate(ry):
    bx.annotate(f"{v:.1f}", (i, v), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom",
                fontsize=FS["note"], color=INK)
bx.set_ylabel("all 43 queries,\ntotal (s, log)", fontsize=FS["label"])

for lc, _, vf in STAGES:
    if vf:
        ok = verdict(vf) == "pass"
        ax.text(X[lc], 2140, "PASS" if ok else "REJECT", ha="center", va="center", fontsize=FS["box"],
                color=PASS if ok else FAIL, bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": PASS if ok else FAIL, "lw": 1})
bx.set_xticks(xs)
bx.set_xticklabels([lab for _, lab, _ in STAGES], rotation=35, ha="right", fontsize=FS["tick"])
ax.set_title("demo-v4: wrong sorting key on bench.hits (100M rows), verifier's own replays as user dashboard",
             pad=22, fontsize=FS["title"])
fig.text(0.01, 0.005, "Each point is one replay (median of repeats 2-4 per query, from system.query_log). "
         "B/C = Run B (schema fix allowed) / Run C (settings and skip indexes only), #n = iteration; "
         "C' = the first Run C; 10b = scripted wrong fix + verifier.", fontsize=FS["note"], color=INK2)
fig.savefig(OUTD / "timeline.png", dpi=DPI, bbox_inches="tight")
plt.close(fig)

# ---- 2. per query: ratio to baseline for the clean runs --------------------------------------------------------
SER = [("post-fault", "post-fault (faulted table)", S2, "s"),
       ("ver-rvl-6d45d1fc-iter1", "Run B, verifier replay (PASS)", S1, "o"),
       ("ver-rvl-ec38122d-iter2", "Run C, verifier replay #2 (REJECT)", S3, "^"),
       ("ver-rvl-e8bb12b2-iter1", "10b wrong fix, verifier replay (REJECT)", S4, "D")]
fig, ax = plt.subplots(figsize=(11, 4.6))
qs = list(range(1, 44))
for n in TARGET:
    ax.axvspan(n - 0.5, n + 0.5, color="#eeeeee", zorder=0, lw=0)
for j, (lc, label, col, mk) in enumerate(SER):
    off = (j - 1.5) * 0.17
    y = [runs[lc]["median_ms"][str(n)] / base["per_query"][str(n)]["baseline_ms"] if base["per_query"][str(n)]["baseline_ms"] else None
         for n in qs]
    ax.scatter([n + off for n in qs], y, s=14, color=col, marker=mk, edgecolor="white", linewidth=0.5, zorder=3, label=label)
for n in qs:
    pb = base["per_query"][str(n)]
    if pb["baseline_ms"]:
        lim = pb["c2_limit_ms"] / pb["baseline_ms"]
        ax.plot([n - 0.42, n + 0.42], [lim, lim], color=INK2, lw=0.9, zorder=2)
ax.axhline(1, color="#999", lw=0.6)
ax.set_yscale("log")
ax.set_ylim(0.1, 12)
ax.set_yticks([0.1, 0.3, 1, 3, 10])
ax.set_yticklabels(["0.1×", "0.3×", "1×", "3×", "10×"])
ax.yaxis.set_minor_formatter(NullFormatter())
ax.set_xlim(0.4, 43.6)
ax.set_xticks(qs)
ax.set_xticklabels([str(n) for n in qs], fontsize=FS["note"])
ax.set_xlabel("query number in workspace/regression.sql (grey columns: C1 target set)", fontsize=FS["label"])
ax.set_ylabel("warm median / baseline mean", fontsize=FS["label"])
ax.grid(axis="y", color=GRID, lw=0.6)
ax.set_axisbelow(True)
handles, labels = ax.get_legend_handles_labels()
handles.append(Line2D([0], [0], color=INK2, lw=0.9))
labels.append("C2 limit per query: max(1.3×, +50 ms)")
ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=FS["note"], frameon=False, ncol=5)
ax.set_title("Per-query latency vs. baseline (clean server); points under the dash pass C2", fontsize=FS["title"])
fig.savefig(OUTD / "per_query.png", dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("wrote", OUTD / "timeline.png", OUTD / "per_query.png")
