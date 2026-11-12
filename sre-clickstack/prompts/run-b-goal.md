astronomy-shop (namespace `astronomy-shop`, kind cluster, kube context `kind-kind`) has an
active incident. Diagnose it from ClickStack telemetry (`clickhouse` MCP tools; schema in
`skill_get clickstack-schema`, playbook in `skill_get incident-triage`), apply a mitigation
via kubectl (no code changes, no image changes), and leave the cluster healthy.

Fault-injection time: the most recent `inject_done` event in
`$HOME/Research/nerve-experiments/demo/evidence/timeline.log` (UTC).

Document in `.nerve-review/<loop>/STATE.md`:
- root cause, with the SQL query and numbers that show it;
- the exact kubectl change (command + before/after of the relevant spec fields);
- `MITIGATION_TS_UTC: YYYY-MM-DD HH:MM:SS` — taken with `date -u` right after
  `kubectl rollout status` reports success;
- the baseline window you used: the 15 minutes before inject_done.

Verification needs ≥5 minutes of post-fix traffic in ClickStack. After the mitigation
is rolled out, do not end your leg until at least 300 seconds have passed since
MITIGATION_TS_UTC (poll with short `sleep`s if needed), then run the baseline-vs-window
query yourself and record the result in STATE.md (as your own unverified claim).
If the post-fix numbers are not back to baseline, keep investigating instead of stopping.
