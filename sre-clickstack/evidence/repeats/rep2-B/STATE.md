# STATE — rvl-39d8e287 (iteration 3, final; earlier legs below)

MITIGATION_TS_UTC: 2026-11-10 04:25:55

- T_inj: 2026-11-10 04:25:02 UTC. Baseline B: [04:10:02, 04:25:02) UTC.
- Root cause: duplicate `FRONTEND_HOST=localhost` env in deploy/frontend-proxy. Fix: JSON-patch removal at 04:25:55. Full detail and SQL are in the Iteration 1 section below.

## Iteration 3 (2026-11-10 04:43–04:45 UTC): no mutating command; C2 still blocked outside my scope

### Done (read-only; these are my own unverified claims)
- **Criterion query** at 04:43:27 UTC, W = [04:38:27.39, 04:43:27.39), 300 s. The SQL is the verifier's iteration-2 query with `b_fp_spm` computed as `/15.0`:
  `b_lg_total 2045, b_lg_errors 1, b_error_pct 0.0489 | w_lg_total 3572, w_lg_errors 0, w_error_pct 0.0 | b_fp_spm 131.933, w_fp_spm 667.6, fp_ratio 5.0601 | b_p95_ns 21920266.8, w_p95_ns 33806792.0, p95_ratio 1.5423`.
  C1 passes. C2 FAILS: the limit is 26,304,320.16 ns.
- **Per-service Server p95, B vs the last 5 min**, plus row duplication. SQL: `SELECT ServiceName, quantileIf(0.95)(Duration,Timestamp<b_end)/1e6 AS b_p95_ms, quantileIf(0.95)(Duration,Timestamp>=now64()-INTERVAL 5 MINUTE)/1e6 AS w_p95_ms, countIf(..)/uniqExactIf((TraceId,SpanId),..) AS dup_factor FROM otel_traces WHERE SpanKind='Server' ... GROUP BY ServiceName`:
  cart 2.02→4.07 ms (2.01×, dup 7.74), currency 0.84→1.52 (1.81×, dup 7.84), ad 4.82→8.67 (1.80×, dup 7.35), frontend 20.22→30.43 (1.50×, dup 4.86), checkout 35.29→51.52 (1.46×), payment 2.05→2.98 (1.45×), frontend-proxy 21.1→30.46 (1.44×, dup 4.78).
  Leaf services that never touch frontend-proxy are slowed by the same factor, so the cause is host-wide, not a remaining astronomy-shop fault.
- **The host is still saturated by Jaeger.** At 04:43:18 `kubectl top pods -A` showed `observe/jaeger-agent-6ccbcc486d-9rznt` at 5773m CPU and 1012Mi (limit 1Gi). The next-highest pod was kube-apiserver at 37m.
- **New: I confirmed the mechanism of the span duplication.**
  - `kubectl -n observe logs deploy/otel-collector` shows the `otlp` exporter failing: `DeadlineExceeded` with retries, and `sending queue is full ... Rejecting data`.
  - All 3 `astronomy-shop/otel-collector-agent-*` pods log `Exporting failed. Will retry the request` every second or so.
  - So Jaeger's slowness backpressures the observe collector. The agents then retry batches the ClickStack exporter had already written, which is why rows are duplicated 5–8×. The retries also feed more load into Jaeger, a feedback loop.
  - Every lever is in `observe`, or else in the astronomy-shop agent's export path (the measuring path, C5). I did not touch either.
- **C3** at 04:44:17 UTC, `kubectl get pods` summarised: `25 × 1/1 Running 0` and `1 × 2/2 Running 0` (load-generator). No pod restarted after T_mit; frontend-proxy-6b55d7464d-7gvw9 is 17m old with 0 restarts.
- **C4:**
  - `rollout history deploy/frontend-proxy` lists revisions 7 and 8.
  - Live env has a single `FRONTEND_HOST=frontend`.
  - Live Deployment images (29, containers plus initContainers, sorted) `diff` against the Helm manifest Deployment images (29, extracted with awk on `kind: Deployment` documents) printed `IMAGES_IDENTICAL`.
