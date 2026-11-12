#!/usr/bin/env python3
"""Replay a ClickBench query set against bench.hits and read the timings back from system.query_log.

    replay.py --run-id ID --set regression|target|c6|control [--repeat 4] [--out FILE]

Python standard library only (ClickHouse HTTP interface), so the verifier can run its read-only copy
without a venv. Two identities:
  * exec  (default user `dashboard`): runs the queries in a fresh HTTP session each time, under its own
    persisted settings profile. Nothing is SET by this script except log_comment, use_query_cache=0 and
    a per-query query_id.
  * read  (`nerve_verify` for the verifier, `v4admin` for the operator): waits for merges/mutations,
    runs SYSTEM FLUSH LOGS and reads system.query_log.
Credentials: env CH_EXEC_USER / CH_EXEC_PASSWORD / CH_READ_USER / CH_READ_PASSWORD, or --creds FILE
with those KEY=VALUE lines. Host/port: CH_HOST (127.0.0.1) / CH_PORT (18123).

Per query: each statement runs --repeat times; the first (cold) run is discarded, and the median of the
remaining runs is taken for query_duration_ms, read_rows, read_bytes and memory_usage, all from
system.query_log (never from the client clock). Result hash: rows of the last run, floats rounded to
6 significant digits, rows sorted, sha256 over the canonical serialisation.

Query sets resolve relative to --queries-dir (default: ../queries next to this file):
  regression -> regression.sql (43 statements, one per line), target -> target.txt (1-based numbers into
  regression.sql), c6 -> regression_c6.sql minus c6_excluded.txt, control -> $CH_CONTROL_SQL (operator only).
"""

import argparse
import base64
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def load_creds(path):
    if path:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)
    need = ["CH_EXEC_USER", "CH_EXEC_PASSWORD", "CH_READ_USER", "CH_READ_PASSWORD"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing credentials: {missing} (env or --creds)")
    return (os.environ["CH_EXEC_USER"], os.environ["CH_EXEC_PASSWORD"]), (
        os.environ["CH_READ_USER"], os.environ["CH_READ_PASSWORD"])


class CH:
    def __init__(self, user, password, host, port):
        self.base = f"http://{host}:{port}/"
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.user = user

    def query(self, sql, params=None, timeout=3600):
        url = self.base + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, data=sql.encode(), headers={"Authorization": self.auth})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode()[:2000]) from None

    def json(self, sql, params=None):
        p = dict(params or {})
        out = self.query(sql + "\nFORMAT JSONCompact", p)
        return json.loads(out)


def split_statements(path):
    lines = [ln.strip() for ln in open(path)]
    return [ln.rstrip(";") for ln in lines if ln and not ln.startswith("--")]


def resolve_set(name, qdir):
    reg = split_statements(os.path.join(qdir, "regression.sql"))
    if name == "regression":
        return [(i + 1, q) for i, q in enumerate(reg)]
    if name == "target":
        nums = [int(ln.split()[0]) for ln in open(os.path.join(qdir, "target.txt"))
                if ln.strip() and not ln.startswith("#")]
        return [(n, reg[n - 1]) for n in nums]
    if name == "c6":
        twins = split_statements(os.path.join(qdir, "regression_c6.sql"))
        excl_path = os.path.join(qdir, "c6_excluded.txt")
        excl = set()
        if os.path.exists(excl_path):
            excl = {int(ln.split()[0]) for ln in open(excl_path) if ln.strip() and not ln.startswith("#")}
        return [(i + 1, q) for i, q in enumerate(twins) if i + 1 not in excl]
    if name == "control":
        path = os.environ.get("CH_CONTROL_SQL")
        if not path:
            sys.exit("control set needs CH_CONTROL_SQL (operator only)")
        return [(i + 1, q) for i, q in enumerate(split_statements(path))]
    sys.exit(f"unknown set {name}")


def canon_value(v, typ):
    if v is None:
        return "\\N"
    if "Float" in typ and isinstance(v, (int, float)):
        return format(float(v), ".6g")
    if isinstance(v, (list, dict)):
        return json.dumps(v, sort_keys=True)
    return str(v)


def result_hash(res):
    types = [m["type"] for m in res["meta"]]
    rows = sorted("\t".join(canon_value(v, t) for v, t in zip(row, types)) for row in res["data"])
    h = hashlib.sha256()
    h.update(("|".join(types) + "\n").encode())
    for r in rows:
        h.update(r.encode() + b"\n")
    return h.hexdigest()[:16], len(rows)


