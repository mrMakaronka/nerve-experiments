# STATE — review loop rvl-1fbeb4e0 (rep3-B), implementer iteration 1

MITIGATION_TS_UTC: 2026-11-10 05:33:49

- T_inj (latest `inject_done` in timeline.log): **2026-11-10 05:33:10 UTC**
- Baseline window B: **[2026-11-10 05:18:10, 2026-11-10 05:33:10) UTC** (the 15 min before inject_done)
- Mitigation: JSON patch on `deploy/frontend-proxy` removing the duplicate `FRONTEND_HOST=localhost` env entry
- Post-fix check: see "Post-fix verification" below (my own, unverified claim)

## Done

### Root cause
`deploy/frontend-proxy` (the Envoy edge) had `FRONTEND_HOST` defined twice in its container env:
index 10 `FRONTEND_HOST=frontend` and a later index 23 `FRONTEND_HOST=localhost`. Kubernetes keeps the
**last** definition, so Envoy's `frontend` upstream pointed at `localhost:8080`, which is Envoy's own
listener. The edge proxied to itself, the pod was OOMKilled and went into CrashLoopBackOff
(`frontend-proxy-87c864665-ckvcs`: `OOMKilled`, then `CrashLoopBackOff`, with 2 restarts in 33 s).
All user traffic enters through frontend-proxy, so synthetic users got connection errors and frontend-proxy
stopped emitting server spans. The quiet downstream services (frontend, cart, ...) were only a symptom.
The rollout happened at T_inj: frontend-proxy went from revision 11 (RS 5766549668, good) to revision 12 (RS 87c864665, shadowed env).

Evidence, query 1: user-facing SLI, baseline vs. incident (incident = [T_inj, T_mit)):
```sql
SELECT if(Timestamp < toDateTime64('2026-11-10 05:33:10',9,'UTC'),'B_baseline','I_incident') AS win,
  count() AS n, countIf(StatusCode='Error') AS errors, round(100*errors/greatest(n,1),2) AS err_pct,
  round(quantile(0.95)(Duration)/1e6,1) AS p95_ms,
  topKIf(3)(substring(StatusMessage,1,80), StatusCode='Error') AS top_errors
FROM otel_traces
WHERE ServiceName='load-generator' AND SpanKind='Client'
  AND Timestamp >= toDateTime64('2026-11-10 05:18:10',9,'UTC') AND Timestamp < toDateTime64('2026-11-10 05:33:49',9,'UTC')
GROUP BY win ORDER BY win
```
| win | n | errors | err_pct | p95_ms | top_errors |
|---|---|---|---|---|---|
| B_baseline | 2148 | 0 | 0.00 | 34.1 | [] |
| I_incident | 78 | 61 | 78.21 | 6045.8 | ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retri…; ConnectionError: ('Connection aborted.', RemoteDisconnected(…)) |

Evidence, query 2: edge server-span volume:
```sql
SELECT if(Timestamp < toDateTime64('2026-11-10 05:33:10',9,'UTC'),'B_baseline','I_incident') AS win,
  count() AS server_spans, round(count()/dateDiff('second', min(Timestamp), max(Timestamp))*60,1) AS approx_per_min, max(Timestamp) AS last_span
FROM otel_traces
WHERE ServiceName='frontend-proxy' AND SpanKind='Server'
  AND Timestamp >= toDateTime64('2026-11-10 05:18:10',9,'UTC') AND Timestamp < toDateTime64('2026-11-10 05:33:49',9,'UTC')
GROUP BY win ORDER BY win
```
Returned only `B_baseline, 2025, 135.2, 2026-11-10 05:33:09.447657`. No `I_incident` row: frontend-proxy emitted
**zero** server spans after T_inj. Its last span was 1 s before inject_done.

