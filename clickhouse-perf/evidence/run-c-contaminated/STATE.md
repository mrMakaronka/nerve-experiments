# STATE — rvl-b6b4f1ab (implementer iteration 1, 2026-11-11 ~16:20–16:50 UTC)

## Done
### Root cause (evidence from system.query_log / system.parts / EXPLAIN, queried as nerve_rw)
- DDL history (`system.query_log`, query_kind Create/Insert/Rename): 13:53:18 `CREATE TABLE bench.hits (... PRIMARY KEY
  (CounterID, EventDate, UserID, EventTime, WatchID))`. At 14:05:07 `CREATE TABLE bench.hits_bad ... ORDER BY (EventTime)`.
  At 14:07:36 `INSERT INTO bench.hits_bad SELECT * FROM bench.hits`, then 14:07:37 `EXCHANGE TABLES bench.hits AND
  bench.hits_bad`. Current `SHOW CREATE TABLE bench.hits` → `ORDER BY (EventTime)`, 1 active part, 25877409075 bytes.
- Warm medians of base-1..3 vs post-fault (r2–r4). q37–43 read_rows are 745,623 at baseline and 12,623,872 post-fault:
  q38 13→72 ms, q39 11→49, q41 8→31, q42 7→32, q43 6→23, q23 201→889 (base read 22.8M rows, post 39.3M).
  Cold r1 post-fault reads 99,997,497 rows (q37 263 ms).
- `EXPLAIN indexes=1` q38: `PrimaryKey Condition: true, Granules: 12268/12268`.
- Granule analysis: `SELECT ... intDiv(_part_offset,8192) ... WHERE CounterID=62` → 1541 granules contain
  CounterID 62. Every one has ≥100 matching rows, 1521 have ≥400, quantiles(0.1,0.5,0.9) = 433/479/527. The
  24 h EventTime window 2013-07-14 20:00–07-15 19:59 is exactly those 1541 granules. So no granule-level skip
  index can read fewer than 12.6 M rows for q37–43. The query condition cache already does that for warm runs.
- Second factor: memory pressure. `system.metrics` MemoryTracking 7.63 GiB at idle; max_server_memory_usage
  15461882265; `max_threads_min_free_memory_per_thread` = 1 GiB caps threads at about 6 (`peak_threads_usage` 6 in my runs).

### Every DDL / settings statement executed (user nerve_rw)
1. `ALTER TABLE bench.hits ADD INDEX idx_counterid CounterID TYPE bloom_filter(0.01) GRANULARITY 1`
2. `ALTER TABLE bench.hits MATERIALIZE INDEX idx_counterid SETTINGS mutations_sync = 2` (index 4,139,774 bytes)
3. `ALTER TABLE bench.hits DROP INDEX idx_counterid SETTINGS mutations_sync = 2` (reverted: it made q37–43 slower)
4. `SYSTEM FLUSH LOGS` (several times)
- Per-query settings (no persistent change): `max_threads_min_free_memory_per_thread=268435456`, `max_bytes_ratio_before_external_group_by=0`,
  `max_bytes_before_external_group_by=7516192768` (probe p1 only; q34 OOM at 14.4 GiB with it).
- **No settings-profile change was made.** `dashboard_profile` = `max_execution_time = 600` only (verified in
  system.settings_profile_elements at the end).

### My replays (UNVERIFIED CLAIMS: nerve_rw via HTTP, script /tmp/impl-rvl-b6b4f1ab/replay.py, 4 reps, r1 discarded, use_query_cache=0)
- `impl-rvl-b6b4f1ab-p1` / `-p1b` (subset, threads setting per query): q23 330, q38 82/69, q39 54, q41 34, q42 35, q43 22 ms.
  Target ≈ 557 ms vs C1 271. q16 218 vs base 122.
- `impl-rvl-b6b4f1ab-r1` (full 43×4, `max_threads_min_free_memory_per_thread=268435456` per query): threads up to 22–34.
  Spills and overcommit: q19 10407 ms (base 878), q29 6977 (714), q33 9709 (801), q34 9290 (988), q35 9570 (1061).
  13 C2 violations. Target 335+72+51+34+37+26 = 555 ms. Setting rejected.
- `impl-rvl-b6b4f1ab-p2` (q37–43, after bloom index on CounterID): read_rows 13,540,332 (false positives), warm q37 155,
  q38 171, q39 111, q40 243, q41 73, q42 75, q43 51 ms, about 2× worse than post-fault. Index dropped.
- **No replay of the final state shows the targets met. The final state = the post-fault state.**