- The operator escalations are still unanswered as of 04:43: notif-9d25088d (urgent, 04:32) and notif-8a1b1a3f (urgent, 04:39).

### In progress
- Nothing. C2 cannot be closed by any action I am authorised to take.

### Key decisions
- I made no astronomy-shop change in iteration 3. The remaining gap (p95 at 1.54× baseline) comes from host CPU and memory-reclaim starvation caused by observe/jaeger-agent. The agent-retry duplication amplifies it, and that also originates in observe.
- I rejected these options:
  - Sampling, throttling, or disabling retries in `otel-collector-agent`: this alters the measured telemetry (C5; the hard rule on the instrument).
  - Restarting astronomy-shop pods: there is no hypothesis, because they are not the bottleneck.
  - Rescheduling: Jaeger shares the Docker VM kernel with every kind node.

### Next steps (operator)
1. Restart `observe/jaeger-agent`, or raise its 1Gi memory limit / lower `--memory.max-traces`. This should also stop the collector backpressure and the 5–8× duplication.
2. Wait 5 minutes, then re-run the C2 query over a fresh 300 s window. No astronomy-shop change is expected to be needed.

### Open questions
- Is an `observe` scope exception granted? It is unanswered in notif-9d25088d and notif-8a1b1a3f.

---
(Iteration 2 notes follow, unchanged.)

## Iteration 2 (2026-11-10 04:37–04:41 UTC): no new astronomy-shop change; C2 blocked outside my scope

**Done in iteration 2 (no mutating command was run):**
- I re-ran the criterion query at 04:39:16 UTC (same SQL as §3 below, but returning raw ns p95). W = [04:34:16.46, 04:39:16.46), 300 s:
  `b_lg_spans 2045, b_lg_err 1, b_lg_err_pct 0.049 | w_lg_spans 3091, w_lg_err 0, w_lg_err_pct 0.0 | b_fp_spm 131.93, w_fp_spm 511.4, fp_volume_ratio 3.876 | b_lg_p95_ns 21920266.8, w_lg_p95_ns 34305625.0, p95_ratio 1.565`.
  This is my own unverified claim. C1 passes and C2 still FAILS (the limit is 26,304,320 ns).
- **The latency inflation spans the whole cluster and does not come from astronomy-shop.** p95 by service, B vs the last 5 min (query: `quantileIf(0.95)(Duration, ...)` grouped by ServiceName, SpanKind over B and `now64()-INTERVAL 5 MINUTE`):
  ad Server 4.82→16.1 ms (3.34×), currency Server 0.84→2.04 (2.43×), cart Server 2.02→5.11 (2.53×), checkout Server 35.3→73.0 (2.07×), payment Server 2.05→3.11 (1.52×), frontend Server 20.2→32.9 (1.63×), frontend-proxy Server 21.1→33.3 (1.58×).
  These leaf services have no dependency on frontend-proxy, so the slowdown is a host-level effect.
