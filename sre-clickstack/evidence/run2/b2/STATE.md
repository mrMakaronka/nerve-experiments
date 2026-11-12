# STATE — review loop rvl-9c2b4035 (impl leg 1)

T_inj (latest `inject_done`, timeline.log): `2026-11-10 00:57:54` UTC — problem `internal_traffic_policy_local_astronomy_shop`
Baseline window B: `[2026-11-10 00:42:54, 2026-11-10 00:57:54)` UTC (15 min before inject_done; after deploy_done 00:39:42)

MITIGATION_TS_UTC: 2026-11-10 01:02:19

(The authoritative value is in the line above: `date -u` right after `kubectl rollout status deploy/frontend` succeeded following step 2.
The step-1 Service patch completed at 01:01:14 UTC.)

## Done

### Root cause
The Service `astronomy-shop/recommendation` had `spec.internalTrafficPolicy: Local`. The Helm
release sets no policy for it (the API default is `Cluster`; the only `Local` in the Helm manifest is
the otel-collector agent DaemonSet service). The injector (field manager `OpenAPI-Generator`)
also pinned the pods with nodeSelectors: `recommendation` on `kind-worker` (its only endpoint is
10.244.162.147) and `frontend` on `kind-worker2`. With `Local`, kube-proxy on kind-worker2
has no node-local endpoint for the ClusterIP, so it drops frontend's gRPC calls to recommendation.
Result: gRPC UNAVAILABLE (14) on the client side, HTTP 500 on `/api/recommendations`, and
504 timeouts (~15 s) at frontend-proxy and the load-generator.
`frontend` and `frontend-proxy` are the symptom services; the recommendation Service spec is the cause.

Evidence query 1 (server spans per service, B vs post-inject, run 2026-11-10 ~01:00:40 UTC, post window 164 s):
```sql
WITH toDateTime64('2026-11-10 00:42:54', 9, 'UTC') AS b_start, toDateTime64('2026-11-10 00:57:54', 9, 'UTC') AS b_end
SELECT ServiceName,
  countIf(Timestamp >= b_start AND Timestamp < b_end) AS base_n,
  round(100*countIf(Timestamp >= b_start AND Timestamp < b_end AND StatusCode='Error')/greatest(base_n,1),2) AS base_err_pct,
  countIf(Timestamp >= b_end) AS cur_n,
  round(100*countIf(Timestamp >= b_end AND StatusCode='Error')/greatest(cur_n,1),2) AS cur_err_pct,
  round(quantileIf(0.95)(Duration, Timestamp >= b_start AND Timestamp < b_end)/1e6,1) AS base_p95_ms,
  round(quantileIf(0.95)(Duration, Timestamp >= b_end)/1e6,1) AS cur_p95_ms,
  dateDiff('second', b_end, now()) AS cur_window_s
FROM otel_traces WHERE Timestamp >= b_start AND SpanKind='Server'
GROUP BY ServiceName ORDER BY cur_err_pct DESC, base_n DESC
```
Key rows (service, base_n, base_err%, cur_n, cur_err%, base_p95_ms, cur_p95_ms):
- frontend-proxy: 1961, 0.15, 302, **10.26**, 19.1, **14991.5**
- frontend: 3744, 0.08, 567, **7.23**, 18.5, **14999.6**
- recommendation: 139, 0.0, **0**, 0.0, 3.4, NaN  ← no server spans at all after injection
- all other services: 0 % errors after injection

Evidence query 2 (errors by span after injection):
```sql
SELECT ServiceName, SpanName, SpanKind, StatusMessage, SpanAttributes['rpc.grpc.status_code'] AS grpc, SpanAttributes['http.status_code'] AS http, count() AS n
FROM otel_traces WHERE Timestamp >= toDateTime64('2026-11-10 00:57:54', 9, 'UTC') AND StatusCode='Error'
GROUP BY ALL ORDER BY n DESC LIMIT 20
```
Rows: frontend `GET /api/recommendations` Server http 500 ×47; frontend
`oteldemo.RecommendationService/ListRecommendations` Client grpc **14** ×32; load-generator GET
Client 504 ×17 and 500 ×15; frontend-proxy GET Server 504 ×17 and 500 ×15.

Evidence query 3 (recommendation spans): in B there were 139 `ListRecommendations` Server spans
(p95 3.4 ms) and 137 OK Client spans. After injection: 0 Server spans and 32 Client spans,
all `Error` (p95 107854 ms).

Load-generator Client SLI before the fix: B = 2054 Unset + 3 Error; post-inject = 291 Unset + 31 Error (~9.6 %).

### Mitigation (kubectl, no image or code change)
```
kubectl --context kind-kind -n astronomy-shop patch svc recommendation --type=merge \
  -p '{"spec":{"internalTrafficPolicy":"Cluster"}}'
```
- Before: `spec.internalTrafficPolicy: Local`
- After:  `spec.internalTrafficPolicy: Cluster` (same as the Helm manifest, which leaves it at the default)
- Step 1: patched at 01:01:14 UTC. `kubectl rollout status` reported success for recommendation and frontend.
- Step 1 alone did NOT restore traffic. Query (spans of `ListRecommendations` from 01:01:00 on) still showed 11
  frontend Client spans with grpc 14 between 01:01:07 and 01:01:59, each ~0 ms, and no recommendation Server spans.
  Frontend log: `14 UNAVAILABLE: No connection established. Last error: connect ETIMEDOUT 10.96.4.126:8080 (2026-11-10T00:59:52.504Z)`
  The grpc-js channel in the frontend pod stayed in TRANSIENT_FAILURE backoff from the incident.
  Its last connect attempt predates the fix, so it kept failing fast without retrying.
- Step 2 (reset the stale channel; same image and spec):
  `kubectl --context kind-kind -n astronomy-shop rollout restart deploy/frontend`
  → `rollout status` succeeded → `date -u` = **01:02:19** = MITIGATION_TS_UTC.
  The new pod is `frontend-56d9f7684d-nqc8p` (kind-worker2). The rollout added template annotation `kubectl.kubernetes.io/restartedAt`.
- Recovery check (30 s buckets of `ListRecommendations` from 01:02:00): frontend Client Unset ×6 and recommendation Server Unset ×5, with no errors.
- Visible in the cluster: the managedFields of `svc/recommendation` show `kubectl-patch Update 2026-11-10T01:01:14Z`.
  `kubectl get svc recommendation -o jsonpath='{.spec.internalTrafficPolicy}'` → `Cluster`.

## In progress
- Post-fix verification (see "Verification" below, filled after ≥300 s).

## Key decisions
- I left the injected nodeSelectors (`recommendation` on kind-worker, `frontend` on kind-worker2) in place.
  With `Cluster` policy, cross-node placement is harmless. Removing them would roll two pods and add restarts
  for no telemetry benefit. They remain a drift from Helm (pod spec only; the images are unchanged).
- I did not touch the otel-collector service's `internalTrafficPolicy: Local`. It is the Helm default for the agent DaemonSet.

## Next steps
- The verifier re-runs C1–C4 itself.

## Open questions
- Should the injected nodeSelectors also be reverted to match Helm? Not needed for health.
