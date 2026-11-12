"""Agent-quality figures, drawn only from evidence files (no Langfuse or API access needed).

    uv run --with matplotlib python agent-quality-langfuse/scripts/plot_v3.py [--out-dir DIR]

Inputs : evidence/scores_table.md (replay + control per experiment run, oracle per label),
         evidence/oracle-scores.json, evidence/run-{b,c}/verdict-iter*.json
Outputs: <out-dir>/scores_timeline.png, <out-dir>/summary.png  (200 dpi, 2200 px wide); --out-dir defaults to runs/
         (gitignored). The recorded figures in evidence/ are not overwritten unless --out-dir points there.

Font sizes match sre-clickstack/evidence/summary.png in pixels: that figure is rendered at 130 dpi, these at 200,
so every point size is the SRE size x 130/200.
"""

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

V3 = Path(__file__).resolve().parent.parent
EV = V3 / "evidence"
_ap = argparse.ArgumentParser()
_ap.add_argument("--out-dir", type=Path, default=V3 / "runs", help="where to write the PNGs (default: runs/)")
OUTD = _ap.parse_args().out_dir
OUTD.mkdir(parents=True, exist_ok=True)
DPI, K = 200, 130 / 200  # K: SRE point size -> same pixel size at 200 dpi
FS = {"title": 12 * K, "tick": 10 * K, "label": 10 * K, "note": 8 * K, "box": 9 * K}
RED, DARKRED, GREEN, BLUE = "#c0392b", "#8e1b10", "#27ae60", "#2471a3"
ORANGE, PURPLE, GREY = "#d35400", "#6c3483", "#7f8c8d"
BAR_BLUE, BAR_ORANGE = "#2a78d6", "#eb6834"  # summary.png keeps its original colours
plt.rcParams.update({"font.size": FS["tick"], "axes.titlesize": FS["title"], "figure.facecolor": "white"})

# ---- data -------------------------------------------------------------------------------------------------
rows, oracle_tbl = {}, {}
for line in (EV / "scores_table.md").read_text().splitlines():
    c = [x.strip() for x in line.strip("|").split("|")]
    if len(c) == 6 and re.match(r"^\d\.\d{4}$", c[2]):
        rows[c[0]] = {"replay": float(c[2]), "control": float(c[3])}
    elif len(c) == 2 and re.match(r"^\d\.\d{4}$", c[1]):
        oracle_tbl[c[0]] = float(c[1])
oracle = {k: v["exec_match_avg"] for k, v in json.loads((EV / "oracle-scores.json").read_text()).items()}
assert all(abs(oracle[k] - oracle_tbl[k]) < 1e-4 for k in oracle_tbl), "oracle-scores.json != scores_table.md"
verdicts = {
    f"{run}{p.stem[-1]}": json.loads(p.read_text())["verdict"]
    for run in ("b", "c")
    for p in sorted((EV / f"run-{run}").glob("verdict-iter*.json"))
}

# stage label -> run in scores_table.md. "B impl N" = the implementer's last replay before verifier N.
STAGES = [
    ("baseline 1", "baseline"),
    ("baseline 2", "baseline-2"),
    ("baseline 3", "baseline-3"),
    ("schema change", "post-fault"),
    ("B impl 1", "impl-rvl87f3-renames-casing-nofilter-2"),
    ("B verify 1", "verifier-rvl-87f3dbe9-iter1"),
    ("B impl 2", "impl-rvl87f3-iter2-head-recheck-2"),
    ("B verify 2", "verifier-rvl-87f3dbe9-iter2"),
    ("B impl 3", "impl-rvl87f3-iter3-superl-2"),
    ("B verify 3", "verifier-rvl-87f3dbe9-iter3"),
    ("C impl", "impl-rvl-d42b3a50-iter1-general-prompt-v2"),
    ("C verify", "verifier-rvl-d42b3a50-iter1"),
]
X = {lab: i for i, (lab, _) in enumerate(STAGES)}
rep = [rows[r]["replay"] * 100 for _, r in STAGES]
ctl = [rows[r]["control"] * 100 for _, r in STAGES]
ORACLE_PTS = [
    ("baseline 2", "baseline"),
    ("schema change", "post-fault"),
    ("B verify 3", "run-b"),
    ("C verify", "run-c"),
]
C1 = 0.8110  # prompts/verifier.md: baseline mean - max(1 pp, spread)

