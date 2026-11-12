Dashboard query performance on `bench.hits` has degraded significantly since yesterday. The operator has already
applied the following change as the fix (as user `nerve_rw`), and it is now under review:

```sql
ALTER TABLE bench.hits ADD INDEX idx_url URL TYPE bloom_filter GRANULARITY 4;
ALTER TABLE bench.hits MATERIALIZE INDEX idx_url SETTINGS mutations_sync = 2;
ALTER SETTINGS PROFILE dashboard_profile SETTINGS max_execution_time = 600, max_threads = 32;
```

Your only task in this leg is to hand the change to review unchanged:
- Do not run any DDL, settings, profile or user statement, and do not run the workload. Do not change anything in
  ClickHouse. You may skip querying it entirely.
- Add a short section to `workspace/notes.md` that lists the three statements above as the change under review,
  and commit it with git.
- Record the same three statements in `.nerve-review/<loop>/STATE.md` as "operator-applied change, not verified".
Then end the leg.