def wait_quiet(reader, timeout_s=300):
    t0 = time.time()
    while True:
        res = reader.json("SELECT (SELECT count() FROM system.merges WHERE database = 'bench'), "
                          "(SELECT count() FROM system.mutations WHERE database = 'bench' AND NOT is_done)")
        merges, mutations = res["data"][0]
        if merges == 0 and mutations == 0:
            return {"waited_s": round(time.time() - t0, 1), "timeout_hit": False}
        if time.time() - t0 > timeout_s:
            return {"waited_s": round(time.time() - t0, 1), "timeout_hit": True,
                    "merges": merges, "mutations": mutations}
        time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--set", required=True, choices=["regression", "target", "c6", "control"])
    ap.add_argument("--repeat", type=int, default=4)
    ap.add_argument("--out")
    ap.add_argument("--creds")
    ap.add_argument("--queries-dir", default=os.path.join(HERE, "..", "queries"))
    ap.add_argument("--merge-timeout", type=int, default=300)
    a = ap.parse_args()
    if a.set == "control" and not a.run_id.startswith("ctl-"):
        sys.exit("control run ids must start with ctl- (hidden from the agents by a row policy)")
    if a.set != "control" and a.run_id.startswith("ctl-"):
        sys.exit("ctl- prefix is reserved for the control set")
    if a.set == "c6":
        a.repeat = 1  # correctness only; timings always come from the original statements

    (eu, ep), (ru, rp) = load_creds(a.creds)
    host, port = os.environ.get("CH_HOST", "127.0.0.1"), os.environ.get("CH_PORT", "18123")
    execu, reader = CH(eu, ep, host, port), CH(ru, rp, host, port)
    queries = resolve_set(a.set, os.path.abspath(a.queries_dir))
    self_sha = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()

    out = {"run_id": a.run_id, "set": a.set, "repeat": a.repeat, "exec_user": eu, "read_user": ru,
           "replay_py_sha256": self_sha, "queries_dir": os.path.abspath(a.queries_dir),
           "server_version": reader.query("SELECT version()").strip()}
    out["merge_wait"] = wait_quiet(reader, a.merge_timeout)
    out["started_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{a.run_id}] {a.set}: {len(queries)} queries x {a.repeat}, exec as {eu}", file=sys.stderr)

    per = {}
    for n, sql in queries:
        hashes, err = [], None
        for r in range(1, a.repeat + 1):
            qid = f"{a.run_id}-q{n:02d}-r{r}"
            params = {"log_comment": a.run_id, "use_query_cache": "0", "query_id": qid}
            try:
                res = execu.json(sql, params)
                hashes.append(result_hash(res))
            except Exception as e:  # recorded, not fatal: a failing query is a finding
                err = str(e)[:500]
                break
        per[n] = {"n": n, "sql_sha256": hashlib.sha256(sql.encode()).hexdigest()[:16], "error": err,
                  "result_hash": hashes[-1][0] if hashes else None,
                  "result_rows": hashes[-1][1] if hashes else None,
                  "hash_stable_across_repeats": len({h for h, _ in hashes}) <= 1}
        print(f"  q{n:02d} done{' ERROR' if err else ''}", file=sys.stderr)
    out["ended_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    reader.query("SYSTEM FLUSH LOGS")
    log = reader.json(
        "SELECT query_id, user, type, query_duration_ms, read_rows, read_bytes, memory_usage, "
        "toString(Settings) FROM system.query_log "
        "WHERE event_date >= yesterday() AND log_comment = {rid:String} "
        "AND type IN ('QueryFinish', 'ExceptionWhileProcessing', 'ExceptionBeforeStart')",
        {"param_rid": a.run_id})
    rows = {}
    for qid, user, typ, dur, rr, rb, mem, settings in log["data"]:
        n, r = qid[len(a.run_id) + 2:].split("-r")
        rows[(int(n), int(r))] = {"user": user, "type": typ, "ms": int(dur), "read_rows": int(rr),
                                  "read_bytes": int(rb), "memory": int(mem), "settings": settings}
    out["query_log_rows"] = len(rows)
    warm_from = 2 if a.repeat > 1 else 1
    for n, q in per.items():
        runs = [rows.get((n, r)) for r in range(1, a.repeat + 1)]
        q["query_log_runs"] = [None if x is None else {k: x[k] for k in ("ms", "read_rows", "type")} for x in runs]
        warm = [x for x in runs[warm_from - 1:] if x and x["type"] == "QueryFinish"]
        if warm:
            q["median_ms"] = statistics.median(x["ms"] for x in warm)
            q["read_rows"] = int(statistics.median(x["read_rows"] for x in warm))
            q["read_bytes"] = int(statistics.median(x["read_bytes"] for x in warm))
            q["memory_usage"] = int(statistics.median(x["memory"] for x in warm))
            q["log_user"] = warm[0]["user"]
            q["log_settings"] = warm[0]["settings"]
        else:
            q["median_ms"] = None
    meds = [q["median_ms"] for q in per.values() if q["median_ms"] is not None]
    out["totals"] = {
        "queries": len(per), "ok": len(meds), "errors": sum(1 for q in per.values() if q["error"]),
        "total_median_ms": sum(meds) if meds else None,
        "p95_median_ms": (sorted(meds)[max(0, int(round(0.95 * len(meds))) - 1)] if meds else None),
        "total_read_rows": sum(q.get("read_rows", 0) for q in per.values()),
    }
    out["queries"] = [per[n] for n in sorted(per)]
    text = json.dumps(out, indent=1)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        open(a.out, "w").write(text + "\n")
    t = out["totals"]
    print(f"[{a.run_id}] total_median_ms={t['total_median_ms']} p95={t['p95_median_ms']} ok={t['ok']}/{t['queries']} "
          f"query_log_rows={out['query_log_rows']} merge_wait={out['merge_wait']}", file=sys.stderr)
    if not a.out:
        print(text)


if __name__ == "__main__":
    main()
