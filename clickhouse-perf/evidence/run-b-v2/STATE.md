# STATE — rvl-b7ac3e2e (after implementer iteration 1)

## Root cause (two layers, both evidenced in this session as nerve_rw)

### 1. Sort key changed (the incident, 14:05–14:07 UTC)
`system.query_log` DDL history (`SELECT event_time, user, query_kind, query FROM system.query_log WHERE type='QueryFinish' AND query_kind NOT IN ('Select','System','Insert') AND event_date >= today()-7 ORDER BY event_time`):
- 13:53:18 v4admin `CREATE TABLE bench.hits (...) PRIMARY KEY (CounterID, EventDate, UserID, EventTime, WatchID) ENGINE = MergeTree`
- 14:05:07 v4admin `CREATE TABLE bench.hits_bad (...) ENGINE = MergeTree ORDER BY (EventTime)`; 14:07:36 `INSERT INTO bench.hits_bad SELECT * FROM bench.hits` (99997497 rows); 14:07:37 `EXCHANGE TABLES bench.hits AND bench.hits_bad`
- 14:18:56 table reset from `_snap.hits_faulted` (still ORDER BY (EventTime)).
Before fix: `SHOW CREATE TABLE bench.hits` → `ORDER BY (EventTime)`, no skip indexes/projections; 1 part; sum(bytes_on_disk) 25877409075 (above the C3 cap 22870751427).
`EXPLAIN indexes = 1` q37 before: `PrimaryKey Condition: true, Granules: 12268/12268`. After: `Keys: CounterID, EventDate`, `Granules: 91/12226`.
Warm medians base-1..3 → post-fault (queries ≥1.5×): q23 200→889 (4.44×, read_rows 22.85M→39.30M), q37 24→67, q38 14→72 (5.14×), q39 12→49, q40 44→113,
q41 8→31, q42 7→32, q43 6→23 (read_rows 0.75M→12.6M for q37–q43), q21 126→210, q4/q16/q17/q28/q36 1.6–2.2× (same read_rows).

### 2. Memory pressure caps parallelism and forces GROUP BY spills (appeared 14:45–15:00 UTC, after the baselines)
- `system.metric_log`: UncompressedCacheBytes 0 B through 14:40, 5.42 GiB at 14:45, 6.44 GiB from 15:00 until now; MemoryTracking ≈ 6.7 GiB at idle.
  No query visible to nerve_rw used the uncompressed cache (filler unknown, possibly a hidden `ctl-%` control run).
- 26.8 setting `max_threads_min_free_memory_per_thread` = 1073741824 (default): free = max_server_memory_usage 15461882265 − ~6.7 GiB ≈ 7.6 GiB → max_threads capped at 7.
  Proof: `EXPLAIN PIPELINE SELECT sum(number) FROM numbers_mt(1e9) SETTINGS max_threads=16|8` → `NumbersRange × 7`; with max_threads=6 → ×6. Same 7 streams on bench.hits.
  query_log: base-1 peak_threads_usage 20 (median), my first replay impl-rvl-b7ac3e2e-r1 13; same CPU time (q29 9.7 s vs 9.1 s), wall 1.7–2×; OS idle 75 % during the replay; no CPU steal/PSI.
- `max_bytes_ratio_before_external_group_by` = 0.5: r1 q19 ExternalAggregationWritePart 60, 10212 ms vs base 895; q34 4789 vs 1007.
- Applies server-wide, so `dashboard` (fresh sessions, only `max_execution_time = 600` in its profile) is affected as well.