### Mitigation (kubectl only, image unchanged)
Command (05:33:48 UTC); the `test` op makes it fail closed if index 23 is not the shadowing entry:
```bash
kubectl --context kind-kind -n astronomy-shop patch deploy frontend-proxy --type=json -p='[
  {"op":"test","path":"/spec/template/spec/containers/0/env/23","value":{"name":"FRONTEND_HOST","value":"localhost"}},
  {"op":"remove","path":"/spec/template/spec/containers/0/env/23"}]'
kubectl --context kind-kind -n astronomy-shop rollout status deploy/frontend-proxy --timeout=180s
date -u   # -> 2026-11-10 05:33:49
```
Before (`.spec.template.spec.containers[0].env`, FRONTEND entries, 24 entries in total): `[10] FRONTEND_HOST=frontend`, `[11] FRONTEND_PORT=8080`, `[23] FRONTEND_HOST=localhost`; revision 12.
After (23 entries): `[10] FRONTEND_HOST=frontend`, `[11] FRONTEND_PORT=8080`; revision 13 (reuses pod-template RS 5766549668).
Image before and after: `ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy`.
New pod `frontend-proxy-5766549668-rzdkr` is 1/1 Running with 0 restarts.

## Post-fix verification (implementer's own claim, unverified; verifier must re-run)
Run at 2026-11-10 05:39:12 UTC. W = [max(now-5min, T_mit), now) = [05:34:12.83, 05:39:12.83), 300 s. B = [05:18:10, 05:33:10).
```sql
WITH toDateTime64('2026-11-10 05:18:10',9,'UTC') AS b_start, toDateTime64('2026-11-10 05:33:10',9,'UTC') AS b_end,
     greatest(now64(9,'UTC') - INTERVAL 5 MINUTE, toDateTime64('2026-11-10 05:33:49',9,'UTC')) AS w_start, now64(9,'UTC') AS w_end
SELECT
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end) AS b_lg_n,
  round(100*countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end AND StatusCode='Error')/greatest(b_lg_n,1),2) AS b_lg_err_pct,
  round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end)/1e6,2) AS b_lg_p95_ms,
  round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=b_start AND Timestamp<b_end)/(dateDiff('second',b_start,b_end)/60),1) AS b_fp_per_min,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end) AS w_lg_n,
  round(100*countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end AND StatusCode='Error')/greatest(w_lg_n,1),2) AS w_lg_err_pct,
  round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end)/1e6,2) AS w_lg_p95_ms,
  round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=w_start AND Timestamp<w_end)/(dateDiff('second',w_start,w_end)/60),1) AS w_fp_per_min,
  w_start, w_end, dateDiff('second', w_start, w_end) AS w_span_s
FROM otel_traces
WHERE Timestamp >= b_start AND ServiceName IN ('load-generator','frontend-proxy')
```
Returned: b_lg_n=2148, b_lg_err_pct=0.00, b_lg_p95_ms=34.07, b_fp_per_min=135.0, w_lg_n=666, w_lg_err_pct=0.00,
w_lg_p95_ms=20.98, w_fp_per_min=128.8, w_span_s=300.
- C1: error rate 0.00% ≤ 0.00% + 1 pp, PASS. Edge volume 128.8/min ≥ 0.7 × 135.0 = 94.5/min (95.4%), PASS.
- C2: p95 20.98 ms ≤ 1.2 × 34.07 = 40.88 ms, PASS.
- C3 (05:39:18 UTC): all 26 pods are Running and Ready with RESTARTS 0. No container has lastState.terminated.
  frontend-proxy-5766549668-rzdkr is 1/1, age 5m31s, 0 restarts.
- C4: `kubectl rollout history deploy/frontend-proxy` lists revision 13, which has a single `FRONTEND_HOST: frontend`.
  The image is unchanged. Comparing Deployment images (init and main containers) against `helm get manifest`:
  29/29 identical, `diff` is empty.

## In progress
- Nothing. Mitigation applied and verified by my own queries.

## Key decisions
- Removed only the shadowing env entry. I did not use `rollout undo`, so the change is explicit and visible as revision 13.
- The fault name in timeline.log was not used as evidence. The diagnosis rests on the queries above plus the deployment spec and pod status.

## Next steps
- Verifier: re-run C1/C2 queries with W = [max(now-5min, 05:33:49), now) and B = [05:18:10, 05:33:10).

## Open questions
- None.