# ---- 1. timeline ------------------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(11, 5.2))
xs = list(range(len(STAGES)))
ax.set_xlim(-1.25, len(STAGES) - 0.4)
ax.set_ylim(0, 106)

b0, b1, c0, c1 = X["B impl 1"] - 0.5, X["B verify 3"] + 0.5, X["C impl"] - 0.5, X["C verify"] + 0.5
for lo, hi, text in (
    (b0, b1, "Run B — fix workspace files (3 iterations)"),
    (c0, c1, "Run C — prompt-only (1 iteration)"),
):
    ax.axvspan(lo, hi, color="#eeeeee", zorder=0, lw=0)
    ax.text(
        (lo + hi) / 2,
        1.012,
        text,
        transform=ax.get_xaxis_transform(),
        ha="center",
        va="bottom",
        fontsize=FS["label"],
        fontweight="bold",
        color="#444",
    )
ax.axvline(c0, color="white", lw=2, zorder=0)

inj = X["schema change"] - 0.5
ax.axvline(inj, color=RED, ls="--", lw=1.2, zorder=1)
ax.annotate(
    "schema change\n(4 columns renamed)",
    (inj, 22),
    xytext=(3, 0),
    textcoords="offset points",
    fontsize=FS["note"],
    color=RED,
    va="top",
)

for stage, key in (("B verify 1", "b1"), ("B verify 2", "b2"), ("B verify 3", "b3"), ("C verify", "c1")):
    ax.axvline(X[stage], color=GREEN if verdicts[key] == "pass" else DARKRED, ls="--", lw=1.2, zorder=1)

ax.axhline(C1 * 100, color="#555", ls=":", lw=1, zorder=1)
ax.text(-1.2, C1 * 100 + 1.2, f"C1 threshold\n{C1 * 100:.1f} %", fontsize=FS["note"], color="#555", va="bottom")

ax.plot(xs, rep, color=BLUE, lw=1.6, marker="o", ms=4.5, zorder=4)
ax.plot(xs, ctl, color=ORANGE, lw=1.6, marker="s", ms=4, zorder=3)
ox = [X[s] for s, _ in ORACLE_PTS]
oy = [oracle[k] * 100 for _, k in ORACLE_PTS]
ax.plot(ox, oy, color=PURPLE, lw=1.4, ls="--", marker="D", ms=4.5, zorder=5)
# schema-notes-only workspace (first implementer commit of Run B), scored on the oracle: separate, unconnected point
ax.plot(
    [X["B verify 1"]],
    [oracle["run-b-notes-only"] * 100],
    ls="none",
    marker="D",
    ms=4.5,
    mfc="white",
    mec=PURPLE,
    mew=1.2,
    zorder=5,
)

for i, v in enumerate(rep):
    above = i < 3  # keep baseline labels clear of the C1 threshold line
    ax.annotate(
        f"{v:.0f}",
        (i, v),
        xytext=(-6, 3 if above else -3),  # lower-left of the point: clear of the verdict lines and oracle labels
        textcoords="offset points",
        ha="right",
        va="bottom" if above else "top",
        fontsize=FS["note"],
        color=BLUE,
    )
for i, v in enumerate(ctl):
    if v < 100:
        ax.annotate(
            f"{round(v / 5)}/20",
            (i, v),
            xytext=(4, 4),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=FS["note"],
            color=ORANGE,
        )
for x, y in zip(ox, oy, strict=True):
    ax.annotate(
        f"{y:.0f}",
        (x, y),
        xytext=(5, 0),
        textcoords="offset points",
        ha="left",
        va="center",
        fontsize=FS["note"],
        color=PURPLE,
    )
nx, ny = X["B verify 1"], oracle["run-b-notes-only"] * 100
ax.annotate(
    f"{ny:.0f} (schema notes only)",
    (nx, ny),
    xytext=(6, 0),
    textcoords="offset points",
    ha="left",
    va="center",
    fontsize=FS["note"],
    color=PURPLE,
)

