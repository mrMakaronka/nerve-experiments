# Run A: open-loop diagnosis

- session: `a18bd040`
- wall time: 102 s
- finished: 2026-11-09 23:05:19 UTC

## Prompt

There is an incident in astronomy-shop. Diagnose the root cause using telemetry.

This is a DIAGNOSIS-ONLY request: do not run any mutating command (no kubectl
set/patch/apply/edit/rollout/scale/delete). Read-only kubectl and ClickHouse
SELECT queries only.

Report: the faulty component, the mechanism, and the exact SQL queries + returned
numbers that support it. Distinguish the root-cause component from symptom
services. Finish with the fix you would apply (but do not apply it).


## Final answer

Edge failure: connection refused to frontend-proxy:8080. Now I'll get an aggregate count and check Kubernetes.Diagnosis is done. I'm saving the finding to memory, then the report follows.# Diagnosis: astronomy-shop outage since 2026-11-09 23:01 UTC

**Root cause:** `frontend-proxy` (the Envoy edge) is down. Deployment revision 4 added a second `FRONTEND_HOST` env var, `FRONTEND_HOST=localhost`, after the existing `FRONTEND_HOST=frontend`. Kubernetes keeps the last one, so Envoy's frontend route now points at itself on `localhost:8080`. The container is killed for running out of memory about one second after each start, the pod is in CrashLoopBackOff, and the `frontend-proxy` Service has no endpoints. Every user request fails with "connection refused".

## Telemetry evidence
All numbers below come from queries I ran in this session. The fault was injected at 23:01:00 UTC (from `timeline.log`).

**Q1: users are failing. 87.85% of load-generator requests get "connection refused" from the proxy.**
```sql
SELECT multiIf(StatusMessage LIKE '%frontend-proxy%Connection refused%', 'frontend-proxy:8080 connection refused',
               StatusCode = 'Error', 'other error', 'ok') AS outcome,
       count() AS n, round(100*n/sum(n) OVER (), 2) AS pct
FROM otel_traces
WHERE ServiceName = 'load-generator' AND SpanKind = 'Client'
  AND Timestamp >= toDateTime64('2026-11-09 23:01:15', 9, 'UTC') AND Timestamp < now() - INTERVAL 30 SECOND
GROUP BY outcome ORDER BY n DESC
```
| outcome | n | pct |
|---|---|---|
| frontend-proxy:8080 connection refused | 159 | 87.85 |
| ok | 18 | 9.94 |
| other error | 4 | 2.21 |

The 18 OK requests are the load generator's direct calls to `flagd`, which don't go through the proxy. The error text is `Failed to establish a new connection: [Errno 111] Connection refused` on every route: `/api/cart`, `/api/products/*`, `/api/checkout`, `/`.

**Q2: traffic stopped at the edge in the minute of the injection.**
```sql
SELECT toStartOfMinute(Timestamp) AS minute,
  countIf(ServiceName='frontend-proxy' AND SpanKind='Server') AS proxy_server_spans,
  countIf(ServiceName='frontend' AND SpanKind='Server') AS frontend_server_spans,
  countIf(ServiceName='load-generator' AND SpanKind='Client') AS lg_client,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error') AS lg_err
FROM otel_traces WHERE Timestamp >= toDateTime64('2026-11-09 22:55:00', 9, 'UTC')
GROUP BY minute ORDER BY minute
```
| minute | proxy | frontend | load-generator requests | load-generator errors |
|---|---|---|---|---|
| 22:55 – 23:00 | 120–143/min | 232–275/min | 125–147/min | **0** |
| 23:01 | **0** | 2 | 105 | 91 |
| 23:02 | 0 | 0 | 71 | 63 |
| 23:03 | 0 | 0 | 69 | 62 |

A follow-up query found the last `frontend-proxy` span at **23:00:57.424**, from the old pod `frontend-proxy-579d54f6f5-lq9rj`. The last `frontend` span was at 23:01:00.080.

**Q3: no downstream service has errors; they simply stopped getting traffic.** Window: 10 minutes before the injection vs 23:01:15 to now−30 s (130 s). This is the inject-boundary variant of the triage query.

| service (Server spans) | before: spans / error % | after: spans / error % |
|---|---|---|
| frontend-proxy | 1300 / 0.0 | **0** / – |
| frontend | 2508 / 0.0 | **0** / – |
| product-catalog | 1313 / 0.0 | 0 / – |
| cart | 576 / 0.0 | 0 / – |
| checkout, payment, shipping, currency, ad, recommendation, … | normal / 0.0 | 0 / – |
| flagd, image-provider | 448 / 0.0, 60 / 0.0 | 28 / 0.0, 13 / 0.0 (reached without the proxy) |

## Kubernetes evidence (read-only commands)
- **Pod:** `frontend-proxy-7b7cd5fb4-xhb4l` is `0/1 CrashLoopBackOff`, with 5 restarts in 3 minutes.
- **Why it dies:** the last termination was `reason: OOMKilled`, `exitCode: 137`, started 23:03:47 and finished 23:03:48. The memory limit is `65Mi`. Envoy's log ends normally (`all clusters initialized … starting workers`) right before the kill.
- **Endpoints:** `frontend-proxy` has none. `frontend` has 10.244.195.208:8080 and is Running 1/1, so it is healthy.
- **What changed:** `rollout history --revision=3` vs `--revision=4` differ in exactly one line: rev 4 adds `FRONTEND_HOST: localhost`. The good revision (3, ReplicaSet 579d54f6f5) had the same 65Mi limit, so the memory limit is not the cause; the env var is.
- **Timing:** events show deployment `frontend-proxy` scaled up ReplicaSet 7b7cd5fb4 and deleted the good pod 3m9s before I checked, which matches 23:01. ReplicaSet 7b7cd5fb4 also crash-looped 36 minutes earlier, during the 22:23 injection of the same fault.

## Mechanism
1. Revision 4 appends `FRONTEND_HOST=localhost` after `FRONTEND_HOST=frontend`, and Kubernetes keeps the last one.
2. Envoy's frontend route now points at `localhost:8080`, which is Envoy's own listener (`ENVOY_PORT=8080`).
3. Requests loop back into Envoy over and over, the container goes past 65Mi and is OOMKilled within about 1 s of starting.
4. The pod never becomes Ready, so the Service has no endpoints and the load generator gets "connection refused".
5. Nothing reaches `frontend` or anything behind it, so those services fall silent.

