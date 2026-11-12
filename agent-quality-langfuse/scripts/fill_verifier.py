"""prompts/verifier.tmpl.md + runs/baseline.json + agent fingerprint -> runs/verifier.md (frozen criteria).

runs/ is gitignored. prompts/verifier.md holds the criteria used in the recorded runs and is never written here.
"""

import json
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V3 / "langfuse-tools"))
sys.path.insert(0, str(V3 / "agent"))
import statistics as st

import langfuse_tools as t

RUNS = ["baseline", "baseline-2", "baseline-3"]  # identical pre-fault runs: noise estimate
bs = [json.loads(t.get_run_scores(n)) for n in RUNS]
rs = [b["recomputed_from_item_scores"] for b in bs]
em = [r["exec_match_avg"] for r in rs]
ctl = {r["control_exec_match_avg"] for r in rs}
assert len(ctl) == 1, f"control differs between baselines: {ctl}"  # zero-tolerance C2 needs a stable control set
spread = max(em) - min(em)
fp = json.loads(t.agent_fingerprint())["combined"]
m = {
    "BASE_TS": f"{bs[0]['start'][:16]} – {bs[-1]['start'][11:16]} UTC",
    "BASE_EM_RUNS": ", ".join(f"{x:.4f}" for x in em),
    "BASE_EM": f"{st.mean(em):.4f}",
    "BASE_SPREAD": f"{spread * 100:.2f} pp",
    "C1_MIN": f"{st.mean(em) - max(0.01, spread):.4f}",
    "BASE_CTL": f"{ctl.pop():.4f}",
    "BASE_CTL_N": str(rs[0]["control_n"]),
    "BASE_COST": f"{st.mean(r['cost_per_q_usd'] for r in rs):.6f}",
    "BASE_P50": f"{st.mean(r['latency_p50_s'] for r in rs):.3f}",
    "BASE_FP": fp,
}
s = (V3 / "prompts/verifier.tmpl.md").read_text()
for k, v in m.items():
    s = s.replace("{{" + k + "}}", v)
assert "{{" not in s
out = V3 / "runs" / "verifier.md"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(s)
print("criteria written to", out)
print(json.dumps(m, indent=1))
