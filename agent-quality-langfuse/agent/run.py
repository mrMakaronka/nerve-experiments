"""demo-v3 system under test: a single-shot text-to-SQL agent (Claude Haiku 5.5) over BIRD `superhero`.

Prompt = workspace/prompt.md + agent/schema_snapshot.md (frozen at build time) + workspace/schema_notes.md
         + workspace/skills/*.md.  One model call, one SQL statement, no retries, no live schema access.
Tracing/scoring in Langfuse: one trace per question (generation + sql span), item scores exec_match / cost_usd /
latency_s, run scores exec_match_avg / control_exec_match_avg / cost_per_q_usd / latency_avg_s / latency_p50_s.

    run.py experiment --run-name NAME --workspace DIR [--dataset replay]   # Langfuse experiment on `replay`
    run.py oracle --label LABEL --workspace DIR                            # hidden split, local only, no tracing
    run.py ask --workspace DIR "question"                                  # one-off
Every run writes runs/<name>.json (summary + per-item rows) and prints the summary as JSON.
"""
import argparse, json, re, sqlite3, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DB, FAULT, MODEL, ORACLE, PRICE_IN, PRICE_OUT, V3, langfuse_client, load_env  # noqa: E402

SQL_TIMEOUT_S = 15


def build_system(ws: Path) -> str:
    parts = [(ws / "prompt.md").read_text(), "\n\n# Schema reference\n\n", (V3 / "agent/schema_snapshot.md").read_text()]
    notes = ws / "schema_notes.md"
    if notes.exists() and notes.read_text().strip():
        parts += ["\n\n# Schema notes (maintained by the data team; these override the reference above)\n\n", notes.read_text()]
    for sk in sorted((ws / "skills").glob("**/*.md")) if (ws / "skills").exists() else []:
        parts += [f"\n\n# Skill: {sk.stem}\n\n", sk.read_text()]
    return "".join(parts)


def run_sql(sql: str, timeout=SQL_TIMEOUT_S):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    t0 = time.monotonic()
    con.set_progress_handler(lambda: 1 if time.monotonic() - t0 > timeout else 0, 10000)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def extract_sql(text: str) -> str:
    m = re.findall(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m[-1] if m else text).strip().rstrip(";").strip()


def answer(question: str, evidence: str, ws: Path, client, lf=None):
    """Returns dict(sql, rows|None, error|None, cost_usd, latency_s, usage)."""
    system = build_system(ws)
    user = f"Question: {question}\nEvidence: {evidence or '(none)'}\n\nReturn one SQLite query in a ```sql block."
    t0 = time.monotonic()
    gen_cm = lf.start_as_current_observation(as_type="generation", name="text2sql", model=MODEL,
                                             input={"question": question, "evidence": evidence}) if lf else None
    gen = gen_cm.__enter__() if gen_cm else None
    try:
        msg = client.messages.create(model=MODEL, max_tokens=4000, system=system,
                                     output_config={"effort": "low"},
                                     messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in msg.content if b.type == "text")
        u = msg.usage
        usage = {"input": u.input_tokens, "output": u.output_tokens}
        cost = u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT
        if gen:
            gen.update(output=text, usage_details=usage,
                       cost_details={"input": u.input_tokens * PRICE_IN, "output": u.output_tokens * PRICE_OUT})
    finally:
        if gen_cm:
            gen_cm.__exit__(None, None, None)
    sql = extract_sql(text)
    rows, err = None, None
    sp_cm = lf.start_as_current_observation(as_type="tool", name="sqlite", input={"sql": sql}) if lf else None
    sp = sp_cm.__enter__() if sp_cm else None
    try:
        rows = run_sql(sql)
    except Exception as e:  # noqa: BLE001 — any DB error is an agent failure, recorded on the trace
        err = f"{type(e).__name__}: {e}"
    if sp:
        sp.update(output={"rows": [list(r) for r in rows[:20]], "row_count": len(rows)} if rows is not None else {"error": err},
                  level="ERROR" if err else "DEFAULT", status_message=err)
        sp_cm.__exit__(None, None, None)
    return {"sql": sql, "rows": rows, "error": err, "cost_usd": cost, "latency_s": time.monotonic() - t0, "usage": usage}


def exec_match(pred_rows, gold: str) -> int:
    if pred_rows is None:
        return 0
    try:
        return int(set(map(tuple, pred_rows)) == set(map(tuple, run_sql(gold, timeout=60))))
    except Exception:  # noqa: BLE001
        return 0


def summarize(name, rows, extra=None):
    em = [r["exec_match"] for r in rows]
    ctl = [r["exec_match"] for r in rows if r.get("control")]
    lat = [r["latency_s"] for r in rows]
    s = {"run_name": name, "n": len(rows), "model": MODEL, "fault": json.loads(FAULT.read_text()) if FAULT.exists() else None,
         "exec_match_avg": round(st.mean(em), 4), "control_n": len(ctl),
         "control_exec_match_avg": round(st.mean(ctl), 4) if ctl else None,
         "cost_per_q_usd": round(st.mean(r["cost_usd"] for r in rows), 6),
         "latency_avg_s": round(st.mean(lat), 3), "latency_p50_s": round(st.median(lat), 3),
         "sql_errors": sum(1 for r in rows if r["error"]), **(extra or {})}
    (V3 / "runs").mkdir(exist_ok=True)
    (V3 / "runs" / f"{name}.json").write_text(json.dumps({"summary": s, "items": rows}, indent=1, default=str))
    return s


