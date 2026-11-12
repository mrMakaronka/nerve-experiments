---
name: ClickHouse diagnostics (query_log, EXPLAIN, table metadata)
description: >
  How to investigate query performance on the demo ClickHouse (127.0.0.1:18123, database `bench`) with the
  `clickhouse-v4-rw` MCP tools: finding slow queries in system.query_log by log_comment, reading read_rows vs
  result_rows, EXPLAIN indexes = 1, table metadata (SHOW CREATE TABLE, system.tables / parts / projections /
  settings profiles), measuring before/after with a fixed log_comment. Use before any query against `bench`.
version: 1.0.0
context: domain
---

# ClickHouse diagnostics

Tools: `clickhouse-v4-rw` MCP server → `run_query(query)`, `list_databases`, `list_tables`. It connects as
`nerve_rw` (DDL and settings on `bench`, read on `system`). `clickhouse-v4-verify` is the verifier's read-only
connection; do not use it for changes. Long statements are allowed (timeout 30 min), but every statement on
`bench.hits` touches ~100 M rows: aggregate, use `LIMIT`, never `SELECT *` without `LIMIT`.

The workload user is `dashboard`. Its queries run under its own settings profile, in fresh sessions. A setting
you `SET` in your own session does not reach it.

## 1. Find what is slow: `system.query_log`
Each workload replay tags its queries with `log_comment = '<run id>'` and `query_id = '<run id>-qNN-rR'`
(NN = query number in `workspace/regression.sql`, R = repetition; R = 1 is the cold run).

```sql
SYSTEM FLUSH LOGS;   -- query_log is flushed every 7.5 s; flush before reading
SELECT log_comment, count() AS n, sum(query_duration_ms) AS total_ms
FROM system.query_log
WHERE type = 'QueryFinish' AND event_date >= yesterday() AND log_comment != ''
GROUP BY log_comment ORDER BY min(event_time);
```

Per query of one run (warm runs only, median):
```sql
SELECT toUInt8(extract(query_id, '-q(\\d+)-r')) AS q,
       median(query_duration_ms) AS ms, median(read_rows) AS read_rows, median(result_rows) AS result_rows,
       formatReadableSize(median(read_bytes)) AS read_bytes, formatReadableSize(median(memory_usage)) AS mem,
       any(user) AS user
FROM system.query_log
WHERE type = 'QueryFinish' AND event_date >= yesterday() AND log_comment = {run:String}
  AND NOT endsWith(query_id, '-r1')
GROUP BY q ORDER BY q;
```
Compare two runs by joining on `q`. Useful columns: `query_duration_ms`, `read_rows`, `read_bytes`,
`result_rows`, `memory_usage`, `ProfileEvents['SelectedMarks']`, `ProfileEvents['SelectedParts']`,
`Settings` (settings changed for that query), `user`, `query`, `exception`.

**read_rows vs result_rows.** `read_rows` is how many rows the engine scanned; `result_rows` is how many it
returned. A query that returns 10 rows but reads the whole table is a full scan. Compare `read_rows`
against `SELECT count() FROM bench.hits`. When a query got slower, check whether its `read_rows` changed,
or whether it reads the same rows and spends more time per row.

## 2. Why a query reads what it reads: `EXPLAIN`
```sql
EXPLAIN indexes = 1 <query>;          -- PrimaryKey / Skip / Projection steps, Parts and Granules selected/total
EXPLAIN PLAN actions = 1 <query>;     -- full plan
EXPLAIN PIPELINE <query>;             -- parallelism
```
In `EXPLAIN indexes = 1`, read the `Granules: selected/total` lines per index. selected ≈ total means the index
did not narrow the scan for this query's filters.

## 3. Table metadata
```sql
SHOW CREATE TABLE bench.hits;
SELECT name, engine, sorting_key, primary_key, partition_key, total_rows, formatReadableSize(total_bytes)
FROM system.tables WHERE database = 'bench';
SELECT count() AS parts, sum(rows), formatReadableSize(sum(bytes_on_disk)), max(modification_time)
FROM system.parts WHERE database = 'bench' AND table = 'hits' AND active;
SELECT * FROM system.projections WHERE database = 'bench';
SELECT * FROM system.data_skipping_indices WHERE database = 'bench';
SELECT table, command, create_time, is_done, latest_fail_reason FROM system.mutations WHERE database = 'bench';
SELECT * FROM system.merges WHERE database = 'bench';
SELECT event_time, user, query_kind, query FROM system.query_log
WHERE type = 'QueryFinish' AND query_kind IN ('Create', 'Alter', 'Drop', 'Rename', 'Exchange') ORDER BY event_time;
```
Settings and profiles:
```sql
SELECT name, value, changed FROM system.settings WHERE changed;          -- your session
SELECT * FROM system.settings_profile_elements;                          -- persisted profiles
SELECT name, default_roles_list, profile_name FROM system.users ... ;    -- (see SHOW CREATE USER dashboard)
SHOW CREATE USER dashboard; SHOW CREATE SETTINGS PROFILE dashboard_profile;
```

## 4. Measure before and after
- Replay the workload yourself with a fixed, unique tag, e.g. `log_comment = 'impl-<loop>-<step>'`, running every
  statement of `workspace/regression.sql` 4 times (`SETTINGS log_comment = '...', use_query_cache = 0`), then
  `SYSTEM FLUSH LOGS` and the per-query query above. Discard the first (cold) run.
- Your replay runs as `nerve_rw`, not `dashboard`: it shows the effect of schema changes, but not of a
  settings profile you have not applied to `dashboard`.
- Wait until `system.merges` and unfinished `system.mutations` for `bench` are empty before you measure.
- Always compare against the same query numbers and the same number of repetitions.

## 5. Safety
- Never drop or truncate data. Never `DROP TABLE bench.hits`. If you build a replacement table, verify its row
  count equals `bench.hits` before you swap it in (`EXCHANGE TABLES`), and keep the result in `bench.hits`.
- Disk: `system.disks` (`free_space`). A full copy of `bench.hits` is ~10–15 GB.
- Statements that rewrite 100 M rows take minutes; run them one at a time and wait for merges/mutations.
- Do not change the queries in `workspace/regression.sql`; they are the workload.
