---
name: ClickStack Schema (traces/logs/metrics in ClickHouse)
description: >
  How astronomy-shop telemetry is stored in the ClickStack ClickHouse and how to
  query it correctly with the `clickhouse` MCP tools: tables, columns, enum
  values, units, error-rate and p95 recipes, baseline-vs-window comparison.
  Use before writing any SQL against otel_traces / otel_logs / otel_metrics_*.
version: 1.0.0
context: domain
---

# ClickStack schema

Access: `clickhouse` MCP server → `run_query(query)`; read-only user,
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
  feature-flag noise produce a few % errors on `frontend`/`frontend-proxy` at baseline.
  Compare to a baseline window, never to 0.
- Time literals: `toDateTime64('2026-11-09 22:40:00', 9, 'UTC')`.

## Saved queries (also in the demo repo: `sre-clickstack/queries/*.sql`)

### Error rate per service (window)
```sql
SELECT ServiceName, count() AS spans, countIf(StatusCode = 'Error') AS errors,
       round(100 * errors / greatest(spans, 1), 2) AS error_pct
FROM otel_traces
WHERE SpanKind = 'Server'
  AND Timestamp >= now() - INTERVAL 5 MINUTE AND Timestamp < now()
GROUP BY ServiceName ORDER BY error_pct DESC, spans DESC
```

### p95 latency per service / span
```sql
SELECT ServiceName, SpanName, count() AS spans,
       round(quantile(0.50)(Duration) / 1e6, 1) AS p50_ms,
       round(quantile(0.95)(Duration) / 1e6, 1) AS p95_ms
FROM otel_traces
WHERE SpanKind = 'Server' AND Timestamp >= now() - INTERVAL 5 MINUTE
GROUP BY ServiceName, SpanName HAVING spans >= 5
ORDER BY ServiceName, spans DESC
```

### Baseline vs current window (verification)
```sql
WITH toDateTime64('<baseline_start>', 9, 'UTC') AS b_start,
     toDateTime64('<baseline_end>',   9, 'UTC') AS b_end,      -- e.g. inject time
     greatest(now() - INTERVAL 5 MINUTE, toDateTime64('<mitigation_ts>', 9, 'UTC')) AS c_start,
     now() AS c_end
SELECT ServiceName,
  countIf(Timestamp >= b_start AND Timestamp < b_end) AS base_spans,
  round(100 * countIf(Timestamp >= b_start AND Timestamp < b_end AND StatusCode = 'Error') / greatest(base_spans, 1), 2) AS base_error_pct,
  round(quantileIf(0.95)(Duration, Timestamp >= b_start AND Timestamp < b_end) / 1e6, 1) AS base_p95_ms,
  countIf(Timestamp >= c_start AND Timestamp < c_end) AS cur_spans,
  round(100 * countIf(Timestamp >= c_start AND Timestamp < c_end AND StatusCode = 'Error') / greatest(cur_spans, 1), 2) AS cur_error_pct,
  round(quantileIf(0.95)(Duration, Timestamp >= c_start AND Timestamp < c_end) / 1e6, 1) AS cur_p95_ms,
  dateDiff('second', c_start, c_end) AS cur_window_s
FROM otel_traces
WHERE SpanKind = 'Server' AND Timestamp >= b_start
GROUP BY ServiceName ORDER BY cur_error_pct DESC, base_spans DESC
```
Report `cur_window_s` — a verification window shorter than 300 s is not a valid
5-minute window.

### Error breakdown for one service
```sql
SELECT SpanName, SpanAttributes['http.status_code'] AS http_status,
       SpanAttributes['response_flags'] AS flags, SpanAttributes['upstream_cluster'] AS upstream,
       StatusMessage, count() AS n
FROM otel_traces
WHERE ServiceName = 'frontend-proxy' AND SpanKind = 'Server'
  AND Timestamp >= now() - INTERVAL 10 MINUTE AND StatusCode = 'Error'
GROUP BY ALL ORDER BY n DESC LIMIT 20
```