**Not verified:** steps 2–3 (Envoy looping into itself and running out of memory that way) are my inference. The env diff, the OOMKill, the ~1 s lifetime and the unchanged limit all point to it, but the crashing proxy emits no spans, so I could not see the loop in telemetry.

**Symptoms, not causes:** `frontend`, `product-catalog`, `cart`, `checkout`, `currency`, `shipping`, `recommendation`, `ad`, `product-reviews`, `email`, `payment`, `quote`. They all show zero traffic and zero errors. Their pods are fine; nothing is reaching them. `accounting` restarted 12 minutes before the injection and is Ready now; it is unrelated background noise.

## Fix I would apply (not applied, this was diagnosis-only)
Remove the shadowing entry with the smallest change, a rollback to revision 3:
```bash
kubectl --context kind-kind -n astronomy-shop rollout undo deploy/frontend-proxy --to-revision=3
kubectl --context kind-kind -n astronomy-shop rollout status deploy/frontend-proxy
date -u   # mitigation timestamp
```
Instead of the rollback, I could remove just the duplicate entry. It is the last item in the env list, index 23:
```bash
kubectl --context kind-kind -n astronomy-shop patch deploy frontend-proxy --type=json \
  -p='[{"op":"test","path":"/spec/template/spec/containers/0/env/23","value":{"name":"FRONTEND_HOST","value":"localhost"}},
       {"op":"remove","path":"/spec/template/spec/containers/0/env/23"}]'
```
The `test` step makes the patch refuse to run if index 23 is not that entry.

**How I would confirm it worked:** wait for at least 5 minutes of traffic after the mitigation timestamp, then re-run Q2 and Q3 against that window.
- `frontend-proxy` server spans back to about 120–140 per minute.
- Load-generator error rate back to about 0%, the pre-injection baseline.
- `frontend` and the downstream services back to their baseline volumes, with the proxy's p95 no more than 1.2 × the ~21 ms baseline.

I tried to save this finding to long-term memory twice and both attempts failed with a 401 (invalid API key). I wrote it to `memory/contexts/lessons-inbox.md` instead.

## Full transcript

### user — 2026-11-09 23:03:37

There is an incident in astronomy-shop. Diagnose the root cause using telemetry.

This is a DIAGNOSIS-ONLY request: do not run any mutating command (no kubectl
set/patch/apply/edit/rollout/scale/delete). Read-only kubectl and ClickHouse
SELECT queries only.

Report: the faulty component, the mechanism, and the exact SQL queries + returned
numbers that support it. Distinguish the root-cause component from symptom
services. Finish with the fix you would apply (but do not apply it).


### assistant — 2026-11-09 23:05:19

**tool `mcp__nerve__skill_get`**
```json
{
  "name": "incident-triage"
}
```
<details><summary>result</summary>

```
# Skill: Incident Triage (astronomy-shop) (v1.0.0)

Source: workspace

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

If `demo/evidence/timeline.log` has an `inject_done` event, prefer that timestamp
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
Pods that are Runni
```
</details>

**tool `mcp__nerve__skill_get`**
```json
{
  "name": "clickstack-schema"
}
```
<details><summary>result</summary>

```
# Skill: ClickStack Schema (traces/logs/metrics in ClickHouse) (v1.0.0)

Source: workspace

# ClickStack schema

Access: `clickhouse` MCP server → `run_select_query(query)`; read-only user,
database `default`. Queries are limited to 60 s and 10 000 result rows — always
aggregate, never `SELECT *` without `LIMIT`.

Data path: astronomy-shop pods → in-namespace collector → SREGym collector
(`observe` ns) → ClickStack OTLP → these tables. Ingestion lag is ~5–15 s; treat the
last 30 s as incomplete.

## Tables
| Table | What |
|---|---|
| `otel_traces` | one row per span (primary signal) |
| `otel_logs` | logs (sparse for this app) |
| `otel_metrics_gauge/sum/histogram/...` | metrics (not populated by this pipeline; use traces) |

## `otel_traces` key columns
| Column | Type | Notes |
|---|---|---|
| `Timestamp` | DateTime64(9) | span start, **UTC** |
| `TraceId`, `SpanId`, `ParentSpanId` | String | |
| `ServiceName` | LowCardinality(String) | e.g. `frontend-proxy`, `frontend`, `cart`, `product-catalog`, `checkout`, `recommendation` |
| `SpanName` | LowCardinality(String) | e.g. `GET /api/products/{productId}`, `oteldemo.CartService/GetCart`; Envoy server spans are just `GET`/`POST` |
| `SpanKind` | String | **`'Server'`, `'Client'`, `'Internal'`** (NOT `SPAN_KIND_SERVER`) |
| `StatusCode` | String | **`'Error'`, `'Unset'`, `'Ok'`** (NOT `STATUS_CODE_ERROR`) |
| `StatusMessage` | String | error text when set |
| `Duration` | UInt64 | **nanoseconds** → `/1e6` for ms |
| `SpanAttributes` | Map(String,String) | e.g. `http.status_code`, `http.url`, `rpc.grpc.status_code`, Envoy: `upstream_cluster`, `response_flags`, `peer.address` |
| `ResourceAttributes` | Map(String,String) | `k8s.pod.name`, `k8s.deployment.name`, `service.version`, … |
| `Events.Name`, `Events.Attributes` | Array | exceptions are events named `exception` |

## Services worth knowing
- `load-generator` = the synthetic users (Locust). Its `Client` spans are the
  **user-facing SLI**: every request a "user" makes, with `StatusMessage` holding the
  client-side error (connection refused, timeout, HTTP 5xx). When a service stops
  emitting spans entirely (crashed, OOMKilled, unreachable), this is where the
  failure stays visible.
- `frontend-proxy` = Envoy edge; all user traffic enters through it, then `frontend`.

## Pitfalls
- Use `SpanKind = 'Server'` for request-level stats; client spans double count.
- Envoy (`frontend-proxy`) marks 5xx responses `StatusCode='Error'`; the reason is in
  `SpanAttributes['response_flags']` (`UF` upstream connection failure, `UH` no healthy
  upstream, `URX` retry limit, `NR` no route) and `SpanAttributes['upstream_cluster']`.
- A collapse in span **volume** is a symptom too: if the edge fails, downstream
  services go quiet rather than erroring. Always show `count()` next to rates.
- `quantile()` is approximate (fine here); for small windows (`count() < 20`) say so.
- Background error rate is not zero: the AI-assistant route and the demo's
  feature-fl
```
</details>

