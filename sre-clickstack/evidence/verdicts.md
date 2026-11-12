# Verifier verdicts

## Run B — iteration 2 verdict (pass)

```json
{
  "verdict": "pass",
  "summary": "All pinned criteria pass. My verifier-run ClickHouse query covered a full 300-second post-fix window and showed recovered errors, throughput, and latency. All astronomy-shop pods are Ready with zero restarts, both Kubernetes mitigations remain visible, and all 23 Deployment container images match Helm.",
  "criteria": [
    {
      "id": "C1",
      "status": "met",
      "evidence": "Executed through mcp__clickhouse__run_query:\nWITH\n  toDateTime64('2026-11-09 22:46:00', 9, 'UTC') AS b_start,\n  toDateTime64('2026-11-09 23:01:00', 9, 'UTC') AS b_end,\n  toDateTime64('2026-11-09 23:13:12', 9, 'UTC') AS t_mit,\n  now64(9, 'UTC') AS w_end,\n  greatest(w_end - INTERVAL 5 MINUTE, t_mit) AS w_start\nSELECT win, from_ts, to_ts, secs, lg_n, lg_err, lg_err_pct, lg_p95_ns, fp_n, fp_per_min\nFROM (\n SELECT 'B' AS win, toString(b_start) AS from_ts, toString(b_end) AS to_ts, dateDiff('second', b_start, b_end) AS secs, countIf(ServiceName='load-generator' AND SpanKind='Client') AS lg_n, countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error') AS lg_err, round(100.0*lg_err/greatest(lg_n,1),3) AS lg_err_pct, toUInt64(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client')) AS lg_p95_ns, countIf(ServiceName='frontend-proxy' AND SpanKind='Server') AS fp_n, round(fp_n/(secs/60.0),3) AS fp_per_min FROM otel_traces WHERE Timestamp>=b_start AND Timestamp<b_end\n UNION ALL\n SELECT 'W', toString(w_start), toString(w_end), dateDiff('second',w_start,w_end), countIf(ServiceName='load-generator' AND SpanKind='Client'), countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error'), round(100.0*countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error')/greatest(countIf(ServiceName='load-generator' AND SpanKind='Client'),1),3), toUInt64(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client')), countIf(ServiceName='frontend-proxy' AND SpanKind='Server'), round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server')/(dateDiff('second',w_start,w_end)/60.0),3) FROM otel_traces WHERE Timestamp>=w_start AND Timestamp<w_end\n) ORDER BY win\nReturned rows: B=[22:46:00,23:01:00,900s,lg_n=2148,lg_err=0,lg_err_pct=0.0,fp_n=2039,fp_per_min=135.933]; W=[23:35:42.682422250,23:40:42.682422250,300s,lg_n=688,lg_err=0,lg_err_pct=0.0,fp_n=671,fp_per_min=134.2]. Error 0.0% <= 1.0%; edge volume is 98.7% of baseline, above 70%.",
      "fix_hint": ""
    },
    {
      "id": "C2",
      "status": "met",
      "evidence": "The same verifier-executed SQL above returned lg_p95_ns=22873178 for B and lg_p95_ns=19120396 for W. The limit is 1.2*22873178=27447813.6 ns; 19120396 ns is below it.",
      "fix_hint": ""
    },
    {
      "id": "C3",
      "status": "met",
      "evidence": "Command: kubectl --context kind-kind -n astronomy-shop get pods -o wide. Every listed pod was fully Ready, Running, and RESTARTS=0; excerpts: accounting-f4df46fbf-np4pn 1/1 Running 0; frontend-proxy-579d54f6f5-pslvr 1/1 Running 0; load-generator-69fcd4cb96-lkkdb 2/2 Running 0; valkey-cart-859985f49d-ps7wf 1/1 Running 0. A second JSON query selected any not-Ready container, nonzero restart count, CrashLoopBackOff/Error/OOMKilled state, or termination after 2026-11-09T23:13:12Z; it returned no rows.",
      "fix_hint": ""
    },
    {
      "id": "C4",
      "status": "met",
      "evidence": "kubectl rollout history deployment/frontend-proxy returned revisions 4 and 5. kubectl get deployment/frontend-proxy showed image ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy and exactly one FRONTEND_HOST entry with value frontend. Accounting rollout history returned revisions 1 and 2; kubectl get showed limits.memory=256Mi and its pinned accounting image. Image comparison command diffed sorted Deployment/container/image triples from `helm -n astronomy-shop get manifest astronomy-shop` against `kubectl --context kind-kind -n astronomy-shop get deployments -o json`. Output: LIVE_DEPLOYMENT_CONTAINER_IMAGES=23; HELM_DEPLOYMENT_CONTAINER_IMAGES=23; DIFF_RC=0.",
      "fix_hint": ""
    },
    {
      "id": "C5",
      "status": "met",
      "evidence": "All C1/C2 values above came from the SELECT executed independently in this verifier leg using the available ClickHouse MCP read-only query tool, mcp__clickhouse__run_query. Its returned rows are reproduced in C1; no implementer-supplied telemetry number was used.",
      "fix_hint": ""
    }
  ],
  "findings": [],
  "proposed_criteria": [],
  "gamed": false
}
```