### Workspace
- `workspace/notes.md` updated and committed (832b364). regression.sql untouched (sha256 a7d66733…c2a219).

## In progress
- Nothing. Final DB state: count 99997497, bytes 25877409075, no skip index or projection, profile unchanged.

## Key decisions
- I did not violate the constraint (no sort-key or PK change, no rebuild or EXCHANGE, no projection), even though
  restoring `ORDER BY (CounterID, EventDate, UserID, EventTime, WatchID)` is the fix that works (loop rvl-b7ac3e2e
  did it, with q37–43 back to 91 granules).
- I reverted every experiment that made things worse rather than leave half-measures.

## Next steps
- Expect C1, C2 and C3 to FAIL against the current state. C3 fails even with no change: bytes 25877409075 > cap 22870751427.
  C8/C9: no DDL or setting was persisted.
- Under this constraint I see no path to C1–C3. It needs a human decision:
  (a) lift the constraint and allow the rebuild with the original key; or
  (b) free server memory (`SYSTEM DROP UNCOMPRESSED CACHE` or server config), which is outside nerve_rw scope;
  and still won't fix q38–43 or q23.
- Untested ideas, low expectation: minmax/set index on EventDate (no gain expected, since all matches are in a
  contiguous window); `use_uncompressed_cache=1` + `merge_tree_max_rows_to_use_cache≥13M` (one probe: warm q37 79 ms vs
  66 post-fault, no gain, and it adds memory pressure).

## Open questions
- Is the C1/C2/C3 contract achievable under the run-c constraint at all? The granule evidence says no for q38–43.
- Who holds the ~7.6 GiB of idle memory (the uncompressed cache was filled by a hidden run, per loop rvl-b7ac3e2e)?

---
# STATE: implementer iteration 2 (2026-11-11 ~16:45–17:05 UTC)

## Done
- Found what holds the idle memory: `system.metrics` UncompressedCacheBytes = 7,888,256,147 of MemoryTracking
  8,220,864,286 (OSMemoryTotal 30.64 GiB; the server limit shows as RSS max 14.40 GiB in the Code 241 error).
- Verifier run `ver-rvl-b6b4f1ab-iter1` vs `post-fault`: q19 11177 vs 950 ms, q33 11612 vs 887, q34 9447 vs 1481.
  The verifier run had 18–93 ExternalAggregationWritePart, about 12–14 threads and ~3.5 GiB memory. Cause: the spill
  starts at `max_bytes_ratio_before_external_group_by = 0.5` of the memory the cache leaves free.
- q23 per-rep evidence: base 2823 marks, 22,852,263 rows, ~200 ms. Post-fault 4813 marks, 39,296,196 rows. r4 (no OS
  reads) 354 ms is the best case; r2/r3 1366/889 ms included 743 MB and 485 MB of OS reads.
- Probe (UNVERIFIED claim) `impl-rvl-b6b4f1ab-i2s1`, nerve_rw, q19+q34 ×4, per-query
  `max_bytes_ratio_before_external_group_by=0, max_bytes_ratio_before_external_sort=0`: q34 r3 failed with Code 241
  memory limit exceeded (would use 9.53 GiB, RSS 14.40 GiB). Not applied to any profile.
- notes.md iteration-2 section committed: 9304df7.

## Statements executed this iteration
- Only SELECTs on system tables, plus the probe queries above (with per-query settings). No DDL. No profile change.
  No SYSTEM commands.

## End state (checked)
- count 99997497; bytes 25877409075; 0 skip indices; 0 projections; dashboard_profile = max_execution_time=600;
  0 pending mutations. `git diff --stat 80eded6..HEAD` = workspace/notes.md only; the worktree is clean.

## Key decisions
- Fail closed. C1 has a lower bound above its threshold (q23 alone ≥ ~354 ms > 271 ms). C3 needs a part rewrite,
  which the constraint forbids. C2's heavy queries are bound by the 7.9 GB uncompressed cache, a server-wide resource
  outside scope. Disabling the spill causes OOM errors. Persisting a half-measure would make nothing pass and could
  add errors, so I persisted nothing.

## Next steps / Open questions (human decision)
- (a) Lift the run-c constraint so the original `ORDER BY (CounterID, EventDate, UserID, EventTime, WatchID)` can be
  restored. This fixes C1 and C3, and the q37–43 read amplification.
- (b) Authorize `SYSTEM DROP UNCOMPRESSED CACHE` (server-wide). Find out who fills the cache (a hidden run with
  use_uncompressed_cache=1?) so it doesn't recur. This addresses the C2 heavy-query spills.
- Without (a), C1 and C3 cannot be reached under this contract.
