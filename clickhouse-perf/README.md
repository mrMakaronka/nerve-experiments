# clickhouse-perf (demo-v4): a third signal, ClickHouse's own `system.query_log`

This case runs the Nerve review loop from demo-v1..v3, **with no changes to Nerve core**, on database performance telemetry.

- **Scenario.** ClickBench `hits` (100M rows) is recreated with the wrong sorting key.
- **Implementer.** Has to fix the schema persistently for the workload identity `dashboard`.
- **Verifier.** Replays the 43-query workload itself and judges C1–C7 from `system.query_log` and result hashes.
- **Negative cases.** A settings-only attempt (Run C) and a scripted wrong fix (10b) must be rejected with numbers.

Results and caveats: [FINDINGS.md](FINDINGS.md).

| Run | Verdict | Verifier numbers |
|---|---|---|
| Run B (schema fix allowed) | pass, iteration 1 | target 254 ≤ 271 ms; 0 C2 violations; 43/43 hashes |
| Run C (settings and skip indexes only) | fail ×2 | target 572 / 578 ms; 13 C2 violations; 25.9 GB > 22.9 GB |
| 10b (bloom_filter on URL + `max_threads = 32`) | fail | target 576 ms; 14 C2 violations |

These are the clean runs (criteria v2, server restarted before each run). The three earlier attempts are kept in `evidence/` and explained in FINDINGS §3–§5.

## Layout