**tool `mcp__nerve__memory_recall`**
```json
{
  "query": "What past astronomy-shop incidents and root causes do we know about?"
}
```
<details><summary>result</summary>

```
No relevant memories found.
```
</details>

**tool `ToolSearch`**
```json
{
  "query": "select:mcp__clickhouse__run_query,mcp__clickhouse__list_tables",
  "max_results": 2
}
```
<details><summary>result</summary>

```


```
</details>

**tool `Bash`**
```json
{
  "command": "tail -20 $HOME/Research/nerve-experiments/demo/evidence/timeline.log; date -u",
  "description": "Show incident timeline and current UTC time"
}
```
<details><summary>result</summary>

```
{"ts_utc": "2026-11-09 22:13:22", "event": "deploy_start", "problem": "env_variable_shadowing_astronomy_shop"}
{"ts_utc": "2026-11-09 22:20:48", "event": "deploy_done", "problem": "env_variable_shadowing_astronomy_shop"}
{"ts_utc": "2026-11-09 22:23:42", "event": "inject_start", "problem": "env_variable_shadowing_astronomy_shop"}
{"ts_utc": "2026-11-09 22:23:43", "event": "inject_done", "problem": "env_variable_shadowing_astronomy_shop"}
{"ts_utc": "2026-11-09 22:27:28", "event": "recover_done", "problem": "env_variable_shadowing_astronomy_shop"}
{"ts_utc": "2026-11-09 23:00:59", "event": "inject_start", "problem": "env_variable_shadowing_astronomy_shop"}
{"ts_utc": "2026-11-09 23:01:00", "event": "inject_done", "problem": "env_variable_shadowing_astronomy_shop"}
Mon Nov  9 23:03:46 UTC 2026
```
</details>

**tool `mcp__clickhouse__run_query`**
```json
{
  "query": "SELECT ServiceName,\n       countIf(Timestamp >= now() - INTERVAL 10 MINUTE) AS cur_n,\n       round(100 * countIf(Timestamp >= now() - INTERVAL 10 MINUTE AND StatusCode = 'Error') / greatest(cur_n, 1), 2) AS cur_err_pct,\n       countIf(Timestamp < now() - INTERVAL 10 MINUTE) AS base_n,\n       round(100 * countIf(Timestamp < now() - INTERVAL 10 MINUTE AND StatusCode = 'Error') / greatest(base_n, 1), 2) AS base_err_pct,\n       round(quantileIf(0.95)(Duration, Timestamp >= now() - INTERVAL 10 MINUTE) / 1e6, 1) AS cur_p95_ms,\n       round(quantileIf(0.95)(Duration, Timestamp <  now() - INTERVAL 10 MINUTE) / 1e6, 1) AS base_p95_ms\nFROM otel_traces\nWHERE Timestamp >= now() - INTERVAL 25 MINUTE AND SpanKind = 'Server'\nGROUP BY ServiceName ORDER BY cur_err_pct DESC, cur_n DESC"
}
```
<details><summary>result</summary>

```
{"result":"{\"columns\": [\"ServiceName\", \"cur_n\", \"cur_err_pct\", \"base_n\", \"base_err_pct\", \"cur_p95_ms\", \"base_p95_ms\"], \"rows\": [[\"frontend\", 1754, 0.0, 4042, 0.0, 21.4, 20.6], [\"product-catalog\", 927, 0.0, 1969, 0.0, 4.9, 4.5], [\"frontend-proxy\", 907, 0.0, 2101, 0.0, 21.8, 21.4], [\"cart\", 389, 0.0, 1007, 0.0, 2.3, 2.0], [\"flagd\", 341, 0.0, 735, 0.54, 0.4, 0.3], [\"currency\", 100, 0.0, 299, 0.0, 0.8, 0.7], [\"recommendation\", 87, 0.0, 151, 0.0, 4.5, 4.6], [\"product-reviews\", 77, 0.0, 167, 0.0, 31.8, 32.7], [\"shipping\", 70, 0.0, 210, 0.0, 3.1, 2.7], [\"ad\", 64, 0.0, 160, 0.0, 6.1, 8.7], [\"image-provider\", 60, 0.0, 90, 0.0, 0.0, 0.0], [\"quote\", 35, 0.0, 105, 0.0, 0.9, 0.7], [\"email\", 35, 0.0, 105, 0.0, 14.1, 9.8], [\"checkout\", 35, 0.0, 105, 0.0, 40.3, 31.9], [\"payment\", 35, 0.0, 105, 0.0, 2.0, 2.0]]}"}
```
</details>

**tool `mcp__clickhouse__run_query`**
```json
{
  "query": "WITH toDateTime64('2026-11-09 23:01:00', 9, 'UTC') AS inj\nSELECT ServiceName, SpanKind,\n  countIf(Timestamp >= inj - INTERVAL 10 MINUTE AND Timestamp < inj) AS base_n,\n  round(100*countIf(Timestamp >= inj - INTERVAL 10 MINUTE AND Timestamp < inj AND StatusCode='Error')/greatest(base_n,1),2) AS base_err_pct,\n  countIf(Timestamp >= inj + INTERVAL 15 SECOND AND Timestamp < now() - INTERVAL 30 SECOND) AS cur_n,\n  round(100*countIf(Timestamp >= inj + INTERVAL 15 SECOND AND Timestamp < now() - INTERVAL 30 SECOND AND StatusCode='Error')/greatest(cur_n,1),2) AS cur_err_pct,\n  dateDiff('second', inj + INTERVAL 15 SECOND, now() - INTERVAL 30 SECOND) AS cur_window_s\nFROM otel_traces\nWHERE Timestamp >= inj - INTERVAL 10 MINUTE AND SpanKind IN ('Server','Client')\nGROUP BY ServiceName, SpanKind ORDER BY cur_err_pct DESC, ServiceName"
}
```
<details><summary>result</summary>

