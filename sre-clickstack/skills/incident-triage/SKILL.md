---
name: Incident Triage (astronomy-shop)
description: >
  Playbook for diagnosing and mitigating an incident in astronomy-shop on the kind
  cluster using ClickStack traces plus kubectl, and for verifying a mitigation by
  telemetry. Use when asked about an incident, outage, errors, latency, "what is
  broken", "diagnose", "mitigate", or "verify the fix".
version: 1.0.0
context: domain
---

# Incident triage — telemetry first

Load `skill_get clickstack-schema` first for table/column details and the saved queries.

## 1. Which services are unhealthy right now? (≤ 2 queries)
Compare the last 10 minutes against the 15 minutes before that, server spans only:

```sql
SELECT ServiceName,
       countIf(Timestamp >= now() - INTERVAL 10 MINUTE)                                   AS cur_n,
       round(100 * countIf(Timestamp >= now() - INTERVAL 10 MINUTE AND StatusCode = 'Error')
             / greatest(cur_n, 1), 2)                                                     AS cur_err_pct,
       countIf(Timestamp < now() - INTERVAL 10 MINUTE)                                    AS base_n,
       round(100 * countIf(Timestamp < now() - INTERVAL 10 MINUTE AND StatusCode = 'Error')
             / greatest(base_n, 1), 2)                                                    AS base_err_pct,
       round(quantileIf(0.95)(Duration, Timestamp >= now() - INTERVAL 10 MINUTE) / 1e6, 1) AS cur_p95_ms,
       round(quantileIf(0.95)(Duration, Timestamp <  now() - INTERVAL 10 MINUTE) / 1e6, 1) AS base_p95_ms
FROM otel_traces
WHERE Timestamp >= now() - INTERVAL 25 MINUTE
  AND SpanKind = 'Server'
GROUP BY ServiceName
ORDER BY cur_err_pct DESC, cur_n DESC
```

Then check the user-facing SLI — `load-generator` `Client` spans (error rate, p95,
and the top `StatusMessage` values) for the same two windows. A service that crashed
or became unreachable emits no spans of its own; its failure shows up here.

Also look for services whose **traffic collapsed** (cur_n ≪ base_n) — an edge
failure starves everything downstream, so the broken component is often the one
*upstream* of the quiet services, not the quiet services themselves.

If `sre-clickstack/evidence/timeline.log` has an `inject_done` event, prefer that timestamp
as the baseline boundary over "10 minutes ago".

## 2. Drill into the failing spans
For the worst service, group errors by span name, status message and the most
telling attributes:

```sql
SELECT SpanName, StatusMessage,
       SpanAttributes['http.status_code'] AS http_status,
       SpanAttributes['upstream_cluster']          AS upstream_cluster,
       SpanAttributes['response_flags']            AS envoy_flags,
       count() AS n
FROM otel_traces
WHERE ServiceName = '<svc>' AND Timestamp >= now() - INTERVAL 10 MINUTE
  AND StatusCode = 'Error'
GROUP BY ALL ORDER BY n DESC LIMIT 20
```

Look at a few full attribute maps (`SpanAttributes`, `ResourceAttributes`, `Events`)
for raw evidence (peer address, upstream host, error message). Check `otel_logs`
for the same service and window.

## 3. Correlate with Kubernetes
```bash
kubectl -n astronomy-shop get pods -o wide
kubectl -n astronomy-shop get events --sort-by=.lastTimestamp | tail -30
kubectl -n astronomy-shop get deploy <svc> -o yaml   # env, image, args, probes
kubectl -n astronomy-shop rollout history deploy/<svc>
```
Pods that are Running/Ready do **not** clear a component: config errors (env vars,
service spec, secrets) keep pods healthy while traffic fails. Read the spec.
Watch for duplicated env var names — Kubernetes keeps the **last** definition.

## 4. State the root cause
One paragraph: component, mechanism, and the exact evidence query + numbers that
show it. Distinguish symptom services from the cause.

## 5. Mitigate (only if the request allows)
Smallest kubectl change that removes the cause. Print the change before applying.
Record the UTC timestamp right after the rollout completes (`date -u`) — the
verification window starts there.

## 6. Verify by telemetry
Wait until ≥ 5 minutes of traffic exist after the mitigation timestamp, then
re-run the step-1 query with the window `[mitigation_ts + 0, now)` vs the
pre-incident baseline window. "Resolved" = error rate ≤ baseline + 1pp and
p95 ≤ 1.2 × baseline for the affected service, and the traffic volume is back.