- **The host is saturated by Jaeger in `observe`.** At 04:37–04:39 UTC (all read-only): `kubectl top pods -A`: `observe/jaeger-agent-6ccbcc486d-9rznt` 6753m and later 7851m CPU at ~1015–1020Mi (limit 1Gi, request 100m). `kubectl top nodes`: kind-control-plane 8475m (84%) and each worker under 80m. `docker stats`: kind-control-plane 855% CPU. The Docker VM has 10 CPUs (`hw.ncpu` 15 on the Mac). Every kind node shares the VM kernel, so Jaeger's memory-limit thrash slows every pod. No astronomy-shop pod runs on kind-control-plane, so rescheduling cannot isolate them from it.
- **The only astronomy-shop lever is the telemetry path itself, and I refused it.** `astronomy-shop/otel-collector-agent` exports traces to `jaeger:4317`. `svc/jaeger` is an ExternalName pointing to `otel-collector.observe.svc.cluster.local`, i.e. SREGym's collector, which feeds both Jaeger and ClickStack. Throttling or sampling it would tamper with the measuring instrument (hard rule; C5).
- **New observation: since ~04:32 UTC every span lands in ClickHouse about 4×.** Query: `count()` vs `uniqExact(TraceId, SpanId)` per minute for load-generator Client: dup_factor 1.0 through 04:31, then 2.58 (04:32), 8.72 (04:33), 4.0 (04:34–04:36). The real request rate is unchanged (about 135–157 unique spans/min, the same as baseline; locust `user_count` 10). This is why `w_fp_spm` reads 3.9× baseline. Uniform duplication barely moves p95. The cause is in the telemetry pipeline (observe/ClickStack), which is outside my scope.
- C3 at 04:39:21 UTC: 25 pods `1/1 Running 0` and 1 pod `2/2 Running 0` (load-generator). Restarts are 0 everywhere.
- C4: `rollout history deploy/frontend-proxy` shows revisions 7 and 8. Exactly one `FRONTEND_HOST` env entry is left. Live Deployment images (29 lines, containers plus initContainers) `diff` against the `helm get manifest` Deployment images gave IMAGES_IDENTICAL.
- The operator escalation notif-9d25088d (urgent, 04:32 UTC) is still unanswered. I sent a follow-up in this leg.

**Key decision (iteration 2):** I made no further change. The remaining C2 gap can only be closed by restarting Jaeger or raising its memory limit in `observe/jaeger-agent`, and the TASK.md hard rule forbids that. The verifier's own feedback confirms that this needs an operator or a scope exception. Changing astronomy-shop objects to chase a host-level latency would be "restart to see if it helps" without a hypothesis.

**Next steps:** the operator restarts `observe/jaeger-agent` (or raises its 1Gi limit) and checks the 4× span duplication in the observe collector or ClickStack. Then re-run the C2 query over a fresh 300 s window that starts after Jaeger recovers. No astronomy-shop change is expected.

**Open questions:** Is a scope exception for observe granted? What causes the 4× ingest duplication since 04:32?

---
(Iteration 1 notes follow, unchanged.)

- T_inj (latest `inject_done` in timeline.log): **2026-11-10 04:25:02 UTC** (problem `env_variable_shadowing_astronomy_shop`)
- Baseline window B: **[2026-11-10 04:10:02, 2026-11-10 04:25:02) UTC** (15 min before inject_done)
- Post-fix window W: [max(now − 5 min, 04:25:55), now)

## Done

### 1. Root cause — duplicate env var shadows `FRONTEND_HOST` in deploy/frontend-proxy
The injection appended a second `FRONTEND_HOST` env entry (`localhost`) after the Helm one (`frontend`) in
`deploy/frontend-proxy`. Kubernetes uses the **last** definition, so Envoy's `frontend` upstream pointed at
`localhost:8080`, i.e. Envoy itself. The pod had no readiness gating against this. It was **OOMKilled**
(65Mi limit, which equals the Helm value) a second or two after each start, producing CrashLoopBackOff. With
the only edge pod down, every synthetic-user request failed with `ConnectionError ... host='frontend-proxy',
port=8080`. frontend-proxy and frontend emitted 0 server spans during the incident.

Kubernetes evidence (before fix, 04:25:30 UTC):
- `kubectl get pods`: `frontend-proxy-5b8758bbcc-v2bbk 0/1 CrashLoopBackOff`
- `kubectl describe pod`: `State: Terminated, Reason: OOMKilled, Exit Code: 137`, Restart Count 2, `Limits: memory 65Mi`
- Env (`kubectl get deploy frontend-proxy -o jsonpath=...env`): index 10 `FRONTEND_HOST=frontend`, index 23 `FRONTEND_HOST=localhost`
- Helm manifest (`helm get manifest`) for frontend-proxy: only `FRONTEND_HOST=frontend`, memory 65Mi, image `ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy`

