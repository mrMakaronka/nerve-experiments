# STATE — rvl-453f96ca (rep3-C, restart-only, iteration 1/1 — FINAL)

FAULT_INJECTION_TS_UTC: 2026-11-10 06:16:39   (latest `inject_done`, problem=env_variable_shadowing_astronomy_shop)
MITIGATION_TS_UTC: 2026-11-10 06:17:14

## Bottom line
**Restarts did NOT fix the incident.** The cause is in the Deployment spec, and a
restart re-creates pods from that same spec. The fix needs a spec change, which the
change freeze for this loop forbids. The incident is still active.

## Done
- Diagnosis (06:16:50–06:17:10 UTC):
  - Pods: `frontend-proxy-87c864665-sfdlf` 0/1 CrashLoopBackOff. Last state `OOMKilled`, exit 137, each run lasts ~1–2 s.
  - `kubectl get deploy frontend-proxy` env lists `FRONTEND_HOST=frontend` (original) and then a second
    `FRONTEND_HOST=localhost` at env[23]. The later definition wins, so Envoy's `frontend` upstream points at
    localhost:8080, which is Envoy's own listener (ENVOY_PORT=8080). Requests loop back into the proxy and memory
    blows up, giving OOMKilled. kubectl also warns: `env[23]: hides previous definition of "FRONTEND_HOST"`.
  - Telemetry (my query, per-minute `load-generator` Client spans since 06:01): err 0.0 % every minute
    06:01–06:15, p95 16–25 ms. The 06:16 minute: 22/139 errors (15.83 %), p95 60.6 ms. Error messages are
    `ConnectionError ... host='frontend-proxy', port=8080 ... [Errno 111] Connection refused` and `RemoteDisconnected`.
- Mitigation within the freeze: `kubectl -n astronomy-shop rollout restart deployment/frontend-proxy`, issued
  at about 06:17:11 UTC (annotation `kubectl.kubernetes.io/restartedAt: 2026-11-10T07:17:11+01:00`, rollout
  history revision 17, new RS `frontend-proxy-58ffcb8f4`). `rollout status` printed "successfully rolled out" at
  06:17:14 UTC. That message was misleading: the new pod had already restarted once at age 3 s.
- Post-restart: `frontend-proxy-58ffcb8f4-ml2qq` was OOMKilled again and in CrashLoopBackOff by 06:18:20.
  At 06:22:25 it was CrashLoopBackOff with 5 restarts.
- Verification query (run 06:22:33 UTC; W = [06:17:33.08, 06:22:33.08), 300 s; B = [06:01:39, 06:16:39)):
  ```sql
  WITH toDateTime64('2026-11-10 06:16:39',9,'UTC') AS t_inj, toDateTime64('2026-11-10 06:17:14',9,'UTC') AS t_mit,
   t_inj - INTERVAL 15 MINUTE AS b_start, t_inj AS b_end,
   greatest(now64(9) - INTERVAL 5 MINUTE, t_mit) AS w_start, now64(9) AS w_end
  SELECT
   countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end) AS b_lg,
   round(100*countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end AND StatusCode='Error')/greatest(b_lg,1),2) AS b_err_pct,
   round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=b_start AND Timestamp<b_end)/1e6,1) AS b_p95_ms,
   round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=b_start AND Timestamp<b_end)/15,1) AS b_fp_per_min,
   countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end) AS w_lg,
   round(100*countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end AND StatusCode='Error')/greatest(w_lg,1),2) AS w_err_pct,
   round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp>=w_start AND Timestamp<w_end)/1e6,1) AS w_p95_ms,
   round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp>=w_start AND Timestamp<w_end)/(dateDiff('second',w_start,w_end)/60),1) AS w_fp_per_min,
   dateDiff('second',w_start,w_end) AS w_window_s, w_start, w_end
  FROM otel_traces WHERE Timestamp >= b_start AND ServiceName IN ('load-generator','frontend-proxy')
  ```
  Returned: b_lg=2148, b_err_pct=0.0, b_p95_ms=19.6, b_fp_per_min=134.2 | w_lg=351, w_err_pct=89.17,
  w_p95_ms=19392.9, w_fp_per_min=0.0, w_window_s=300.
  - C1: error rate 89.17 % vs the allowed 1.0 % (FAIL). Edge volume 0.0/min vs the required 93.9/min, 70 % of 134.2 (FAIL).
  - C2: p95 19392.9 ms vs the allowed 23.5 ms, 1.2 × 19.6 (FAIL).
  - C3: frontend-proxy pod is CrashLoopBackOff/OOMKilled and restarted after T_mit (FAIL).
  - C4: the restart is visible as the restartedAt annotation, revision 17 and the new RS. All 23 unique container
    images across Deployments are present in `helm get manifest astronomy-shop` (0 live images missing). Helm has 3
    extra images: busybox init containers and the otel-collector DaemonSet image. I changed no image.

## In progress
- Nothing. The leg is finished.

## Key decisions
- I restarted only `frontend-proxy`, the one failing workload, which Envoy's OOMKilled state and the load-generator
  `Connection refused` errors point to. I did not restart other deployments: `frontend` and the backends are healthy,
  and restarting without a hypothesis is an anti-pattern. A `kubectl delete pod` is equivalent to the restart the
  ReplicaSet already performs, so it cannot help either.
- I did not try to work around the freeze. No `set env`, `patch`, `apply` or `rollout undo`.

## Next steps (need a human to lift the freeze)
- Proper fix: remove the shadowing `FRONTEND_HOST=localhost` entry (env[23]) from `deployment/frontend-proxy`. For
  example, `kubectl rollout undo deployment/frontend-proxy` to the last revision without it (check first with
  `kubectl rollout history --revision=N`), or a JSON patch removing `/spec/template/spec/containers/0/env/23`.
  Then verify with the C1/C2 query above over a fresh 300 s window.

## Open questions
- None about the cause. The only decision is the operator's: whether to allow a spec change.