BOXES = [
    ("B verify 1", "REJECTED\nC2: control 19/20\n(q837 regressed)", DARKRED),
    ("B verify 2", "REJECTED\nC2: control 19/20", DARKRED),
    ("B verify 3", "PASS 93 %\ncontrol 20/20\noracle 90 %", GREEN),
    ("C verify", "FAIL 38 %\ncontrol 19/20\noracle 38 %", DARKRED),
]
for stage, text, color in BOXES:
    ax.text(
        X[stage],
        3,
        text,
        ha="center",
        va="bottom",
        fontsize=FS["box"],
        color=color,
        zorder=6,
        bbox={"boxstyle": "round", "fc": "white", "ec": color, "lw": 1},
    )

ax.set_xticks(xs)
ax.set_xticklabels([s for s, _ in STAGES], rotation=30, ha="right", rotation_mode="anchor", fontsize=FS["tick"])
ax.set_yticks(range(0, 101, 20))
ax.set_ylabel("exec_match, %", fontsize=FS["label"])
ax.grid(axis="y", alpha=0.3)
ax.legend(
    handles=[
        Line2D([], [], color=BLUE, marker="o", ms=4.5, lw=1.6, label="exec_match, replay (60 items, visible to Nerve)"),
        Line2D([], [], color=ORANGE, marker="s", ms=4, lw=1.6, label="exec_match, control (20 items)"),
        Line2D([], [], color=PURPLE, marker="D", ms=4.5, lw=1.4, ls="--", label="exec_match, hidden oracle (60 items)"),
        Line2D([], [], color="#555", lw=1, ls=":", label=f"C1 threshold {C1 * 100:.1f} %"),
    ],
    loc="lower left",
    fontsize=FS["note"],
    frameon=True,
    framealpha=1,
    edgecolor="#ccc",
)
fig.suptitle(
    "One schema change, two fixes — text-to-SQL agent · Nerve review loop · Langfuse scores", fontsize=FS["title"]
)
fig.tight_layout()
fig.savefig(OUTD / "scores_timeline.png", dpi=DPI)
plt.close(fig)

# ---- 2. summary bars: replay vs hidden oracle ---------------------------------------------------------------
base = sum(rows[r]["replay"] for r in ("baseline", "baseline-2", "baseline-3")) / 3
groups = [
    ("baseline (mean of 3)", base, oracle["baseline"]),
    ("after schema change", rows["post-fault"]["replay"], oracle["post-fault"]),
    ("Run B fix (verifier replay)", rows["verifier-rvl-87f3dbe9-iter3"]["replay"], oracle["run-b"]),
    ("Run C prompt-only (verifier replay)", rows["verifier-rvl-d42b3a50-iter1"]["replay"], oracle["run-c"]),
]
fig, ax = plt.subplots(figsize=(11, 5))
w = 0.36
for i, (_, r, o) in enumerate(groups):
    for dx, v, c in ((-w / 2 - 0.01, r, BAR_BLUE), (w / 2 + 0.01, o, BAR_ORANGE)):
        ax.bar(i + dx, v * 100, w, color=c, zorder=3)
        ax.text(i + dx, v * 100 + 1.5, f"{v * 100:.0f}%", ha="center", fontsize=FS["label"])
ax.set_xticks(range(len(groups)))
ax.set_xticklabels([g[0] for g in groups], fontsize=FS["label"])
ax.set_ylim(0, 105)
ax.set_ylabel("exec_match, %", fontsize=FS["label"])
ax.grid(axis="y", alpha=0.3, zorder=0)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(
    handles=[
        plt.Rectangle((0, 0), 1, 1, color=BAR_BLUE, label="replay (60, visible to Nerve)"),
        plt.Rectangle((0, 0), 1, 1, color=BAR_ORANGE, label="oracle (60, hidden, scored locally)"),
    ],
    loc="upper center",
    bbox_to_anchor=(0.5, -0.1),
    ncol=2,
    frameon=False,
    fontsize=FS["label"],
)
ax.set_title("Visible replay set vs hidden oracle set", loc="left", fontsize=FS["title"])
fig.tight_layout()
fig.savefig(OUTD / "summary.png", dpi=DPI)
plt.close(fig)
print("wrote", OUTD / "scores_timeline.png", OUTD / "summary.png")