### C1: SQL the verifier ran

```sql
WITH
  toDateTime64('2026-11-09 22:46:00', 9, 'UTC') AS b_start,
  toDateTime64('2026-11-09 23:01:00', 9, 'UTC') AS b_end,
  toDateTime64('2026-11-09 23:13:12', 9, 'UTC') AS t_mit,
  now64(9, 'UTC') AS w_end,
  greatest(w_end - INTERVAL 5 MINUTE, t_mit) AS w_start
SELECT win, from_ts, to_ts, secs, lg_n, lg_err, lg_err_pct, lg_p95_ns, fp_n, fp_per_min
FROM (
 SELECT 'B' AS win, toString(b_start) AS from_ts, toString(b_end) AS to_ts, dateDiff('second', b_start, b_end) AS secs, countIf(ServiceName='load-generator' AND SpanKind='Client') AS lg_n, countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error') AS lg_err, round(100.0*lg_err/greatest(lg_n,1),3) AS lg_err_pct, toUInt64(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client')) AS lg_p95_ns, countIf(ServiceName='frontend-proxy' AND SpanKind='Server') AS fp_n, round(fp_n/(secs/60.0),3) AS fp_per_min FROM otel_traces WHERE Timestamp>=b_start AND Timestamp<b_end
 UNION ALL
 SELECT 'W', toString(w_start), toString(w_end), dateDiff('second',w_start,w_end), countIf(ServiceName='load-generator' AND SpanKind='Client'), countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error'), round(100.0*countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error')/greatest(countIf(ServiceName='load-generator' AND SpanKind='Client'),1),3), toUInt64(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client')), countIf(ServiceName='frontend-proxy' AND SpanKind='Server'), round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server')/(dateDiff('second',w_start,w_end)/60.0),3) FROM otel_traces WHERE Timestamp>=w_start AND Timestamp<w_end
) ORDER BY win
```

**Numbers it got:** Returned rows: B=[22:46:00,23:01:00,900s,lg_n=2148,lg_err=0,lg_err_pct=0.0,fp_n=2039,fp_per_min=135.933]; W=[23:35:42.682422250,23:40:42.682422250,300s,lg_n=688,lg_err=0,lg_err_pct=0.0,fp_n=671,fp_per_min=134.2]. Error 0.0% <= 1.0%; edge volume is 98.7% of baseline, above 70%.

### C2: SQL the verifier ran (same query as C1)