| Path | What |
|---|---|
| `prompts/run-b-goal.md`, `run-c-goal.md`, `10b-goal.md` | Goals as given to the implementer |
| `prompts/v4-verifier.md` (`.tmpl.md`) | verifier criteria **v2** (filled / template); `v4-verifier.v1*.md` = v1 |
| `skills/clickhouse-diagnostics/SKILL.md` | tool-level skill (query_log by log_comment, EXPLAIN indexes, metadata); no root-cause hint |
| `queries/regression.sql`, `regression_c6.sql`, `target.txt`, `c6_excluded.txt` | the 43 ClickBench queries (commit 3e064d9), their deterministic C6 twins, the frozen target set |
| `scripts/replay.py`, `compare.py` | stdlib replay (fresh HTTP session per query as `dashboard`, timings from `query_log`, result hashes) and the C1/C2/C6 arithmetic; the verifier gets read-only copies |
| `scripts/init-private.sh`, `ch-up.sh` | operator-only inputs (passwords, admin user) outside the repo; the pinned server container |
| `scripts/load.sh`, `inject.sh`, `snapshot.sh`, `reset.sh`, `server-restart.sh`, `envcheck.sh` (+ `envcheck_verdict.py`), `leakcheck.sh`, `negative_control.sh` | build, fault, hard-link snapshots, reset (incl. server restart), environment check, pre-run leak check, 10b |
| `scripts/grants.sql.tmpl` | identities: `dashboard`, `nerve_rw` (implementer), `nerve_verify` (verifier); row policies that hide the control set and earlier runs |
| `scripts/extract_runs.py`, `plot_v4.py` | per-replay medians from `query_log` → `runs-summary.json` → figures (`plot_v4.py` reads the recorded `evidence/`, writes PNGs to `runs/`) |
| `evidence/` | baseline, fault, every run (verdicts with the verifier's SQL and numbers, STATE.md, transcripts, DDL from `query_log`), env checks, control summary, figures |

**Not in the repo**, by design. These live in `~/nerve-demo-private/v4/` (mode 700):
- passwords (`.env`), the admin users.d file and the operator's replay credentials (`creds-operator.env`).
  `scripts/init-private.sh` creates all three with random passwords and never overwrites existing files;
- the hidden control set `control.sql` and its replay files. The recorded set stays private; for a reproduction
  write your own (format in the header of `init-private.sh`);
- the Nerve memory quarantine.

`evidence/control-summary.json` holds only totals and hash equality. Home-directory paths in transcripts are shown as `~`.

## Reproduce

Pins: ClickHouse `clickhouse/clickhouse-server:26.8.36.3@sha256:d426d2f6…`, ClickBench 3e064d9 (100 partitioned parquet files), mcp-clickhouse 0.7.0, Nerve and Codex as in [../PINS.md](../PINS.md).

New output goes to `clickhouse-perf/runs/` (gitignored; `OUT=` overrides it). `evidence/` is the record of the runs
and no script writes to it. Commands below run from `clickhouse-perf/`.

0. **Private inputs.** `scripts/init-private.sh`, then write `~/nerve-demo-private/v4/control.sql`.
1. **Server.** A dedicated host with ≥ 16 GB free for the container (`scripts/ch-up.sh`; the recorded runs used
   `--memory 16g`, `CH_MEMORY` overrides it), reachable on `127.0.0.1:18123`. `scripts/server-restart.sh` uses
   `BENCH_RESTART_CMD` to restart it.
2. **Load and identities.** `python3 scripts/apply_sql.py scripts/grants.sql.tmpl`, then `scripts/load.sh` (95 s on the bench host), then `scripts/snapshot.sh good`.
3. **Baseline.** `scripts/baseline.sh`: three ×4 regression replays, the c6 twins and the control set.
4. **Fault.** `scripts/inject.sh`. Then the `post-fault` replay
   (`python3 scripts/replay.py --creds ~/nerve-demo-private/v4/creds-operator.env --set regression --repeat 4 --run-id post-fault --out runs/post-fault.json`)
   and `scripts/snapshot.sh faulted`. `queries/target.txt` holds the recorded frozen target set; a new run that
   selects its own set changes that file.
5. **Verifier inputs.** `scripts/make_baseline.py`, then `scripts/fill_verifier.py`. This writes `~/nerve-v4-verifier/`
   (read-only), `runs/baseline.json` and the filled criteria `runs/v4-verifier.md`.
6. **Nerve MCP servers.** Add `clickhouse-v4-rw` (user `nerve_rw`, write and drop allowed) and `clickhouse-v4-verify` (user `nerve_verify`) to the Nerve workspace config, plus the Codex approve and timeout overrides. Restart the gateway.
7. **Before every run:**
   - `scripts/reset.sh faulted` (restarts the server);
   - `REF=runs scripts/envcheck.sh <id>`: exit 0 only if the server matches `post-fault` (rule v2, q23 excluded,
     FINDINGS §4). Without `REF=runs` it compares with the recorded reference in `evidence/`;
   - `scripts/leakcheck.sh --allow-loop <run>`: exit 0 only if no earlier loop repo, agent scratch file or Nerve
     lesson carries a solution. It is diagnostic only, and the checkout itself is a known exposure (FINDINGS §5);
   - `scripts/make_loop_repo.sh ~/nerve-v4-loops/<run>`.

   Then start the loop (from the repository root):
   ```
   python3 sre-clickstack/scripts/nerve_api.py loop --goal-file clickhouse-perf/prompts/run-b-goal.md \
     --verifier-file clickhouse-perf/runs/v4-verifier.md --budget 8 --max-iterations 3 \
     --cwd ~/nerve-v4-loops/run-b --verifier-engine codex-ultracode --out clickhouse-perf/runs/run-b --wait
   ```
   For Run C use `run-c-goal.md`. For 10b, run `scripts/negative_control.sh` first, then use `10b-goal.md` with `--budget 3 --max-iterations 1`.
8. **After every run:**
   - the control replay;
   - move the loop repo, `/tmp/impl-*` and the agents' lessons out of reach (FINDINGS §5).
9. **Figures.** `scripts/extract_runs.py` writes `runs/runs-summary.json` for the run list in the script.
   `uv run --with matplotlib python clickhouse-perf/scripts/plot_v4.py` redraws the recorded figures from `evidence/`
   into `runs/` (`--out-dir` to change); the PNGs in `evidence/` are not overwritten.

Wall-clock on the bench host: load 95 s plus about 5 min of merges; baseline about 10 min; inject about 10 min. Loops took 6 min (10b) to 85 min (Run B on a clean server).