## Done — every DDL / settings statement I executed (user nerve_rw)
1. `CREATE TABLE bench.hits_new AS bench.hits ENGINE = MergeTree ORDER BY (CounterID, EventDate, UserID, EventTime, WatchID) SETTINGS fsync_after_insert = 1, auto_statistics_types = '', index_granularity = 8192`
2. `INSERT INTO bench.hits_new SELECT * FROM bench.hits SETTINGS max_insert_threads = 4`
3. `OPTIMIZE TABLE bench.hits_new FINAL` (twice; the first returned while a background merge was running) → 1 part
4. Check: count 99997497 in both; `sum(cityHash64(WatchID, UserID, EventTime, URL))` = 15642593287742583682 in both
5. `EXCHANGE TABLES bench.hits AND bench.hits_new`
6. `RENAME TABLE bench.hits_new TO bench.hits_faulted_backup` (old ORDER BY (EventTime) copy, kept; not dropped)
7. `ALTER SETTINGS PROFILE dashboard_profile SETTINGS max_execution_time = 600, max_threads_min_free_memory_per_thread = 268435456, max_bytes_ratio_before_external_group_by = 0.8` (superseded by 8)
8. `ALTER SETTINGS PROFILE dashboard_profile SETTINGS max_execution_time = 600, max_threads_min_free_memory_per_thread = 268435456, max_bytes_ratio_before_external_group_by = 0, max_bytes_before_external_group_by = 7516192768`
Also: session-level probes (`SETTINGS ...` on single queries, log_comment impl-rvl-b7ac3e2e-probe / -probe2), SYSTEM FLUSH LOGS. Nothing touched `_snap`.
`workspace/notes.md` updated and committed (7f7cf57).

## My replays (UNVERIFIED CLAIMS: implementer's own runs as nerve_rw, not dashboard)
Script `/tmp/impl-rvl-b7ac3e2e/replay.py`: 43 statements × 4, fresh HTTP request each, query_id `<tag>-qNN-rR`, use_query_cache=0; warm = r2–r4 medians; baseline = median of base-1..3 per-query warm medians.
- `impl-rvl-b7ac3e2e-r1` (after rebuild, no profile settings): target (q23,38,39,41,42,43) 416 ms; total 28114 ms vs 8036; 22 C2 violations (7-thread cap + spills).
- `impl-rvl-b7ac3e2e-r2` (profile v7 settings passed per query): target 238 ms; total 8192; C2 violation q34 1580 vs 1007 (spills on r1/r4).
- `impl-rvl-b7ac3e2e-r3` (final profile settings passed per query, mimicking dashboard_profile): **target 239 ms (≤ 271.0)**; total 7458 ms vs base 8036;
  **C2 violations: none**; read_rows >2× base: none; spills 0; exceptions 0; 172 QueryFinish rows.
  Per query base→r3: q23 201→189, q38 14→15, q39 11→14, q41 8→8, q42 7→7, q43 6→6, q19 895→864, q34 1007→930, q35 1059→871, q29 713→660, q33 803→757.
- C6 (my run of the verifier's read-only replay.py with nerve_rw creds, run id `impl-rvl-b7ac3e2e-c6`): checked 43, excluded [], mismatches [], missing [], errors [].
- C3: count 99997497; parts bytes 15284054273 + projection_parts 0 ≤ 22870751427.

## In progress
Nothing.

## Key decisions
- Schema fix = restore the original sort key by rebuild + EXCHANGE (no skip index or projection needed: q37–q43 back to 91 granules).
- Settings fix in `dashboard_profile` (assigned to `dashboard` per its CREATE USER ... SETTINGS PROFILE `dashboard_profile`), not in sessions.
  Chose to keep both guards rather than disable them: 256 MiB/thread still lowers threads under real pressure; a fixed 7 GiB per-query spill
  threshold replaces the ratio that is tripped by cache-held memory. Peak query memory in the workload is 6.28 GiB; 6.7 + 6.3 < 14.4 GiB server limit.
- Did not drop `bench.hits_faulted_backup` (irreversible; needs operator approval). It does not count towards C3 (bench.hits only).
- Did not try to clear the uncompressed cache (`SYSTEM DROP UNCOMPRESSED CACHE` is outside scope/privileges).

## Next steps (for the verifier / next leg)
- Verifier: run replay as dashboard; expect profile settings in the `Settings` column / log_settings of its rows.
- If C1/C2 fail as dashboard: check `peak_threads_usage` and `ProfileEvents['ExternalAggregationWritePart']` in that run, and `system.metrics` MemoryTracking / UncompressedCacheBytes.

## Open questions
- Who filled the 6.44 GiB uncompressed cache at 14:45–15:00 UTC? Invisible to nerve_rw. If it is cleared, the profile settings are harmless (no effect without pressure).
- Should `bench.hits_faulted_backup` (25.9 GB) be dropped? Operator decision.
- I could not run `SHOW CREATE USER dashboard` (nerve_rw lacks SHOW USERS); the profile assignment comes from query_log (14:18:55 `CREATE USER OR REPLACE dashboard ... SETTINGS PROFILE dashboard_profile`).