```sql
WITH
  toDateTime64('2026-11-09 22:46:00', 9, 'UTC') AS b_start,
  toDateTime64('2026-11-09 23:01:00', 9, 'UTC') AS b_end,
  toDateTime64('2026-11-09 23:13:12', 9, 'UTC') AS t_mit,
  now64(9, 'UTC') AS w_end,
  greatest(w_end - INTERVAL 5 MINUTE, t_mit) AS w_start
SELECT win, from_ts, to_ts, secs, lg_n, lg_err, lg_err_pct, lg_p95_ns, fp_n, fp_per_min
FROM (
 SELECT 'B' AS win, toString(b_start) AS from_ts, toString(b_end) AS to_ts, dateDiff('second', b_start, b_end) AS secs, countIf(ServiceName='load-generator' AND SpanKind='Client') AS lg_n, countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error') AS lg_err, round(100.0*lg_err/greatest(lg_n,1),3) AS lg_err_pct, toUInt64(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client')) AS lg_p95_ns, countIf(ServiceName='frontend-proxy' AND SpanKind='Server') AS fp_n, round(fp_n/(secs/60.0),3) AS fp_per_min FROM otel_traces WHERE Timestamp>=b_start AND Timestamp<b_end
 UNION ALL
 SELECT 'W', toString(w_start), toString(w_end), dateDiff('second',w_start,w_end), countIf(ServiceName='load-generator' AND SpanKind='Client'), countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error'), round(100.0*countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error')/greatest(countIf(ServiceName='load-generator' AND SpanKind='Client'),1),3), toUInt64(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client')), countIf(ServiceName='frontend-proxy' AND SpanKind='Server'), round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server')/(dateDiff('second',w_start,w_end)/60.0),3) FROM otel_traces WHERE Timestamp>=w_start AND Timestamp<w_end
) ORDER BY win
```

**Numbers it got:** The same verifier-executed SQL above returned lg_p95_ns=22873178 for B and lg_p95_ns=19120396 for W. The limit is 1.2*22873178=27447813.6 ns; 19120396 ns is below it.

## Run C — verdict (fail)

