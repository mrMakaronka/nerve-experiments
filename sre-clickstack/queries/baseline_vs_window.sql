-- Baseline vs current window, per service (server spans).
-- baseline = [t-30m, t-15m), current = [t-5m, now). For incident verification
-- replace with: baseline = 15 min before inject_done, current = last 5 min
-- starting no earlier than the mitigation timestamp (see evidence/timeline.log).
WITH
    now() - INTERVAL 30 MINUTE AS b_start,
    now() - INTERVAL 15 MINUTE AS b_end,
    now() - INTERVAL 5 MINUTE  AS c_start,
    now()                      AS c_end
SELECT
    ServiceName,
    countIf(Timestamp >= b_start AND Timestamp < b_end)                                            AS base_spans,
    round(100 * countIf(Timestamp >= b_start AND Timestamp < b_end AND StatusCode = 'Error')
          / greatest(base_spans, 1), 2)                                                            AS base_error_pct,
    round(quantileIf(0.95)(Duration, Timestamp >= b_start AND Timestamp < b_end) / 1e6, 1)         AS base_p95_ms,
    countIf(Timestamp >= c_start AND Timestamp < c_end)                                            AS cur_spans,
    round(100 * countIf(Timestamp >= c_start AND Timestamp < c_end AND StatusCode = 'Error')
          / greatest(cur_spans, 1), 2)                                                             AS cur_error_pct,
    round(quantileIf(0.95)(Duration, Timestamp >= c_start AND Timestamp < c_end) / 1e6, 1)         AS cur_p95_ms
FROM otel_traces
WHERE SpanKind = 'Server'
  AND Timestamp >= b_start
GROUP BY ServiceName
ORDER BY cur_error_pct DESC, base_spans DESC;