```
{"result":"{\"columns\": [\"ServiceName\", \"SpanKind\", \"base_n\", \"base_err_pct\", \"cur_n\", \"cur_err_pct\", \"cur_window_s\"], \"rows\": [[\"load-generator\", \"Client\", 1381, 0.0, 169, 89.35, 130], [\"accounting\", \"Client\", 58, 3.45, 0, 0.0, 130], [\"ad\", \"Server\", 94, 0.0, 0, 0.0, 130], [\"cart\", \"Server\", 576, 0.0, 0, 0.0, 130], [\"cart\", \"Client\", 1154, 0.0, 10, 0.0, 130], [\"checkout\", \"Server\", 56, 0.0, 0, 0.0, 130], [\"checkout\", \"Client\", 600, 0.0, 0, 0.0, 130], [\"currency\", \"Server\", 160, 0.0, 0, 0.0, 130], [\"email\", \"Server\", 56, 0.0, 0, 0.0, 130], [\"flagd\", \"Server\", 448, 0.0, 28, 0.0, 130], [\"frontend\", \"Server\", 2508, 0.0, 0, 0.0, 130], [\"frontend\", \"Client\", 1924, 0.0, 0, 0.0, 130], [\"frontend-proxy\", \"Client\", 1300, 0.0, 0, 0.0, 130], [\"frontend-proxy\", \"Server\", 1300, 0.0, 0, 0.0, 130], [\"image-provider\", \"Server\", 60, 0.0, 13, 0.0, 130], [\"payment\", \"Server\", 56, 0.0, 0, 0.0, 130], [\"product-catalog\", \"Server\", 1313, 0.0, 0, 0.0, 130], [\"product-catalog\", \"Client\", 1313, 0.0, 0, 0.0, 130], [\"product-reviews\", \"Client\", 225, 0.0, 0, 0.0, 130], [\"product-reviews\", \"Server\", 101, 0.0, 0, 0.0, 130], [\"quote\", \"Server\", 56, 0.0, 0, 0.0, 130], [\"recommendation\", \"Server\", 117, 0.0, 0, 0.0, 130], [\"recommendation\", \"Client\", 117, 0.0, 0, 0.0, 130], [\"shipping\", \"Server\", 112, 0.0, 0, 0.0, 130], [\"shipping\", \"Client\", 56, 0.0, 0, 0.0, 130]]}"}
```
</details>

**tool `mcp__clickhouse__run_query`**
```json
{
  "query": "SELECT SpanName, StatusCode, StatusMessage,\n       SpanAttributes['http.status_code'] AS http_status,\n       SpanAttributes['http.url'] AS url_sample_key,\n       count() AS n\nFROM otel_traces\nWHERE ServiceName = 'load-generator' AND SpanKind = 'Client'\n  AND Timestamp >= toDateTime64('2026-11-09 23:01:15', 9, 'UTC')\nGROUP BY SpanName, StatusCode, StatusMessage, http_status, url_sample_key\nORDER BY n DESC LIMIT 25"
}
```
<details><summary>result</summary>

```
{"result":"{\"columns\": [\"SpanName\", \"StatusCode\", \"StatusMessage\", \"http_status\", \"url_sample_key\", \"n\"], \"rows\": [[\"POST\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/cart (Caused by NewConnectionError(\\\"HTTPConnection(host='frontend-proxy', port=8080): Failed to establish a new connection: [Errno 111] Connection refused\\\"))\", \"\", \"http://frontend-proxy:8080/api/cart\", 33], [\"POST\", \"Unset\", \"\", \"200\", \"http://flagd:8016/ofrep/v1/evaluate/flags/loadGeneratorFloodHomepage\", 21], [\"GET\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/cart (Caused by NewConnectionError(\\\"HTTPConnection(host='frontend-proxy', port=8080): Failed to establish a new connection: [Errno 111] Connection refused\\\"))\", \"\", \"http://frontend-proxy:8080/api/cart\", 14], [\"GET\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/products/6E92ZMYYFZ (Caused by NewConnectionError(\\\"HTTPConnection(host='frontend-proxy', port=8080): Failed to establish a new connection: [Errno 111] Connection refused\\\"))\", \"\", \"http://frontend-proxy:8080/api/products/6E92ZMYYFZ\", 11], [\"GET\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/products/LS4PSXUNUM (Caused by NewConnectionError(\\\"HTTPConnection(host='frontend-proxy', port=8080): Failed to establish a new connection: [Errno 111] Connection refused\\\"))\", \"\", \"http://frontend-proxy:8080/api/products/LS4PSXUNUM\", 10], [\"GET\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/products/1YMWWN1N4O (Caused by NewConnectionError(\\\"HTTPConnection(host='frontend-proxy', port=8080): Failed to establish a new connection: [Errno 111] Connection refused\\\"))\", \"\", \"http://frontend-proxy:8080/api/products/1YMWWN1N4O\", 10], [\"POST\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/checkout (Caused by NewConnectionError(\\\"HTTPConnection(host='frontend-proxy', port=8080): Failed to establish a new connection: [Errno 111] Connection refused\\\"))\", \"\", \"http://frontend-proxy:8080/api/checkout\", 10], [\"GET\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/products/9SIQT8TOJO (Caused by NewConnectionError(\\\"HTTPConnection(host='frontend-proxy', port=8080): Failed to establish a new connection: [Errno 111] Connection refused\\\"))\", \"\", \"http://frontend-proxy:8080/api/products/9SIQT8TOJO\", 9], [\"GET\", \"Error\", \"ConnectionError: HTTPConnectionPool(host='frontend-proxy', port=8080): Max retries exceeded with url: /api/products/OLJCESPC7Z (Caused by NewConnectionError(\
```
</details>

Edge failure: connection refused to frontend-proxy:8080. Now I'll get an aggregate count and check Kubernetes.
**tool `mcp__clickhouse__run_query`**
```json
{
  "query": "SELECT\n  multiIf(StatusMessage LIKE '%frontend-proxy%Connection refused%', 'frontend-proxy:8080 connection refused',\n          StatusCode = 'Error', 'other error', 'ok') AS outcome,\n  SpanAttributes['net.peer.name'] AS peer_hint,\n  count() AS n,\n  round(100*n/sum(n) OVER (), 2) AS pct\nFROM otel_traces\nWHERE ServiceName = 'load-generator' AND SpanKind = 'Client'\n  AND Timestamp >= toDateTime64('2026-11-09 23:01:15', 9, 'UTC') AND Timestamp < now() - INTERVAL 30 SECOND\nGROUP BY outcome, peer_hint ORDER BY n DESC"
}
```
<details><summary>result</summary>

```
{"result":"{\"columns\": [\"outcome\", \"peer_hint\", \"n\", \"pct\"], \"rows\": [[\"frontend-proxy:8080 connection refused\", \"\", 159, 87.85], [\"ok\", \"\", 18, 9.94], [\"other error\", \"\", 4, 2.21]]}"}
```
</details>

