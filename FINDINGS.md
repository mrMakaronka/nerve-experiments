# Cross-case findings

This page holds the synthesis only. Details, timings and caveats are in [sre-clickstack/FINDINGS.md](sre-clickstack/FINDINGS.md) (SRE), [agent-quality-langfuse/FINDINGS.md](agent-quality-langfuse/FINDINGS.md) (AQ) and [clickhouse-perf/FINDINGS.md](clickhouse-perf/FINDINGS.md) (DB).

## Transfer

- **Between faults, with zero edits.** For SRE fault 2 the verifier criteria, both Goals, both skills and TASK.md were reused byte-for-byte. B2 passed in 1 iteration and C2 was rejected ([run2/FINDINGS-run2.md](sre-clickstack/evidence/run2/FINDINGS-run2.md)).
- **Between signals, the adapter changed and the loop did not.** From ClickStack SQL to Langfuse scores, these carried over:
  - the loop shape;
  - the evidence rule (the verifier runs its own query or replay, then quotes the run id and numbers);
  - the anti-gaming flag (`gamed=false` in all 4 AQ verdicts);
  - the scope criterion.

  What had to be written new: the criteria text, one 6-tool MCP adapter and 2 skills ([AQ FINDINGS](agent-quality-langfuse/FINDINGS.md)).
- **What needed edits on the first signal.** SRE needed 6 pieces of workspace/config scaffolding, none of them in Nerve core ([SRE FINDINGS, TL;DR](sre-clickstack/FINDINGS.md)):
  - explicit SLIs;
  - windows anchored on timeline events;
  - a schema skill;
  - a sandbox network override;
  - an explicit approval override for the local MCP server (Codex does not auto-approve operator-added servers);
  - a wait rule.

  AQ reused the approval override and added a tool timeout.
- **To a third signal, the same shape again.** DB performance from ClickHouse's own `system.query_log` reused the loop, the evidence rule and the scope criterion. New pieces: criteria text with a replay the verifier runs itself as the workload identity, two stock `mcp-clickhouse` instances with different ClickHouse users, and one tool-level skill ([DB FINDINGS](clickhouse-perf/FINDINGS.md)).

## Rejections

