"""langfuse-tools: stdio MCP server that gives Nerve legs read access to the text2sql project in self-hosted Langfuse
and a way to replay the `replay` dataset against a workspace (demo-v3).

Tools
  list_runs(limit)                    recent experiment runs on `replay` with their run-level scores
  get_run_scores(run_name)            run-level scores + per-item exec_match/cost/latency, read back from Langfuse
  get_failed_traces(run_name, limit)  items with exec_match = 0: question, evidence, generated SQL, DB error, expected SQL
  run_experiment(run_name, workspace_dir)  run the agent over `replay` with that workspace; returns the summary + run id
  describe_live_db()                  live column list of every table in the agent's SQLite DB
  agent_fingerprint()                 sha256 of the agent's code and frozen schema reference (C4 check)

Run: agent-quality-langfuse/.venv/bin/python agent-quality-langfuse/langfuse-tools/langfuse_tools.py   (Nerve config: mcp_servers.langfuse-tools)
"""

import datetime as dt
import hashlib
import json
import re
import sqlite3
import statistics as st
import subprocess
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

V3 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V3 / "agent"))
from common import DB, langfuse_client

mcp = MCPServer("langfuse-tools")
SINCE_DAYS = 14


def _lf():
    return langfuse_client()


def _since():
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=SINCE_DAYS)


def _runs(lf, name=None):
    out, cursor = [], None
    while True:
        r = lf.api.experiments.list(
            from_start_time=_since(), fields="core,metadata,scores", limit=100, name=name, cursor=cursor
        )
        out += [e for e in r.data if not e.name.startswith("mock-")]
        cursor = getattr(r.meta, "cursor", None) or getattr(r.meta, "next_cursor", None)
        if not cursor or not r.data:
            return out


def _items(lf, experiment_id):
    out, cursor = [], None
    while True:
        r = lf.api.experiments.list_items(
            from_start_time=_since(),
            experiment_id=experiment_id,
            fields="core,io,itemMetadata,scores",
            limit=100,
            cursor=cursor,
        )
        out += r.data
        cursor = getattr(r.meta, "cursor", None) or getattr(r.meta, "next_cursor", None)
        if not cursor or not r.data:
            return out