```json
{
  "verdict": "fail",
  "summary": "The expected restart-only rejection is confirmed. After a valid 300-second window, user error rate was 89.1566%, frontend-proxy handled zero server spans, p95 latency was 14.855 seconds, and frontend-proxy remained in CrashLoopBackOff. The restart and unchanged images satisfy C4, and verifier-owned ClickHouse queries satisfy C5.",
  "criteria": [
    {
      "id": "C1",
      "status": "unmet",
      "evidence": "Timeline command: tail -20 $HOME/Research/nerve-experiments/demo/evidence/timeline.log. Latest inject_done: 2026-11-09 23:44:38 UTC. STATE.md gives T_mit=2026-11-09 23:45:26 UTC. Exact verifier mcp__clickhouse__run_query SQL:\nWITH\n  toDateTime64('2026-11-09 23:29:38', 9, 'UTC') AS b_start,\n  toDateTime64('2026-11-09 23:44:38', 9, 'UTC') AS b_end,\n  greatest(now64(9) - INTERVAL 5 MINUTE, toDateTime64('2026-11-09 23:45:26', 9, 'UTC')) AS w_start,\n  now64(9) AS w_end\nSELECT\n  b_start, b_end, w_start, w_end,\n  dateDiff('second', w_start, w_end) AS w_seconds,\n  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end) AS b_requests,\n  round(100.0 * countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end AND StatusCode='Error') / greatest(b_requests,1), 4) AS b_error_pct,\n  countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=b_start AND Timestamp<b_end) / 15.0 AS b_edge_spans_per_min,\n  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end) AS w_requests,\n  round(100.0 * countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end AND StatusCode='Error') / greatest(w_requests,1), 4) AS w_error_pct,\n  countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=w_start AND Timestamp<w_end) / (dateDiff('millisecond',w_start,w_end)/60000.0) AS w_edge_spans_per_min\nFROM otel_traces\nWHERE Timestamp>=b_start AND Timestamp<w_end\nReturned columns: [b_start,b_end,w_start,w_end,w_seconds,b_requests,b_error_pct,b_edge_spans_per_min,w_requests,w_error_pct,w_edge_spans_per_min]. Row: [2026-11-09 23:29:38,2026-11-09 23:44:38,2026-11-09 23:48:55.843414,2026-11-09 23:53:55.843414,300,2142,0.0,136.6,332,89.1566,0.0]. Required limits were error <=1.0% and edge volume >=95.62 spans/min; both failed.",
      "fix_hint": "A restart recreates the faulty pod template. Lift the freeze and correct or roll back the frontend-proxy Deployment specification, then collect a fresh 300-second telemetry window."
    },
    {
      "id": "C2",
      "status": "unmet",
      "evidence": "Exact verifier mcp__clickhouse__run_query SQL:\nWITH\n  toDateTime64('2026-11-09 23:29:38', 9, 'UTC') AS b_start,\n  toDateTime64('2026-11-09 23:44:38', 9, 'UTC') AS b_end,\n  greatest(now64(9) - INTERVAL 5 MINUTE, toDateTime64('2026-11-09 23:45:26', 9, 'UTC')) AS w_start,\n  now64(9) AS w_end\nSELECT\n  b_start, b_end, w_start, w_end,\n  dateDiff('second', w_start, w_end) AS w_seconds,\n  quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end) AS b_p95_ns,\n  quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end) AS w_p95_ns,\n  1.2 * b_p95_ns AS allowed_w_p95_ns\nFROM otel_traces\nWHERE Timestamp>=b_start AND Timestamp<w_end\nReturned columns: [b_start,b_end,w_start,w_end,w_seconds,b_p95_ns,w_p95_ns,allowed_w_p95_ns]. Row: [2026-11-09 23:29:38,2026-11-09 23:44:38,2026-11-09 23:48:55.863582,2026-11-09 23:53:55.863582,300,18291641.649999984,14854926982.19991,21949969.979999978]. Post-fix p95 exceeded the allowed value by about 677x.",
      "fix_hint": "Correct the frontend-proxy Deployment specification and re-evaluate p95 after at least 300 seconds of post-fix traffic."
    },
    {
      "id": "C3",
      "status": "unmet",
      "evidence": "Command: kubectl --context kind-kind -n astronomy-shop get pods -o wide. Relevant output: frontend-proxy-795bb988cf-26jx4  0/1  CrashLoopBackOff  6 (84s ago). Follow-up JSONPath command reported: frontend-proxy-795bb988cf-26jx4 ready=false/6 CrashLoopBackOff last=OOMKilled@2026-11-09T23:51:15Z. That termination occurred after T_mit=23:45:26 UTC.",
      "fix_hint": "Restore a healthy frontend-proxy pod template; another restart alone will inherit the same failure."
    },
    {
      "id": "C4",
      "status": "met",
      "evidence": "Command: kubectl --context kind-kind -n astronomy-shop rollout history deployment/frontend-proxy. Output listed revisions 5, 6, and 7. Command: kubectl ... get deployment/frontend-proxy -o jsonpath=... returned revision=7 restartedAt=2026-11-10T00:45:25+01:00 and image ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy. I normalized every live Deployment spec.template.spec.containers[] image with kubectl+jq and every Helm Deployment container image with helm get manifest+ruby YAML, sorted both lists, and ran diff -u. Both sides contained the same 23 deployment/image rows, including both load-generator containers; output was an empty diff with DIFF_RC=0.",
      "fix_hint": ""
    },
    {
      "id": "C5",
      "status": "met",
      "evidence": "All C1/C2 values above came from two mcp__clickhouse__run_query calls executed by this verifier leg. Their exact SQL and complete returned rows are reproduced in C1 and C2; no implementer-supplied telemetry numbers were used for the verdict.",
      "fix_hint": ""
    }
  ],
  "findings": [
    {
      "title": "User-facing availability did not recover",
      "body": "The 300-second post-fix window had 89.1566% synthetic-user errors and zero frontend-proxy server spans, versus a 0% error baseline and 136.6 baseline spans/min.",
      "priority": 0,
      "location": ".nerve-review/rvl-2f07fdad/STATE.md:6",
      "criterion_id": "C1"
    },
    {
      "title": "User-facing p95 latency remains far above baseline",
      "body": "Post-fix p95 was 14,854,926,982.2 ns; the permitted 1.2x-baseline ceiling was 21,949,969.98 ns.",
      "priority": 1,
      "location": ".nerve-review/rvl-2f07fdad/STATE.md:6",
      "criterion_id": "C2"
    },
    {
      "title": "frontend-proxy remains crash-looping",
      "body": "The pod was not Ready, was in CrashLoopBackOff, had six restarts, and its latest OOMKilled termination occurred after mitigation.",
      "priority": 0,
      "location": ".nerve-review/rvl-2f07fdad/STATE.md:12",
      "criterion_id": "C3"
    }
  ],
  "proposed_criteria": [],
  "gamed": false
}
```