**tool `mcp__clickhouse__run_query`**
```json
{
  "query": "SELECT toStartOfMinute(Timestamp) AS minute,\n  countIf(ServiceName='frontend-proxy' AND SpanKind='Server') AS proxy_server_spans,\n  countIf(ServiceName='frontend' AND SpanKind='Server') AS frontend_server_spans,\n  countIf(ServiceName='load-generator' AND SpanKind='Client') AS lg_client,\n  countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error') AS lg_err\nFROM otel_traces\nWHERE Timestamp >= toDateTime64('2026-11-09 22:55:00', 9, 'UTC')\nGROUP BY minute ORDER BY minute"
}
```
<details><summary>result</summary>

```
{"result":"{\"columns\": [\"minute\", \"proxy_server_spans\", \"frontend_server_spans\", \"lg_client\", \"lg_err\"], \"rows\": [[\"2026-11-09 22:55:00\", 124, 240, 131, 0], [\"2026-11-09 22:56:00\", 143, 275, 147, 0], [\"2026-11-09 22:57:00\", 122, 232, 125, 0], [\"2026-11-09 22:58:00\", 120, 233, 135, 0], [\"2026-11-09 22:59:00\", 123, 242, 133, 0], [\"2026-11-09 23:00:00\", 136, 265, 147, 0], [\"2026-11-09 23:01:00\", 0, 2, 105, 91], [\"2026-11-09 23:02:00\", 0, 0, 71, 63], [\"2026-11-09 23:03:00\", 0, 0, 69, 62], [\"2026-11-09 23:04:00\", 0, 0, 1, 0]]}"}
```
</details>

**tool `Bash`**
```json
{
  "command": "kubectl --context kind-kind -n astronomy-shop get pods -o wide | grep -E 'NAME|frontend'; echo ---; kubectl --context kind-kind -n astronomy-shop get events --sort-by=.lastTimestamp | tail -25; echo ---; kubectl --context kind-kind -n astronomy-shop rollout history deploy/frontend-proxy",
  "description": "Read frontend pods, recent events, proxy rollout history"
}
```
<details><summary>result</summary>

```
NAME                               READY   STATUS             RESTARTS      AGE    IP               NODE           NOMINATED NODE   READINESS GATES
frontend-6859c775df-gnfhx          1/1     Running            0             46m    10.244.195.208   kind-worker3   <none>           <none>
frontend-proxy-7b7cd5fb4-xhb4l     0/1     CrashLoopBackOff   5 (20s ago)   3m9s   10.244.195.212   kind-worker3   <none>           <none>
---
37m         Normal    Created             pod/frontend-proxy-7b7cd5fb4-hx98f      Created container: frontend-proxy
36m         Warning   BackOff             pod/frontend-proxy-7b7cd5fb4-hx98f      Back-off restarting failed container frontend-proxy in pod frontend-proxy-7b7cd5fb4-hx98f_astronomy-shop(c07bfda0-f9cc-4440-9f1f-2d836904231b)
36m         Normal    Scheduled           pod/frontend-proxy-579d54f6f5-lq9rj     Successfully assigned astronomy-shop/frontend-proxy-579d54f6f5-lq9rj to kind-worker2
36m         Normal    SuccessfulCreate    replicaset/frontend-proxy-579d54f6f5    Created pod: frontend-proxy-579d54f6f5-lq9rj
36m         Normal    ScalingReplicaSet   deployment/frontend-proxy               Scaled up replica set frontend-proxy-579d54f6f5 from 0 to 1
36m         Normal    Pulling             pod/frontend-proxy-579d54f6f5-lq9rj     Pulling image "ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy"
36m         Normal    Started             pod/frontend-proxy-579d54f6f5-lq9rj     Started container frontend-proxy
36m         Normal    Created             pod/frontend-proxy-579d54f6f5-lq9rj     Created container: frontend-proxy
36m         Normal    Pulled              pod/frontend-proxy-579d54f6f5-lq9rj     Successfully pulled image "ghcr.io/open-telemetry/demo:2.2.0-frontend-proxy" in 7.579s (7.579s including waiting). Image size: 58068574 bytes.
36m         Normal    ScalingReplicaSet   deployment/frontend-proxy               Scaled down replica set frontend-proxy-7b7cd5fb4 from 1 to 0
36m         Normal    SuccessfulDelete    replicaset/frontend-proxy-7b7cd5fb4     Deleted pod: frontend-proxy-7b7cd5fb4-hx98f
12m         Warning   BackOff             pod/accounting-5897477844-852s2         Back-off restarting failed container accounting in pod accounting-5897477844-852s2_astronomy-shop(eba27692-b795-4f83-8ec8-fd986afcba8b)
12m         Normal    Started             pod/accounting-5897477844-852s2         Started container accounting
12m         Normal    Pulled              pod/accounting-5897477844-852s2         Container image "ghcr.io/open-telemetry/demo:nightly-20939609681-accounting@sha256:51e6720438c13d0a4fefd129b01e2422b176fdb18a9ea71ef08fd84e717e82f4" already present on machine
12m         Normal    Created             pod/accounting-5897477844-852s2         Created container: accounting
3m9s        Normal    SuccessfulCreate    replicaset/frontend-proxy-7b7cd5fb4     Created pod: frontend-proxy-7b7cd5fb4-xhb4l
3m9s        Normal    Scheduled           pod/frontend-proxy-7b7cd5fb4-xhb4l      Successfully a
```
</details>

**tool `Bash`**
```json
{
  "command": "K=\"kubectl --context kind-kind -n astronomy-shop\"\n$K logs frontend-proxy-7b7cd5fb4-xhb4l --previous --tail=30 2>&1; echo \"--- current env (rev 4)\"\n$K get deploy frontend-proxy -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{.valueFrom}{\"\\n\"}{end}'; echo \"--- rev 3 env\"\n$K rollout history deploy/frontend-proxy --revision=3 | sed -n '/Environment/,/Mounts/p'; echo \"--- rev 4 env\"\n$K rollout history deploy/frontend-proxy --revision=4 | sed -n '/Environment/,/Mounts/p'",
  "description": "Read crashing proxy logs and compare env across revisions"
}
```
<details><summary>result</summary>

```
(eval):2: command not found: kubectl --context kind-kind -n astronomy-shop
--- current env (rev 4)
(eval):3: command not found: kubectl --context kind-kind -n astronomy-shop
--- rev 3 env
(eval):4: command not found: kubectl --context kind-kind -n astronomy-shop
--- rev 4 env
(eval):5: command not found: kubectl --context kind-kind -n astronomy-shop
```
</details>

