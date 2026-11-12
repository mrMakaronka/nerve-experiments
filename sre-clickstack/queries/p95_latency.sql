-- p95 / p50 server-span latency per service and span name over a window.
-- Duration is in NANOSECONDS (UInt64) -> divide by 1e6 for ms.
SELECT
    ServiceName,
    SpanName,
    count()                                    AS spans,
    round(quantile(0.50)(Duration) / 1e6, 1)   AS p50_ms,
    round(quantile(0.95)(Duration) / 1e6, 1)   AS p95_ms
FROM otel_traces
WHERE SpanKind = 'Server'
  AND Timestamp >= now() - INTERVAL 5 MINUTE
GROUP BY ServiceName, SpanName
HAVING spans >= 5
ORDER BY ServiceName, spans DESC;