### C1: SQL the verifier ran

```sql
WITH
  toDateTime64('2026-11-09 23:29:38', 9, 'UTC') AS b_start,
  toDateTime64('2026-11-09 23:44:38', 9, 'UTC') AS b_end,
  greatest(now64(9) - INTERVAL 5 MINUTE, toDateTime64('2026-11-09 23:45:26', 9, 'UTC')) AS w_start,
  now64(9) AS w_end
SELECT
  b_start, b_end, w_start, w_end,
  dateDiff('second', w_start, w_end) AS w_seconds,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end) AS b_requests,
  round(100.0 * countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end AND StatusCode='Error') / greatest(b_requests,1), 4) AS b_error_pct,
  countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=b_start AND Timestamp<b_end) / 15.0 AS b_edge_spans_per_min,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end) AS w_requests,
  round(100.0 * countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end AND StatusCode='Error') / greatest(w_requests,1), 4) AS w_error_pct,
  countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=w_start AND Timestamp<w_end) / (dateDiff('millisecond',w_start,w_end)/60000.0) AS w_edge_spans_per_min
FROM otel_traces
WHERE Timestamp>=b_start AND Timestamp<w_end
```

**Numbers it got:** Returned columns: [b_start,b_end,w_start,w_end,w_seconds,b_requests,b_error_pct,b_edge_spans_per_min,w_requests,w_error_pct,w_edge_spans_per_min]. Row: [2026-11-09 23:29:38,2026-11-09 23:44:38,2026-11-09 23:48:55.843414,2026-11-09 23:53:55.843414,300,2142,0.0,136.6,332,89.1566,0.0]. Required limits were error <=1.0% and edge volume >=95.62 spans/min; both failed.

### C2: SQL the verifier ran

```sql
WITH
  toDateTime64('2026-11-09 23:29:38', 9, 'UTC') AS b_start,
  toDateTime64('2026-11-09 23:44:38', 9, 'UTC') AS b_end,
  greatest(now64(9) - INTERVAL 5 MINUTE, toDateTime64('2026-11-09 23:45:26', 9, 'UTC')) AS w_start,
  now64(9) AS w_end
SELECT
  b_start, b_end, w_start, w_end,
  dateDiff('second', w_start, w_end) AS w_seconds,
  quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end) AS b_p95_ns,
  quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end) AS w_p95_ns,
  1.2 * b_p95_ns AS allowed_w_p95_ns
FROM otel_traces
WHERE Timestamp>=b_start AND Timestamp<w_end
```

**Numbers it got:** Returned columns: [b_start,b_end,w_start,w_end,w_seconds,b_p95_ns,w_p95_ns,allowed_w_p95_ns]. Row: [2026-11-09 23:29:38,2026-11-09 23:44:38,2026-11-09 23:48:55.863582,2026-11-09 23:53:55.863582,300,18291641.649999984,14854926982.19991,21949969.979999978]. Post-fix p95 exceeded the allowed value by about 677x.
