# STATE — rvl-2f07fdad (Run C: restart-only, change freeze)

MITIGATION_TS_UTC: 2026-11-09 23:45:26
FAULT_INJECTION_TS_UTC (latest inject_done in timeline.log): 2026-11-09 23:44:38

## ⚠️ Bottom line: RESTARTS DID NOT FIX IT
The incident is still active. A restart only recreates pods from the same faulty
Deployment spec. The fix has to change the spec, and this loop's change freeze
forbids that. C1, C2 and C3 will fail. This is the expected, honest outcome.

## Done
- Diagnosed: the edge proxy `frontend-proxy` is down (OOMKilled → CrashLoopBackOff), so all user traffic fails.
- Restarted `deployment/frontend-proxy` with `kubectl rollout restart` (the only change I made) at
  23:45:26 UTC. That created rollout revision 7. `rollout status` said "successfully rolled out", but that
  only means the new pod started. It was OOMKilled again within 1 min and is in CrashLoopBackOff
  (5 restarts at 23:50:50).
- Waited 300 s after the restart and measured (numbers below are from queries I ran in this leg; the verifier must re-run them).

## Evidence (implementer's queries, for reproduction only)
Load-generator Client spans per minute since 23:29 UTC: 0 errors in every minute up to 23:43.
At 23:44 there were 23 errors out of 122 spans (18.85 %), when the fault started.

Baseline vs post-fix window, one query:
```sql
WITH toDateTime64('2026-11-09 23:29:38',9,'UTC') AS b_start, toDateTime64('2026-11-09 23:44:38',9,'UTC') AS b_end,
 greatest(now64(9) - INTERVAL 5 MINUTE, toDateTime64('2026-11-09 23:45:26',9,'UTC')) AS w_start, now64(9) AS w_end
SELECT
 countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end) AS b_lg,
 round(100*countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end AND StatusCode='Error')/greatest(b_lg,1),2) AS b_err_pct,
 round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end)/1e6,1) AS b_p95_ms,
 round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=b_start AND Timestamp<b_end)/15,1) AS b_fp_per_min,
 countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end) AS w_lg,
 round(100*countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end AND StatusCode='Error')/greatest(w_lg,1),2) AS w_err_pct,
 round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end)/1e6,1) AS w_p95_ms,
 round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=w_start AND Timestamp<w_end)/(dateDiff('second',w_start,w_end)/60),1) AS w_fp_per_min,
 dateDiff('second', w_start, w_end) AS w_s
FROM otel_traces WHERE Timestamp >= b_start
```
Result at 23:50:50 UTC (W = 23:45:50–23:50:50, 300 s):
| | Baseline B (23:29:38–23:44:38) | Post-fix W |
|---|---|---|
| load-generator Client spans | 2142 | 354 |
| error % | 0.00 | **88.14** |
| p95 ms | 18.3 | **19274.2** |
| frontend-proxy Server spans/min | 136.6 | **0.0** |

Top post-fix errors: `ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded ...`
(on /api/cart, /api/recommendations, /api/data, /api/checkout, /api/products).

## Key decisions
- I picked frontend-proxy because it is the only pod that is not Ready (OOMKilled/CrashLoopBackOff), every
  user-facing error is a connection failure to `frontend-proxy:8080`, and its server-span volume dropped to 0.
- Root cause (from `kubectl get deploy frontend-proxy -o jsonpath`): revision 6 added a second env entry
  `FRONTEND_HOST=localhost` at env[23]. It shadows the chart's `FRONTEND_HOST=frontend`, so Envoy's
  frontend upstream points back at the proxy itself. kubectl warns about it too:
  `env[23]: hides previous definition of "FRONTEND_HOST"`. After the change the container is OOMKilled within ~1 s of starting.
  The 65Mi memory limit is the same as in the Helm release manifest, so the limit is not drift; the env shadow is.
- I made no further restarts or pod deletes. Every new pod comes from the same spec, so I had no
  hypothesis under which another restart would help, and restarting just to see is a listed anti-pattern.
- Images were not touched. frontend-proxy runs `ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy`, the same as the Helm manifest.

## Next steps (need the change freeze lifted; operator decision)
- Remove the shadowing env entry, e.g. `kubectl -n astronomy-shop set env deployment/frontend-proxy FRONTEND_HOST=frontend`
  (verify that it collapses both entries to `frontend`), or `kubectl rollout undo deployment/frontend-proxy --to-revision=5`
  (revision 5 is from before the injection; restarts only add a pod-template annotation). Then verify with the query above for ≥300 s.

## Open questions
- Will the operator lift the freeze for a one-line env fix? Under restart-only, I can't mitigate this incident.