Telemetry evidence (SQL run in this leg):
```sql
SELECT if(Timestamp < toDateTime64('2026-11-10 04:25:02',9,'UTC'),'baseline_15m','incident_53s') AS win,
  countIf(ServiceName='load-generator' AND SpanKind='Client') AS lg_spans,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error') AS lg_err,
  round(100*lg_err/greatest(lg_spans,1),2) AS lg_err_pct,
  countIf(ServiceName='frontend-proxy' AND SpanKind='Server') AS fp_spans,
  countIf(ServiceName='frontend' AND SpanKind='Server') AS fe_spans
FROM otel_traces
WHERE Timestamp >= toDateTime64('2026-11-10 04:10:02',9,'UTC') AND Timestamp < toDateTime64('2026-11-10 04:25:55',9,'UTC')
GROUP BY win ORDER BY win
```
| win | lg_spans | lg_err | lg_err_pct | fp_spans | fe_spans |
|---|---|---|---|---|---|
| baseline_15m | 2045 | 1 | 0.05 | 1979 | 3797 |
| incident_53s | 104 | 82 | 78.85 | **0** | **0** |

Top incident error messages, from a GROUP BY on StatusMessage over the same windows:
`ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/cart ...`
(22), `/api/products/...` (multiple), `RemoteDisconnected('Remote end closed connection without response')` (4).

### 2. Mitigation — kubectl JSON patch, guarded by a `test` op
```bash
kubectl --context kind-kind -n astronomy-shop patch deploy frontend-proxy --type=json -p \
 '[{"op":"test","path":"/spec/template/spec/containers/0/env/23","value":{"name":"FRONTEND_HOST","value":"localhost"}},
   {"op":"remove","path":"/spec/template/spec/containers/0/env/23"}]'
kubectl --context kind-kind -n astronomy-shop rollout status deploy/frontend-proxy   # -> successfully rolled out
date -u   # -> 2026-11-10 04:25:55
```
- Before: `spec.template.spec.containers[0].env` had 24 entries with `[10] FRONTEND_HOST=frontend` and `[23] FRONTEND_HOST=localhost`; deployment generation 7, active ReplicaSet `frontend-proxy-5b8758bbcc` (revision 7).
- After: 23 entries, a single `FRONTEND_HOST=frontend`; generation 8, active ReplicaSet `frontend-proxy-6b55d7464d` (revision 8, the same template as the Helm original), pod `frontend-proxy-6b55d7464d-7gvw9` 1/1 Running.
- Image unchanged (`ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy`). No other object changed.
- Note: a first patch attempt at ~04:25:49 failed in the shell (zsh did not word-split `$K`), so nothing was applied then. The patch above is the only change.

