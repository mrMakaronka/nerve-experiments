#!/usr/bin/env python3
"""fill_verifier.py: freeze $OUT/v4-verifier.md from prompts/v4-verifier.tmpl.md + $OUT/baseline.json, and (re)build
the verifier's read-only directory ~/nerve-v4-verifier (replay.py, compare.py, queries/, baseline.json, creds.env).
$OUT defaults to runs/ (gitignored). The recorded criteria (prompts/v4-verifier.md) and evidence/ are not written."""
import hashlib, json, os, shutil, stat

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, os.environ.get("OUT", "runs")); os.makedirs(OUT, exist_ok=True)
VD = os.path.expanduser("~/nerve-v4-verifier")
b = json.load(open(os.path.join(OUT, "baseline.json")))
env = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/nerve-demo-private/v4/.env")) if "=" in l)

# verifier dir: make writable, refresh, lock read-only again
if os.path.exists(VD):
    for d, _, fs in os.walk(VD):
        os.chmod(d, 0o755)
        for f in fs: os.chmod(os.path.join(d, f), 0o644)
    shutil.rmtree(VD)
os.makedirs(os.path.join(VD, "queries"))
for f in ("replay.py", "compare.py"):
    shutil.copy(os.path.join(HERE, f), os.path.join(VD, f))
for f in ("regression.sql", "regression_c6.sql", "target.txt", "c6_excluded.txt"):
    shutil.copy(os.path.join(ROOT, "queries", f), os.path.join(VD, "queries", f))
shutil.copy(os.path.join(OUT, "baseline.json"), os.path.join(VD, "baseline.json"))
open(os.path.join(VD, "creds.env"), "w").write(
    f"CH_EXEC_USER=dashboard\nCH_EXEC_PASSWORD={env['CH_DASHBOARD_PASSWORD']}\n"
    f"CH_READ_USER=nerve_verify\nCH_READ_PASSWORD={env['CH_NERVE_VERIFY_PASSWORD']}\n")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
manifest = {os.path.relpath(os.path.join(d, f), VD): sha(os.path.join(d, f))
            for d, _, fs in os.walk(VD) for f in fs if f != "creds.env"}
json.dump(manifest, open(os.path.join(OUT, "verifier-manifest.json"), "w"), indent=1, sort_keys=True)
for d, _, fs in os.walk(VD):
    for f in fs: os.chmod(os.path.join(d, f), 0o400 if f == "creds.env" else 0o444)
for d, _, _ in os.walk(VD, topdown=False): os.chmod(d, 0o555)
assert sha(os.path.join(VD, "replay.py")) == b["replay_py_sha256"], "replay.py changed since the baseline runs"

fmt = lambda xs: ", ".join(str(x) for x in xs)
sub = {
    "VD": VD.replace(os.path.expanduser("~"), "$HOME"), "BASE_TS": b["frozen_utc"] + " UTC",
    "BASE_TOTALS": fmt(b["regression_totals_ms"]), "N_TARGET": str(len(b["target"])),
    "TARGET_LIST": fmt(f"q{n} ({b['post_fault_ratios'][str(n)]}×)" for n in b["target"]),
    "BASE_TARGET_TOTALS": fmt(b["target_totals_ms"]), "BASE_TARGET_MEAN": str(b["target_mean_ms"]),
    "BASE_TARGET_SPREAD": str(b["target_spread_ms"]), "POST_TARGET": str(b["post_fault_target_total_ms"]),
    "C1_MAX": str(b["c1_threshold_ms"]), "BASE_ROWS": str(b["rows"]), "BASE_BYTES": str(b["bytes"]),
    "C3_MAX_BYTES": str(b["c3_max_bytes"]), "REGRESSION_SHA": b["regression_sql_sha256"],
    "REPLAY_SHA": b["replay_py_sha256"],
}
t = open(os.path.join(ROOT, "prompts", "v4-verifier.tmpl.md")).read()
for k, v in sub.items(): t = t.replace("{{" + k + "}}", v)
assert "{{" not in t, t[t.index("{{"):][:40]
crit = os.path.join(OUT, "v4-verifier.md")
open(crit, "w").write(t)
print("verifier dir", VD, "files", len(manifest), "| criteria written to", crit, "; C1_MAX", sub["C1_MAX"])
