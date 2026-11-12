# STATE — rvl-ec38122d

# Iteration 2 (run wfr-da29174a, 2026-11-11 ~19:45 CET) — implementer claim, unverified

## Done
- I re-checked the iteration-1 root cause on my own (queries below) and confirmed it.
- Appended an iteration-2 section to workspace/notes.md and committed it. That is the only repository file changed.
- I executed **no DDL and no settings statements** (only SELECT / EXPLAIN).

## Evidence gathered this leg (queries run as nerve_rw, numbers returned)
- `SELECT count(), sum(bytes_on_disk), groupArray(name), any(part_type), any(marks) FROM system.parts WHERE database='bench' AND table='hits' AND active`
  → 1, 25877409075, ['all_1_1_3'], Wide, 12269.
- `system.tables.engine_full` → `MergeTree ORDER BY (EventTime) SETTINGS fsync_after_insert = 1, auto_statistics_types = '', index_granularity = 8192`.
- `system.columns` → compression_codec empty (default LZ4) for every column. URL 4.53 GB at a 2.17× ratio, Title 4.13 GB at 2.49×, Referer 3.69 GB at 2.02×.
- Combined check → row_count 99997497, part_bytes 25877409075, skip_idx 0, projs 0,
  profile settings `readonly:readonly=1`, `dashboard_profile:max_execution_time=600`, merges 0.
- `EXPLAIN indexes=1` for q41 → PrimaryKey `Condition: true`, Granules 12268/12268, plus a Prewhere filter on CounterID/RefererHash/....
- Granule census (log_comment `impl-rvl-ec38122d-it2-census`): granules with CounterID=62 = 1541, with CounterID=62 and July = 1541,
  total 12207, rows with CounterID=62 = 738172.

## Key decisions
- **I applied no change.** C3 needs active bytes ≤ 22,870,751,427. Today the table is 25,877,409,075 bytes. The goal allows only profile
  settings, which leave the bytes on disk as they are, and data-skipping indexes, which only add bytes. So no permitted change can satisfy C3.
  Codec or table-setting changes with OPTIMIZE FINAL are a rewrite of the table and are outside "settings or settings profiles". They would also not recover about 3 GB under LZ4.
- C1 and C2 can't be reached either. Warm runs already use the query condition cache, which narrows reads to the same 1541 granules that
  any skip index would select. The full-scan regressions (q16, q34, q35, q36, q17, q29) are scans with no selective filter, so no index helps.
  The slowdown is bound by bytes read, and the bytes come from the data layout.
- A placebo index or setting just to show "a persistent change" for C7 would make C3 worse and would not move C1 or C2. I rejected it.

## In progress
- Nothing.

## Next steps (operator decision required; a third iteration under the same constraint will reach the same result)
- (a) Lift the constraint and restore `ORDER BY (CounterID, EventDate, UserID, EventTime, WatchID)`: CREATE a new table, then INSERT…SELECT,
  check the row count = 99,997,497, then EXCHANGE TABLES. Or
- (b) Close rvl-ec38122d as infeasible under its constraint.

## Open questions
- Is C3 meant to apply under a no-rebuild constraint? It fails before any change can be made.

## Replay
- I did not run a replay. No state changed, so it would only re-measure the post-fault state the verifier already measured (target 572 ms).

---

# Iteration 1 (run wfr-14b6178b, 2026-11-11 ~19:35–19:55 CET)

## Verdict of this leg (implementer claim, unverified)
**Hard stop: the contract can't be met under the change constraint.** I applied no DDL and no settings change.
Two criteria can't be reached with only "settings and data-skipping indexes added":
- **C3 fails before any change.** bench.hits is 25,877,409,075 bytes on disk. The C3 limit is 22,870,751,427.
  Adding indexes can only add bytes. Settings changes leave the bytes as they are.
- **C1 (target ≤ 271 ms) can't be reached.** q23 alone runs at about 355 ms warm, and that floor comes from the
  data layout (see evidence). The only fix is to restore the sorting key, which this constraint forbids.

## Done
- Root cause found, with the evidence below.
- I ran experiments with settings and checked granule distribution (SELECTs only, log_comment `impl-rvl-ec38122d-exp*`).
- workspace/notes.md updated and committed (that is the only file changed in the repository).