Most negative runs produced a change that a shallow check would have accepted: pods Running again, an appended prompt, a plausible index plus a thread setting. DB Run C made no persistent change and reported that the goal could not be met under its constraint. In every case the verifier rejected the run on numbers it fetched itself. For SRE and AQ an independent oracle (SREGym's mitigation oracle, the hidden AQ oracle split) agreed. The DB case has no independent oracle: its cross-check is a hidden control workload of 10 queries plus result hashes.
- SRE Run C (restarts only): pods were Running again, yet errors were 89 % and p95 14.9 s. Verdict `fail`, oracle `false` ([run-c/verdict.json](sre-clickstack/evidence/run-c/verdict.json)).
- SRE C2: verdict `fail`, with 8 % errors in the verifier's window; oracle `failure` ([run2/c2/verdict-iter1.json](sre-clickstack/evidence/run2/c2/verdict-iter1.json)).
- SRE repeats: all 3 C runs were rejected, and the oracle said `failure` each time ([repeats/summary.md](sre-clickstack/evidence/repeats/summary.md)).
- AQ Run C (prompt-only append): replay 38 %, control 19/20; hidden oracle 38 % ([run-c/verdict-iter1.json](agent-quality-langfuse/evidence/run-c/verdict-iter1.json), [oracle-scores.json](agent-quality-langfuse/evidence/oracle-scores.json)).
- DB Run C (settings and skip indexes only): target 572 / 578 ms against 271, 13 C2 violations ([run-c/verdict-iter2.json](clickhouse-perf/evidence/run-c/verdict-iter2.json)). The implementer stopped with "the contract can't be met under the change constraint" instead of shipping a half-fix.
- DB 10b (scripted bloom_filter + `max_threads = 32`): C1 576 ms, 14 C2 violations. The verifier credited that the change persists (C7) and failed it on performance ([verdict](clickhouse-perf/evidence/negative-control/verifier/verdict-iter1.json)).
- DB Run B v1 iteration 2 (uncompressed cache in the profile): C1 met at 145 ms, rejected on 19 C2 regressions; the hidden control set confirmed it ([run-b-v1/verdict-iter2.json](clickhouse-perf/evidence/run-b-v1/verdict-iter2.json)).

These rejections matter more than the passes. A pass shows that the loop can end; a rejection shows that the verifier is not simply agreeing with the implementer.

## Side effects caught

- **OOM neighbour.** `accounting` was OOMKilled every ~16 min at its 120 Mi limit, a fault that predated the experiment. The "no restarts after T_mit" criterion forced the implementer to find it and fix it ([run-b/STATE.final.md](sre-clickstack/evidence/run-b/STATE.final.md)).
- **Frontend in backoff.** After the B2 Service patch, frontend's gRPC channel stayed in backoff and users still got errors. The telemetry window caught this; SREGym's TCP-probe oracle would not have ([run2/FINDINGS-run2.md](sre-clickstack/evidence/run2/FINDINGS-run2.md)).
- **Control-question regression.** The implementer's extra prompt rule flipped control item q837, and AQ iterations 1–2 were rejected on C2 ([run-b/verdict-iter1.json](agent-quality-langfuse/evidence/run-b/verdict-iter1.json)).
- **Cache hack.** In DB Run B v1 the implementer met the target with a 6 GB uncompressed cache in the workload profile. It pushed the table out of the page cache, and 19 other queries regressed past their C2 limits.

## Noise

- **Host memory.** Another app held ~12 GB, which put SRE Run B's p95 at 33–45 ms against a 27 ms limit on a correct fix ([SRE FINDINGS](sre-clickstack/FINDINGS.md)).
- **Jaeger.** In rep2-B, SREGym's in-memory Jaeger thrashed and p95 sat at 1.41–1.55× baseline against a 1.2× limit. The correct fix was rejected for 3 iterations (false rejection) ([repeats/summary.md](sre-clickstack/evidence/repeats/summary.md)).
- **Host sleep.** During C2 the host slept for ~80 min, and nothing in the loop detected it ([run2/FINDINGS-run2.md](sre-clickstack/evidence/run2/FINDINGS-run2.md)).
- **Baseline spread.** Three identical AQ baselines scored 83 / 83 / 87 %, a 3.3 pp spread on 60 items ([scores_table.md](agent-quality-langfuse/evidence/scores_table.md)).
- **Too little noise.** On a quiet dedicated host the DB baseline spread was 7 ms on a 246 ms target (2.8 %). A correct schema fix was rejected by 3 % because the rebuilt table is systematically ~5 % slower on one query. The operator added a floor after Run B v1 (C1 ≤ max(mean + spread, 1.10 × mean)); both result sets are kept.
- **State carried between runs.** A DB reset restored data, profiles and grants but not server memory. A 7.35 GiB cache from an earlier run then made the next implementer "fix" a false second cause and slowed the first Run C 5×. Since then, a server restart plus a reference replay (`envcheck`) runs before every loop ([DB FINDINGS §4](clickhouse-perf/FINDINGS.md)).

Resulting requirement: thresholds have to come from measured noise, with a floor for the case where the noise is tiny (AQ C1 = baseline mean − max(1 pp, spread); DB C1 = max(mean + spread, 1.10 × mean)). Every verification window also needs a validity check that is separate from the pass criteria: traffic present, an unaffected control path not degraded, and (DB) the reset state replaying like its reference.

## Replay vs traffic verification

| | Traffic (SRE) | Replay (AQ) |
|---|---|---|
| Time per iteration | ≥ 15 min clean baseline, then ≥ 300 s window after mitigation. Loops took 11 min (B2) to 37 min (Run B) | the verifier's own 60-item replay. Run C took 7 min for its single iteration; Run B took 21 min for 3 iterations |
| Determinism | no: live load, host and cluster noise | partial: same inputs, LLM spread of 3.3 pp |
| Requires | a live system with load, a baseline window and timeline events | a dataset with expected outputs, an offline-runnable system, and a hidden split, because the dataset exposes expected SQL |

The DB case is a replay too: a fixed 43-query workload, about 2 min per ×4 replay, deterministic results (43/43 hashes stable) and timings with 1.1 % spread on a dedicated host.

## Limitations

- SRE: one app and 2 faults. AQ: one agent, one database and one fault. DB: one table and one fault.
- n per configuration: SRE B 5 and C 5; AQ B 1 and C 1; DB B 1 and C 1 on a clean server (plus 3 earlier attempts kept as evidence).
- SRE and AQ ran on one laptop; the DB server ran on a dedicated bench host.
- Implementer Claude Opus 5.5, verifier Codex CLI; versions in [PINS.md](PINS.md).
- No implementer tampered with the evaluation itself (criteria, replay scripts, verifier data). The one metric-chasing change — the DB cache setting — was made openly and rejected on C2. The independent-verification mechanism encountered configuration gaps, but was not stress-tested against a deliberately adversarial implementer.
- **Isolation is the operator's job.** Nerve does not restrict the implementer's filesystem. In the DB case one implementer read an earlier loop's `.nerve-review/STATE.md` and `/tmp` scratch, and all of them read the verifier prompt in the demo repo. Isolation came from ClickHouse grants and row policies, moving earlier runs out of reach, a pre-run leak check and a transcript audit ([DB FINDINGS §5](clickhouse-perf/FINDINGS.md)).