def cmd_experiment(a):
    import anthropic
    from langfuse import Evaluation
    load_env()
    client, lf, ws = anthropic.Anthropic(max_retries=6), langfuse_client(), Path(a.workspace).resolve()
    ds = lf.get_dataset(a.dataset)
    items = list(ds.items)
    rows = {}

    def task(*, item, **_):
        r = answer(item.input["question"], item.input.get("evidence", ""), ws, client, lf)
        r["exec_match"] = exec_match(r["rows"], item.expected_output["sql"])
        rows[item.id] = {"id": item.id, "control": bool((item.metadata or {}).get("control")),
                         **{k: r[k] for k in ("sql", "error", "exec_match", "cost_usd", "latency_s")}}
        return {"sql": r["sql"], "error": r["error"], "row_count": None if r["rows"] is None else len(r["rows"]),
                "exec_match": r["exec_match"], "cost_usd": r["cost_usd"], "latency_s": r["latency_s"]}

    def ev(*, output, **_):
        return [Evaluation(name="exec_match", value=output["exec_match"], comment=output["error"]),
                Evaluation(name="cost_usd", value=output["cost_usd"]),
                Evaluation(name="latency_s", value=output["latency_s"])]

    def run_ev(*, item_results, **_):
        rs = list(rows.values())
        em = st.mean(r["exec_match"] for r in rs)
        ctl = [r["exec_match"] for r in rs if r["control"]]
        lat = [r["latency_s"] for r in rs]
        return [Evaluation(name="exec_match_avg", value=em),
                Evaluation(name="control_exec_match_avg", value=st.mean(ctl) if ctl else -1),
                Evaluation(name="cost_per_q_usd", value=st.mean(r["cost_usd"] for r in rs)),
                Evaluation(name="latency_avg_s", value=st.mean(lat)),
                Evaluation(name="latency_p50_s", value=st.median(lat))]

    res = ds.run_experiment(name="text2sql-superhero", run_name=a.run_name, task=task, evaluators=[ev],
                            run_evaluators=[run_ev], max_concurrency=a.concurrency,
                            metadata={"workspace": str(ws), "model": MODEL})
    lf.flush()
    failed = [i for i in items if i.id not in rows]
    s = summarize(a.run_name, [rows[k] for k in sorted(rows)],
                  {"dataset": a.dataset, "langfuse_dataset_run_id": res.experiment_id,
                   "langfuse_url": res.experiment_url, "task_failures": len(failed)})
    print(json.dumps(s, indent=1))


def cmd_oracle(a):
    import anthropic
    load_env()
    client, ws = anthropic.Anthropic(max_retries=6), Path(a.workspace).resolve()
    items = [json.loads(l) for l in ORACLE.read_text().splitlines()]
    gold = {}
    if FAULT.exists():  # gold SQL regenerated for the current schema by inject.py
        gold = json.loads(FAULT.read_text()).get("oracle_gold", {})

    def one(it):
        r = answer(it["input"]["question"], it["input"]["evidence"], ws, client)
        return {"id": it["id"], "control": False, "sql": r["sql"], "error": r["error"],
                "exec_match": exec_match(r["rows"], gold.get(it["id"], it["expected_output"]["sql"])),
                "cost_usd": r["cost_usd"], "latency_s": r["latency_s"]}

    with ThreadPoolExecutor(a.concurrency) as ex:
        rows = list(ex.map(one, items))
    print(json.dumps(summarize(f"oracle-{a.label}", rows, {"dataset": "oracle (local)"}), indent=1))


def cmd_ask(a):
    import anthropic
    load_env()
    r = answer(a.question, a.evidence, Path(a.workspace).resolve(), anthropic.Anthropic())
    print(json.dumps({k: v for k, v in r.items() if k != "rows"} | {"rows": (r["rows"] or [])[:10]}, indent=1, default=str))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("experiment"); e.add_argument("--run-name", required=True); e.add_argument("--workspace", required=True)
    e.add_argument("--dataset", default="replay"); e.add_argument("--concurrency", type=int, default=6)
    o = sub.add_parser("oracle"); o.add_argument("--label", required=True); o.add_argument("--workspace", required=True)
    o.add_argument("--concurrency", type=int, default=6)
    q = sub.add_parser("ask"); q.add_argument("--workspace", required=True); q.add_argument("question"); q.add_argument("--evidence", default="")
    a = p.parse_args()
    {"experiment": cmd_experiment, "oracle": cmd_oracle, "ask": cmd_ask}[a.cmd](a)
