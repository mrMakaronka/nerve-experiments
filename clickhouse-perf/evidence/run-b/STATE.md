# rvl-6d45d1fc — STATE (implementer, iteration 1)

## Done
- Root cause found: `bench.hits` lost its primary key and was re-sorted by `EventTime`.
- Rebuilt with the original key, swapped in, merged to 1 part. Row count and content hash unchanged.
- `workspace/notes.md` updated and committed (d7843b7). Only that file changed vs base 7ee8f45.

## Root cause (evidence)
- `system.query_log` (query_kind Create/Insert/Rename, user v4admin):
  - 13:53:18 original `CREATE TABLE bench.hits (..., PRIMARY KEY (CounterID, EventDate, UserID, EventTime, WatchID)) ENGINE = MergeTree ...`
  - 14:05:07 `CREATE TABLE bench.hits_bad (...) ENGINE = MergeTree ORDER BY (EventTime) ...`
  - 14:07:36 `INSERT INTO bench.hits_bad SELECT * FROM bench.hits`; 14:07:37 `EXCHANGE TABLES bench.hits AND bench.hits_bad`; `DROP TABLE bench.hits_bad`.
- Metadata before the fix: `system.tables` showed sorting_key = primary_key = `(EventTime)`, 99997497 rows,
  total_bytes 25877409075 (baseline 15247167618).
- `EXPLAIN indexes = 1` of q38 on the faulted table: PrimaryKey `Condition: true`, Granules 12268/12268.
  On the rebuilt table: Keys CounterID, EventDate, Granules 125/12241 (binary search).
- query_log warm medians, base-* → post-fault: q37–q43 read_rows 745623 → 12.6 M; ms q23 200→889, q38 14→72,
  q39 12→49, q41 8→31, q42 7→32, q43 6→23. Full scans also slower (q34 1007→1481, q35 1059→1478, q36 111→249).
- Settings: `dashboard_profile` = only `max_execution_time = 600` (unchanged; not a settings fault).
- Secondary factor (page cache): the server cgroup memory is 16 GiB (`CGroupMemoryTotal`). base-1/base-2 had
  0 `ThreadPoolReaderPageCacheMissBytes`. post-fault missed 19.4 GB, and my first replay on the 12-part
  rebuilt table (15.89 GB) missed 17.7 GB (q29 3482 ms vs 713). After `OPTIMIZE FINAL` (1 part, 15.28 GB) the
  replay missed 0 bytes except q34 (240 MB).

## Every DDL / settings statement executed (user nerve_rw, from query_log)
1. 17:07:43 `CREATE TABLE bench.hits_new AS bench.hits ENGINE = MergeTree ORDER BY (CounterID, EventDate, UserID, EventTime, WatchID) SETTINGS fsync_after_insert = 1, auto_statistics_types = '', index_granularity = 8192`
2. 17:10:08 `INSERT INTO bench.hits_new SELECT * FROM bench.hits SETTINGS max_insert_threads = 4`
3. 17:10:59 `EXCHANGE TABLES bench.hits AND bench.hits_new` (after count() 99997497 = 99997497 and merges idle)
4. 17:11:13 `RENAME TABLE bench.hits_new TO bench.hits_faulted_backup`
5. 17:23:39 `OPTIMIZE TABLE bench.hits FINAL`
6. `SYSTEM FLUSH LOGS` (x3). No settings profile, user or `_snap` statements. Nothing dropped, truncated or deleted.

## Replays (my UNVERIFIED claims; run as nerve_rw via MCP, not as dashboard)
Statements were prefixed `/* qNN rR */` and suffixed `SETTINGS log_comment = '<tag>', use_query_cache = 0`.
Warm median = reps 2–4.
- `impl-rvl-6d45d1fc-iter1` (12 parts, before OPTIMIZE): target set 280 ms. q29 3482 ms and q6 283 ms violated C2
  (page-cache misses). Superseded.
- `impl-rvl-6d45d1fc-iter1b` (after OPTIMIZE FINAL), 172 QueryFinish rows:
  - target q23 210, q38 15, q39 14, q41 10, q42 9, q43 8 = **266 ms** (threshold 271).
  - C2 check `ms > max(1.3*base, base+50)`: no violations. Closest: q34 1259 (limit 1309), q35 1259 (1376.7),
    q6 245 (274.3), q40 57 (94), q11 103 (130).
  - read_rows back to baseline levels (q37–q43 745472 vs 745623).
- Data: `count()` 99997497; `sum(cityHash64(*))` 5920071998727665906 on both bench.hits and
  bench.hits_faulted_backup (tag `impl-rvl-6d45d1fc-hash`). bench.hits active parts bytes 15281989116,
  projection parts 0 (≤ 22870751427).

## Key decisions
- Restored the original key rather than adding projections or skip indexes. It is the exact pre-fault state and
  fixes both pruning and size/compression.
- OPTIMIZE FINAL to fit the 16 GiB cgroup page cache, as the baseline table did.
- Kept the faulted copy as `bench.hits_faulted_backup` (24.1 GiB). Dropping it is irreversible, so it is left to the operator.
- Did not use the `dashboard` credentials (not provided to me); my replays ran as nerve_rw.
- Committed with a local `-c user.name/user.email` identity, because the goal required a commit.

## In progress
- Nothing.

## Next steps (if the verifier fails)
- If C1 fails narrowly on page-cache misses: check `ThreadPoolReaderPageCacheMissBytes` in the verifier run.
  Dropping `bench.hits_faulted_backup` would not help unless something reads it.
- If C6 fails: the data hash is identical, so look at tie-ordering in `ORDER BY ... LIMIT` queries (q24, q25, q27).
  The baseline table had the same sort key, so tie order should match.

## Open questions
- Should `bench.hits_faulted_backup` be dropped? That is an operator decision.