**tool `Bash`**
```json
{
  "command": "k(){ kubectl --context kind-kind -n astronomy-shop \"$@\"; }\nk logs frontend-proxy-7b7cd5fb4-xhb4l --previous --tail=30 2>&1; echo \"--- current env (rev 4)\"\nk get deploy frontend-proxy -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{.valueFrom}{\"\\n\"}{end}'; echo \"--- rev 3 env\"\nk rollout history deploy/frontend-proxy --revision=3 | sed -n '/Environment/,/Mounts/p'; echo \"--- rev 4 env\"\nk rollout history deploy/frontend-proxy --revision=4 | sed -n '/Environment/,/Mounts/p'",
  "description": "Read crashing proxy logs and compare env across revisions"
}
```
<details><summary>result</summary>

```
[2026-11-09 23:03:47.667][1][info][main] [source/server/server.cc:440]   envoy.http.stateful_session: envoy.http.stateful_session.cookie, envoy.http.stateful_session.header
[2026-11-09 23:03:47.667][1][info][main] [source/server/server.cc:440]   envoy.rds_factory: envoy.rds_factory.default
[2026-11-09 23:03:47.669][1][info][main] [source/server/server.cc:500] HTTP header map info:
[2026-11-09 23:03:47.670][1][info][main] [source/server/server.cc:503]   request header map: 656 bytes: :authority,:method,:path,:protocol,:scheme,accept,accept-encoding,access-control-request-headers,access-control-request-method,access-control-request-private-network,authentication,authorization,cache-control,cdn-loop,connection,content-encoding,content-length,content-type,expect,grpc-accept-encoding,grpc-timeout,if-match,if-modified-since,if-none-match,if-range,if-unmodified-since,keep-alive,origin,pragma,proxy-connection,proxy-status,referer,te,transfer-encoding,upgrade,user-agent,via,x-client-trace-id,x-envoy-attempt-count,x-envoy-decorator-operation,x-envoy-downstream-service-cluster,x-envoy-downstream-service-node,x-envoy-expected-rq-timeout-ms,x-envoy-external-address,x-envoy-force-trace,x-envoy-hedge-on-per-try-timeout,x-envoy-internal,x-envoy-ip-tags,x-envoy-is-timeout-retry,x-envoy-max-retries,x-envoy-original-path,x-envoy-original-url,x-envoy-retriable-header-names,x-envoy-retriable-status-codes,x-envoy-retry-grpc-on,x-envoy-retry-on,x-envoy-upstream-alt-stat-name,x-envoy-upstream-rq-per-try-timeout-ms,x-envoy-upstream-rq-timeout-alt-response,x-envoy-upstream-rq-timeout-ms,x-envoy-upstream-stream-duration-ms,x-forwarded-client-cert,x-forwarded-for,x-forwarded-host,x-forwarded-port,x-forwarded-proto,x-request-id
[2026-11-09 23:03:47.670][1][info][main] [source/server/server.cc:503]   request trailer map: 120 bytes: 
[2026-11-09 23:03:47.670][1][info][main] [source/server/server.cc:503]   response header map: 432 bytes: :status,access-control-allow-credentials,access-control-allow-headers,access-control-allow-methods,access-control-allow-origin,access-control-allow-private-network,access-control-expose-headers,access-control-max-age,age,cache-control,connection,content-encoding,content-length,content-type,date,etag,expires,grpc-message,grpc-status,keep-alive,last-modified,location,proxy-connection,proxy-status,server,transfer-encoding,upgrade,vary,via,x-envoy-attempt-count,x-envoy-decorator-operation,x-envoy-degraded,x-envoy-immediate-health-check-fail,x-envoy-ratelimited,x-envoy-upstream-canary,x-envoy-upstream-healthchecked-cluster,x-envoy-upstream-service-time,x-request-id
[2026-11-09 23:03:47.670][1][info][main] [source/server/server.cc:503]   response trailer map: 144 bytes: grpc-message,grpc-status
[2026-11-09 23:03:47.672][1][info][main] [source/server/server.cc:901] runtime: layers:
  - name: static_layer_0
    static_layer:
      envoy:
        resource_limits:
          listener:
            example_listener_name:
              connection_limit: 1000
```
</details>

**tool `Bash`**
```json
{
  "command": "k(){ kubectl --context kind-kind -n astronomy-shop \"$@\"; }\nk get pod frontend-proxy-7b7cd5fb4-xhb4l -o jsonpath='{.status.containerStatuses[0].lastState}{\"\\n\"}{.status.containerStatuses[0].restartCount}{\"\\n\"}'\nk get deploy frontend-proxy -o jsonpath='{.spec.template.spec.containers[0].livenessProbe}{\"\\n\"}{.spec.template.spec.containers[0].readinessProbe}{\"\\n\"}{.spec.template.spec.containers[0].resources}{\"\\n\"}'\nk get pod frontend-proxy-7b7cd5fb4-xhb4l -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}{\"\\n\"}'\nk get endpoints frontend-proxy frontend -o wide\nk get pods --no-headers | awk '$3!=\"Running\" || $2 !~ /^1\\/1|^2\\/2/'",
  "description": "Inspect crash reason, probes, endpoints, unhealthy pods"
}
```
<details><summary>result</summary>

```
{"terminated":{"containerID":"containerd://05e1e5e355d6a4a01a777c2a871aac9af4aa529e7794f960cfbb34f24e8f83ef","exitCode":137,"finishedAt":"2026-11-09T23:03:48Z","reason":"OOMKilled","startedAt":"2026-11-09T23:03:47Z"}}
5


{"limits":{"memory":"65Mi"}}
PodReadyToStartContainers=True Initialized=True Ready=False ContainersReady=False PodScheduled=True 
NAME             ENDPOINTS             AGE
frontend-proxy                         46m
frontend         10.244.195.208:8080   46m
frontend-proxy-7b7cd5fb4-xhb4l     0/1   CrashLoopBackOff   5 (36s ago)   3m25s
```
</details>