def _j(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except ValueError:
            return x
    return x


def _run_by_name(lf, run_name):
    rs = [e for e in _runs(lf) if e.name == run_name]
    if not rs:
        raise ValueError(f"no experiment run named {run_name!r} in the last {SINCE_DAYS} days; see list_runs")
    return rs[0]


def _control_ids(lf):
    """Control membership from the current `replay` dataset (not the per-run snapshot)."""
    return {i.id for i in lf.get_dataset("replay").items if str((i.metadata or {}).get("control")).lower() == "true"}


def _scores(e):
    return {s.name: round(s.value, 6) for s in (e.scores or []) if isinstance(s.value, (int, float))}


@mcp.tool()
def list_runs(limit: int = 20) -> str:
    """Recent experiment runs on the `replay` dataset (newest first) with run-level scores:
    exec_match_avg, control_exec_match_avg, cost_per_q_usd, latency_avg_s, latency_p50_s."""
    lf = _lf()
    rows = [
        {
            "run_name": e.name,
            "experiment_id": e.id,
            "start": str(e.start_time),
            "items": e.item_count,
            "scores": _scores(e),
        }
        for e in _runs(lf)[:limit]
    ]
    return json.dumps(rows, indent=1)


@mcp.tool()
def get_run_scores(run_name: str) -> str:
    """Scores of one run, read back from Langfuse: run-level scores as stored by the run, plus per-item
    exec_match / cost_usd / latency_s and aggregates recomputed from the item scores (all items and the
    20-item `control` subset). Use this to read results; do not trust numbers quoted elsewhere."""
    lf = _lf()
    e = _run_by_name(lf, run_name)
    items = _items(lf, e.id)
    ctl_ids = _control_ids(lf)
    per = []
    for it in items:
        sc = {s.name: s.value for s in (it.scores or [])}
        per.append(
            {
                "item": it.experiment_item_id,
                "control": it.experiment_item_id in ctl_ids,
                "exec_match": sc.get("exec_match"),
                "cost_usd": sc.get("cost_usd"),
                "latency_s": sc.get("latency_s"),
            }
        )
    em = [p["exec_match"] for p in per if p["exec_match"] is not None]
    ctl = [p["exec_match"] for p in per if p["control"] and p["exec_match"] is not None]
    lat = [p["latency_s"] for p in per if p["latency_s"] is not None]
    cost = [p["cost_usd"] for p in per if p["cost_usd"] is not None]
    recomputed = {
        "n_scored": len(em),
        "exec_match_avg": round(st.mean(em), 4) if em else None,
        "control_n": len(ctl),
        "control_exec_match_avg": round(st.mean(ctl), 4) if ctl else None,
        "cost_per_q_usd": round(st.mean(cost), 6) if cost else None,
        "latency_avg_s": round(st.mean(lat), 3) if lat else None,
        "latency_p50_s": round(st.median(lat), 3) if lat else None,
    }
    return json.dumps(
        {
            "run_name": e.name,
            "experiment_id": e.id,
            "start": str(e.start_time),
            "workspace": (e.metadata or {}).get("workspace"),
            "run_scores": _scores(e),
            "note": "control membership = current `replay` dataset metadata; run_scores were computed at run time",
            "recomputed_from_item_scores": recomputed,
            "items": sorted(per, key=lambda p: p["item"]),
        },
        indent=1,
    )


@mcp.tool()
def get_failed_traces(run_name: str, limit: int = 30) -> str:
    """Items of a run that scored exec_match = 0, with the question, evidence, the SQL the agent generated,
    the SQLite error (if the query failed), the expected SQL and the Langfuse trace id."""
    lf = _lf()
    e = _run_by_name(lf, run_name)
    out, ctl_ids = [], _control_ids(lf)
    for it in _items(lf, e.id):
        sc = {s.name: s.value for s in (it.scores or [])}
        if sc.get("exec_match") == 0:
            o, i, x = _j(it.output) or {}, _j(it.input) or {}, _j(it.expected_output) or {}
            out.append(
                {
                    "item": it.experiment_item_id,
                    "trace_id": it.trace_id,
                    "control": it.experiment_item_id in ctl_ids,
                    "question": i.get("question"),
                    "evidence": i.get("evidence"),
                    "generated_sql": o.get("sql"),
                    "error": o.get("error"),
                    "expected_sql": x.get("sql"),
                }
            )
    out.sort(key=lambda r: r["item"])
    return json.dumps(
        {"run_name": run_name, "failed": len(out), "shown": min(len(out), limit), "items": out[:limit]}, indent=1
    )


@mcp.tool()
def run_experiment(run_name: str, workspace_dir: str) -> str:
    """Run the text-to-SQL agent over all 60 `replay` items with the prompt/notes/skills in `workspace_dir`
    (absolute path of a directory containing prompt.md, schema_notes.md, skills/). Scores (exec_match,
    cost_usd, latency_s and run-level aggregates) are written to Langfuse under `run_name`. Takes ~1-3 min.
    run_name must be new (letters, digits, - _ .)."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", run_name):
        return json.dumps({"error": "run_name must match [A-Za-z0-9._-]{3,80}"})
    ws = Path(workspace_dir).expanduser().resolve()
    if not (ws / "prompt.md").exists():
        return json.dumps({"error": f"{ws} has no prompt.md"})
    lf = _lf()
    if any(e.name == run_name for e in _runs(lf)):
        return json.dumps({"error": f"run_name {run_name!r} already exists; pick a new one"})
    p = subprocess.run(
        [sys.executable, str(V3 / "agent/run.py"), "experiment", "--run-name", run_name, "--workspace", str(ws)],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if p.returncode != 0:
        return json.dumps({"error": "experiment failed", "stderr_tail": p.stderr[-1500:]})
    s = json.loads(p.stdout[p.stdout.index("{") :])
    s.pop("fault", None)
    s.pop("langfuse_url", None)
    return json.dumps(s, indent=1)


@mcp.tool()
def describe_live_db() -> str:
    """Live schema of the agent's SQLite database (tables and their current columns), read with PRAGMA."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        tabs = [t for (t,) in con.execute("select name from sqlite_master where type='table' order by name")]
        return json.dumps({t: [r[1] for r in con.execute(f'pragma table_info("{t}")')] for t in tabs}, indent=1)
    finally:
        con.close()


@mcp.tool()
def agent_fingerprint() -> str:
    """sha256 of the agent's code and frozen schema reference. Equal to the baseline value means the
    system under test (outside the workspace) was not modified."""
    files = ["agent/run.py", "agent/common.py", "agent/schema_snapshot.md"]
    h = {f: hashlib.sha256((V3 / f).read_bytes()).hexdigest() for f in files}
    combined = hashlib.sha256("".join(h[f] for f in files).encode()).hexdigest()
    return json.dumps({"combined": combined, "files": h}, indent=1)


if __name__ == "__main__":
    mcp.run()