### 3. Self-verification (my own unverified claims; the verifier must re-run)
Query at 2026-11-10 04:31:23 UTC (W = [04:26:23, 04:31:23), 300 s):
```sql
WITH toDateTime64('2026-11-10 04:10:02', 9, 'UTC') AS b_start,
     toDateTime64('2026-11-10 04:25:02', 9, 'UTC') AS b_end,
     greatest(now64(9) - INTERVAL 5 MINUTE, toDateTime64('2026-11-10 04:25:55', 9, 'UTC')) AS w_start,
     now64(9) AS w_end
SELECT w_start, w_end, dateDiff('second', w_start, w_end) AS w_seconds,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp >= b_start AND Timestamp < b_end) AS b_lg_spans,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp >= b_start AND Timestamp < b_end AND StatusCode='Error') AS b_lg_err,
  round(100*b_lg_err/greatest(b_lg_spans,1),3) AS b_lg_err_pct,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp >= w_start AND Timestamp < w_end) AS w_lg_spans,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND Timestamp >= w_start AND Timestamp < w_end AND StatusCode='Error') AS w_lg_err,
  round(100*w_lg_err/greatest(w_lg_spans,1),3) AS w_lg_err_pct,
  round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp >= b_start AND Timestamp < b_end) / (dateDiff('second', b_start, b_end)/60), 2) AS b_fp_spm,
  round(countIf(ServiceName='frontend-proxy' AND SpanKind='Server' AND Timestamp >= w_start AND Timestamp < w_end) / (dateDiff('second', w_start, w_end)/60), 2) AS w_fp_spm,
  round(w_fp_spm / b_fp_spm, 3) AS fp_volume_ratio,
  round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp >= b_start AND Timestamp < b_end)/1e6, 2) AS b_lg_p95_ms,
  round(quantileIf(0.95)(Duration, ServiceName='load-generator' AND SpanKind='Client' AND Timestamp >= w_start AND Timestamp < w_end)/1e6, 2) AS w_lg_p95_ms,
  round(w_lg_p95_ms / b_lg_p95_ms, 3) AS p95_ratio
FROM otel_traces
WHERE Timestamp >= b_start AND ServiceName IN ('load-generator','frontend-proxy')
```
| metric | B | W | criterion | result |
|---|---|---|---|---|
| load-generator Client error % | 0.049 (1/2045) | 0.0 (0/733) | W ≤ B + 1pp | PASS |
| frontend-proxy Server spans/min | 131.93 | 138.2 (ratio 1.048) | ≥ 70% | PASS |
| load-generator Client p95 (ms) | 21.92 | 35.19 (ratio 1.605) | ≤ 1.2× | **FAIL** |

- Re-measured at 04:33:17 UTC (W = [04:28:16, 04:33:16), 300 s, same formulas): error rate 0.0% (B 0.049%), fp volume ratio 1.064, p95 **34.94 ms** against B 21.92 ms (1.59×, still FAIL). Jaeger was still at 9224m CPU.
- C3: `kubectl get pods` at 04:32:33 UTC: all 26 pods Running, READY n/n, RESTARTS 0. No container has a recorded previous termination.
- C4: images of all 22 Deployments (containers + initContainers), from `kubectl get deploy -o jsonpath`, are identical to the images in `helm -n astronomy-shop get manifest astronomy-shop` (`diff` was empty). `kubectl rollout history deploy/frontend-proxy` shows the new revision 8.

## In progress
- C2 (latency) is not at baseline, because of an environmental cause **outside the namespace I may change** (see Open questions).

## Key decisions
- Smallest fix: remove only the injected duplicate env entry, guarded by a JSON-patch `test` op so it could not remove the wrong entry. I did not use `rollout undo`: it would also work, but it is less explicit about what changed.
- Did not touch namespace `observe` (hard rule), even though the latency blocker is there.

## Next steps
- Verifier: re-run C1/C2 queries. If p95 is still > 1.2×, check whether Jaeger is still thrashing (see below).
- If the operator restarts Jaeger or raises its memory limit, re-measure p95 over a fresh 5-minute window. No further astronomy-shop change is expected to be needed.

## Open questions
- **Residual latency is caused by host CPU starvation from `observe/jaeger-agent-6ccbcc486d-9rznt` (Jaeger all-in-one, `--memory.max-traces=25000`).** Read-only evidence collected 04:31–04:32 UTC:
  - `kubectl top pods -n observe`: jaeger-agent at **9486m CPU**, 1018Mi
  - cgroup of PID 4469 on kind-control-plane: `memory.current 1073516544` / `memory.max 1073741824`, `memory.events max 604250`, i.e. pinned at its 1 GiB limit and in continuous reclaim (top: 92% `sy`)
  - `docker stats`: kind-control-plane container at 963% CPU; host load average about 11.8–14.7
  - Latency is up 1.5–3× in **every** service, including leaf services unrelated to frontend-proxy (currency p95 0.77→2.14 ms, cart 1.80→4.37 ms, payment 1.94→2.92 ms); `load-generator` p95 had already reached 31.8 ms at 04:24, *before* the injection.
  - Remedy (restart Jaeger or raise its memory) is forbidden to this worker. The operator was notified (notif-9d25088d, urgent).