**tool `Bash`**
```json
{
  "command": "k(){ kubectl --context kind-kind -n astronomy-shop \"$@\"; }\ndiff <(k rollout history deploy/frontend-proxy --revision=3 | sed 1,2d) <(k rollout history deploy/frontend-proxy --revision=4 | sed 1,2d)\nfor r in 579d54f6f5 7b7cd5fb4; do echo \"$r: $(k get rs frontend-proxy-$r -o jsonpath='{.metadata.annotations.deployment\\.kubernetes\\.io/revision} limits={.spec.template.spec.containers[0].resources.limits}')\"; done\nk get pod -l app.kubernetes.io/component=accounting -o jsonpath='{range .items[*]}{.metadata.name} restarts={.status.containerStatuses[0].restartCount} ready={.status.containerStatuses[0].ready}{\"\\n\"}{end}'",
  "description": "Diff good vs bad revision, check limits and accounting"
}
```
<details><summary>result</summary>

```
5c5
< 	pod-template-hash=579d54f6f5
---
> 	pod-template-hash=7b7cd5fb4
48a49
>       FRONTEND_HOST:	localhost
579d54f6f5: 3 limits={"memory":"65Mi"}
7b7cd5fb4: 4 limits={"memory":"65Mi"}
accounting-5897477844-852s2 restarts=3 ready=true
```
</details>

**tool `mcp__clickhouse__run_query`**
```json
{
  "query": "SELECT ServiceName, max(Timestamp) AS last_span, ResourceAttributes['k8s.pod.name'] AS pod, count() AS spans_since_2250\nFROM otel_traces\nWHERE ServiceName IN ('frontend-proxy','frontend') AND Timestamp >= toDateTime64('2026-11-09 22:50:00', 9, 'UTC')\nGROUP BY ServiceName, pod ORDER BY ServiceName, last_span"
}
```
<details><summary>result</summary>

```
{"result":"{\"columns\": [\"ServiceName\", \"last_span\", \"pod\", \"spans_since_2250\"], \"rows\": [[\"frontend\", \"2026-11-09 23:01:00.080000\", \"frontend-6859c775df-gnfhx\", 6326], [\"frontend-proxy\", \"2026-11-09 23:00:57.424052\", \"frontend-proxy-579d54f6f5-lq9rj\", 2900]]}"}
```
</details>

Diagnosis is done. I'm saving the finding to memory, then the report follows.
**tool `mcp__nerve__memorize`**
```json
{
  "content": "2026-11-09 23:01 UTC incident (SREGym problem env_variable_shadowing_astronomy_shop, second injection): frontend-proxy deployment revision 4 appended a duplicate env var FRONTEND_HOST=localhost after FRONTEND_HOST=frontend. Kubernetes keeps the last one, so Envoy's frontend cluster pointed back at its own listener on localhost:8080. The pod was OOMKilled (exit 137, 65Mi limit) about 1 s after each start and went into CrashLoopBackOff, and the frontend-proxy Service had no endpoints. Telemetry: frontend-proxy server spans fell from about 120-143/min to 0 at 23:01; load-generator client spans showed 87.85% 'frontend-proxy:8080 Connection refused'; all downstream services went quiet with 0% errors (symptoms only). The only difference between rev 3 and rev 4 was that env var, and the memory limit was 65Mi in both. Fix: kubectl rollout undo deploy/frontend-proxy --to-revision=3, or remove the duplicate entry with a JSON patch (remove /spec/template/spec/containers/0/env/<last index>). This was diagnosis-only, so nothing was applied.",
  "memory_type": "event"
}
```
<details><summary>result</summary>

```
Failed to memorize (last error: Error code: 401 - Invalid Anthropic API Key). This is an infrastructure failure, not a content refusal — retry later or keep the fact elsewhere.
```
</details>

**tool `mcp__nerve__memorize`**
```json
{
  "content": "2026-11-09 23:01 UTC astronomy-shop incident: frontend-proxy rev 4 got a duplicate env var FRONTEND_HOST=localhost, which shadowed FRONTEND_HOST=frontend because the last one wins. Envoy routed to itself, the pod was OOMKilled (65Mi) and went into CrashLoopBackOff, and the Service had no endpoints. The load generator saw 87.85% connection refused and downstream services went quiet. Fix: rollout undo to rev 3, or remove the duplicate env entry. Diagnosis only, nothing applied.",
  "memory_type": "event"
}
```
<details><summary>result</summary>

```
Failed to memorize (last error: Error code: 401 - Invalid Anthropic API Key). This is an infrastructure failure, not a content refusal — retry later or keep the fact elsewhere.
```
</details>

**tool `Bash`**
```json
{
  "command": "mkdir -p $HOME/nerve-demo-workspace/memory/contexts && cat >> $HOME/nerve-demo-workspace/memory/contexts/lessons-inbox.md <<'EOF'\n- [added 2026-11-10] astronomy-shop incident 2026-11-09 23:01 UTC (env_variable_shadowing): frontend-proxy rev 4 appended a duplicate `FRONTEND_HOST=localhost`, which shadowed `FRONTEND_HOST=frontend` because Kubernetes keeps the last one. Envoy routed to itself, the pod was OOMKilled (65Mi) and went into CrashLoopBackOff, and the Service had no endpoints. The load generator saw 87.85% connection refused; downstream services went quiet with 0% errors (symptoms). Fix: `rollout undo --to-revision=3` or remove the duplicate env entry. Diagnosis only, nothing applied. (memorize failed twice: 401.)\nEOF",
  "description": "Save the finding to the lessons inbox after memorize failed"
}
```
<details><summary>result</summary>

```
(Bash completed with no output)
```
</details>

# Diagnosis: astronomy-shop outage since 2026-11-09 23:01 UTC

**Root cause:** `frontend-proxy` (the Envoy edge) is down. Deployment revision 4 added a second `FRONTEND_HOST` env var, `FRONTEND_HOST=localhost`, after the existing `FRONTEND_HOST=frontend`. Kubernetes keeps the last one, so Envoy's frontend route now points at itself on `localhost:8080`. The container is killed for running out of memory about one second after each start, the pod is in CrashLoopBackOff, and the `frontend-proxy` Service has no endpoints. Every user request fails with "connection refused".

## Telemetry evidence
All numbers below come from queries I ran in this session. The fault was injected at 23:01:00 UTC (from `timeline.log`).

**Q1: users are failing. 87.85% of load-generator requests get "connection refused" from the proxy.**
```sql
SELECT multiIf(StatusMessage LIKE '%frontend-proxy%Connection refused%', 'frontend-proxy:8080 connection refused',
               StatusCode = 'Error', 'other error', 'ok') AS outcome,
       count() AS n, round(100*n/sum(n) OVER (), 2) AS pct
FROM otel_traces
WHERE ServiceName = 'load-generator' AND SpanKind = 'Client'
  AND Timestamp >= toDateTime64('2026-11-09 23:01:15', 9, 'UTC') AND Timestamp < now() - INTERVAL 30 SECOND
GROUP BY outcome ORDER BY n DESC
```
| outcome | n | pct |
|---|---|---|
| frontend-proxy:8080 connection refused | 159 | 87.85 |
| ok | 18 | 9.94 |
| other error | 4 | 2.21 |