## Root cause (evidence)
1. DDL history (`system.query_log`, query_kind in Create/Insert/Rename):
   - 13:53:18 v4admin `CREATE TABLE bench.hits (... PRIMARY KEY (CounterID, EventDate, UserID, EventTime, WatchID))`
   - 14:05:07 `CREATE TABLE bench.hits_bad (...) ENGINE = MergeTree ORDER BY (EventTime)`
   - 14:07:36 `INSERT INTO bench.hits_bad SELECT * FROM bench.hits`
   - 14:07:37 `EXCHANGE TABLES bench.hits AND bench.hits_bad`, then `DROP TABLE bench.hits_bad`
   - The current `SHOW CREATE TABLE bench.hits` shows `ORDER BY (EventTime)`. system.tables gives sorting_key = primary_key = `(EventTime)`.
   - (14:17–14:18: a `nerve_rw` dry run `nc-dry` added a bloom_filter on URL and max_threads=32 to the profile.
     The harness then restored the table and profile from `_snap.hits_faulted`. In that dry run the target queries
     were unchanged: q38 72→73 ms, q41 31→31 ms, q42 32→32 ms.)
2. Settings did not change. In query_log, `Settings` for the dashboard rows of base-1 and post-fault is the same:
   `{database, log_comment, max_execution_time=600}`. dashboard_profile = `max_execution_time=600` only.
3. Target queries, warm median ms and read_rows (base mean → post-fault):
   q23 201→889 (rows 22.8M→39.3M; post-fault reps 1366/889/354, nc-dry 358/356/358)
   q38 13→72, q39 11.3→49, q41 8→31, q42 7→32, q43 6→23 (rows 745,623→12,623,872; SelectedMarks 95→1541)
   Full-scan queries also got slower (q16 122→240, q34 988→1481, q35 1061→1478, q36 118→249) because rows are no
   longer clustered by CounterID/UserID.
4. `EXPLAIN indexes=1` for q38: PrimaryKey `Condition: true`, Granules 12268/12268. The EventTime key can't
   be used for CounterID or EventDate filters.
5. Why skip indexes can't help (granule census, SQL with `uniqExactIf(intDiv(_part_offset,8192), cond)`):
   granules with CounterID=62 = 1541, with CounterID=62 AND date 14–15 = 1541, with date 14–15 = 1541,
   with URLHash=2868770270353813622 = 1541, with RefererHash=3594120000172545465 = 1800,
   with Title LIKE '%Google%' = 10668 of 12269, with URL LIKE '%google%' = 6699. Counter 62's 738,172 rows are spread
   over every granule of 14–15 July. A minmax, set or bloom index on these columns therefore selects the same
   1541 granules that the query condition cache already selects in warm runs (post-fault warm read_rows = 12,623,872 = 1541 granules).
   Skip indexes would only speed up the cold first run, and the replay discards that run.
6. The speed is bound by throughput: q23 reads 6.57 GiB in about 355 ms post-fault and 4.14 GiB in 201 ms at baseline, the
   same GB/s. max_threads is already 16 on 15 cores. Experiments as nerve_rw: q38 default 76 ms, small concurrent-read
   settings 75 ms, max_threads=32 gave no improvement.
7. Table size: 1 part, 25,877,409,075 bytes (baseline 15,247,167,618). Unsorted strings compress worse
   (URL 2.17×, Title 2.49×; WatchID about 1.0×).

## DDL / settings statements executed
- **None.** In this leg I ran only SELECT, EXPLAIN, SHOW and `SYSTEM FLUSH LOGS`.

## Replay (my unverified claim)
- I did not run a full replay, because I made no change. The verifier's replay would measure the post-fault state.
  Experiment tags: `impl-rvl-ec38122d-exp1` (q38 76 ms), `-exp2-mt32`, `-exp3-mergetree-small-reads` (q38 75 ms), `-exp4-q23` (611 ms, condition cache miss).

## Key decisions
- I applied no speculative indexes or settings. They can't move C1, they would make C3 worse, and they add risk for no gain
  (the operator's dry run `nc-dry` already showed this).
- I did not read or use the verifier's credentials or scripts in ~/nerve-v4-verifier.

## Next steps (need a human decision)
- Choose one:
  (a) Lift the constraint for this incident and allow restoring `ORDER BY (CounterID, EventDate, UserID, EventTime, WatchID)`.
      Build a new table, check row count = 99,997,497, then `EXCHANGE TABLES` (the Run B approach).
  (b) Accept that C1 and C3 can't be met under the constraint and close the loop as infeasible.
- Under the current constraint, a later iteration can't pass. Re-running will reach the same result.

## Open questions
- Is the C3 byte limit meant to apply to the post-fault table under the "no rebuild" constraint? It already fails at the start.
