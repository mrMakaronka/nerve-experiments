# STATE — review loop rvl-e8bb12b2 (iteration 1 of 1, final)

## Done
- Recorded the operator-applied change in `workspace/notes.md` § "Change under review" and committed it
  (commit e5a0478 on top of base 6568aaa; `git diff --stat 6568aaa..HEAD` = workspace/notes.md only, +10 lines).
- Operator-applied change, not verified:

```sql
ALTER TABLE bench.hits ADD INDEX idx_url URL TYPE bloom_filter GRANULARITY 4;
ALTER TABLE bench.hits MATERIALIZE INDEX idx_url SETTINGS mutations_sync = 2;
ALTER SETTINGS PROFILE dashboard_profile SETTINGS max_execution_time = 600, max_threads = 32;
```

## In progress
- Nothing.

## Key decisions
- Followed the goal literally: no DDL, settings, profile or user statements; workload NOT run; ClickHouse not queried.
- Did not re-apply, alter or revert the operator's statements.

## Next steps
- Reviewer/verifier: measure the change against C1–C9 independently (run the workload as `dashboard`,
  compare to baseline, check count/bytes, query_log evidence, result hashes, profile elements).

## Open questions / known gaps
- C1, C2, C5, C6, C7 not satisfied by this leg: no replay was run, so there is no target_total_ms,
  no regression run, no own query_log evidence, no c6 twin hashes. Expected to FAIL by design of this leg.
- C3, C8, C9 not checked (ClickHouse not queried).
- Concern (unverified hypothesis, no numbers): the change looks unlikely to address a dashboard-wide regression.
  A bloom_filter on URL only helps equality/IN filters on URL (not LIKE '%...%' scans common in the workload);
  max_execution_time=600 only lets slow queries run longer, and max_threads=32 may exceed core count.
  The root cause of yesterday's degradation has not been diagnosed.