The 18 OK requests are the load generator's direct calls to `flagd`, which don't go through the proxy. The error text is `Failed to establish a new connection: [Errno 111] Connection refused` on every route: `/api/cart`, `/api/products/*`, `/api/checkout`, `/`.

**Q2: traffic stopped at the edge in the minute of the injection.**
```sql
SELECT toStartOfMinute(Timestamp) AS minute,
  countIf(ServiceName='frontend-proxy' AND SpanKind='Server') AS proxy_server_spans,
  countIf(ServiceName='frontend' AND SpanKind='Server') AS frontend_server_spans,
  countIf(ServiceName='load-generator' AND SpanKind='Client') AS lg_client,
  countIf(ServiceName='load-generator' AND SpanKind='Client' AND StatusCode='Error') AS lg_err
FROM otel_traces WHERE Timestamp >= toDateTime64('2026-11-09 22:55:00', 9, 'UTC')
GROUP BY minute ORDER BY minute
```
| minute | proxy | frontend | load-generator requests | load-generator errors |
|---|---|---|---|---|
| 22:55 – 23:00 | 120–143/min | 232–275/min | 125–147/min | **0** |
| 23:01 | **0** | 2 | 105 | 91 |
| 23:02 | 0 | 0 | 71 | 63 |
| 23:03 | 0 | 0 | 69 | 62 |

A follow-up query found the last `frontend-proxy` span at **23:00:57.424**, from the old pod `frontend-proxy-579d54f6f5-lq9rj`. The last `frontend` span was at 23:01:00.080.

**Q3: no downstream service has errors; they simply stopped getting traffic.** Window: 10 minutes before the injection vs 23:01:15 to now−30 s (130 s). This is the inject-boundary variant of the triage query.

| service (Server spans) | before: spans / error % | after: spans / error % |
|---|---|---|
| frontend-proxy | 1300 / 0.0 | **0** / – |
| frontend | 2508 / 0.0 | **0** / – |
| product-catalog | 1313 / 0.0 | 0 / – |
| cart | 576 / 0.0 | 0 / – |
| checkout, payment, shipping, currency, ad, recommendation, … | normal / 0.0 | 0 / – |
| flagd, image-provider | 448 / 0.0, 60 / 0.0 | 28 / 0.0, 13 / 0.0 (reached without the proxy) |

## Kubernetes evidence (read-only commands)
- **Pod:** `frontend-proxy-7b7cd5fb4-xhb4l` is `0/1 CrashLoopBackOff`, with 5 restarts in 3 minutes.
- **Why it dies:** the last termination was `reason: OOMKilled`, `exitCode: 137`, started 23:03:47 and finished 23:03:48. The memory limit is `65Mi`. Envoy's log ends normally (`all clusters initialized … starting workers`) right before the kill.
- **Endpoints:** `frontend-proxy` has none. `frontend` has 10.244.195.208:8080 and is Running 1/1, so it is healthy.
- **What changed:** `rollout history --revision=3` vs `--revision=4` differ in exactly one line: rev 4 adds `FRONTEND_HOST: localhost`. The good revision (3, ReplicaSet 579d54f6f5) had the same 65Mi limit, so the memory limit is not the cause; the env var is.
- **Timing:** events show deployment `frontend-proxy` scaled up ReplicaSet 7b7cd5fb4 and deleted the good pod 3m9s before I checked, which matches 23:01. ReplicaSet 7b7cd5fb4 also crash-looped 36 minutes earlier, during the 22:23 injection of the same fault.

## Mechanism
1. Revision 4 appends `FRONTEND_HOST=localhost` after `FRONTEND_HOST=frontend`, and Kubernetes keeps the last one.
2. Envoy's frontend route now points at `localhost:8080`, which is Envoy's own listener (`ENVOY_PORT=8080`).
3. Requests loop back into Envoy over and over, the container goes past 65Mi and is OOMKilled within about 1 s of starting.
4. The pod never becomes Ready, so the Service has no endpoints and the load generator gets "connection refused".
5. Nothing reaches `frontend` or anything behind it, so those services fall silent.

**Not verified:** steps 2–3 (Envoy looping into itself and running out of memory that way) are my inference. The env diff, the OOMKill, the ~1 s lifetime and the unchanged limit all point to it, but the crashing proxy emits no spans, so I could not see the loop in telemetry.

**Symptoms, not causes:** `frontend`, `product-catalog`, `cart`, `checkout`, `currency`, `shipping`, `recommendation`, `ad`, `product-reviews`, `email`, `payment`, `quote`. They all show zero traffic and zero errors. Their pods are fine; nothing is reaching them. `accounting` restarted 12 minutes before the injection and is Ready now; it is unrelated background noise.

## Fix I would apply (not applied, this was diagnosis-only)
Remove the shadowing entry with the smallest change, a rollback to revision 3:
```bash
kubectl --context kind-kind -n astronomy-shop rollout undo deploy/frontend-proxy --to-revision=3
kubectl --context kind-kind -n astronomy-shop rollout status deploy/frontend-proxy
date -u   # mitigation timestamp
```
Instead of the rollback, I could remove just the duplicate entry. It is the last item in the env list, index 23:
```bash
kubectl --context kind-kind -n astronomy-shop patch deploy frontend-proxy --type=json \
  -p='[{"op":"test","path":"/spec/template/spec/containers/0/env/23","value":{"name":"FRONTEND_HOST","value":"localhost"}},
       {"op":"remove","path":"/spec/template/spec/containers/0/env/23"}]'
```
The `test` step makes the patch refuse to run if index 23 is not that entry.

**How I would confirm it worked:** wait for at least 5 minutes of traffic after the mitigation timestamp, then re-run Q2 and Q3 against that window.
- `frontend-proxy` server spans back to about 120–140 per minute.
- Load-generator error rate back to about 0%, the pre-injection baseline.
- `frontend` and the downstream services back to their baseline volumes, with the proxy's p95 no more than 1.2 × the ~21 ms baseline.

I tried to save this finding to long-term memory twice and both attempts failed with a 401 (invalid API key). I wrote it to `memory/contexts/lessons-inbox.md` instead.
