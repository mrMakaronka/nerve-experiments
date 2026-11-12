-- Server-span error rate per service over a window.
-- Window: replace the two literals (UTC). Default = last 5 minutes.
-- NOTE: in ClickStack's schema SpanKind is 'Server'|'Client'|'Internal' and
--       StatusCode is 'Error'|'Unset'|'Ok' (not the SPAN_KIND_*/STATUS_CODE_* enum names).
SELECT
    ServiceName,
    count()                                             AS spans,
    countIf(StatusCode = 'Error')                       AS errors,
    round(100 * errors / greatest(spans, 1), 2)         AS error_pct
FROM otel_traces
WHERE SpanKind = 'Server'
  AND Timestamp >= now() - INTERVAL 5 MINUTE   -- or: Timestamp >= toDateTime64('2026-11-09 22:40:00', 9, 'UTC')
  AND Timestamp <  now()                        -- or: Timestamp <  toDateTime64('2026-11-09 22:45:00', 9, 'UTC')
GROUP BY ServiceName
ORDER BY error_pct DESC, spans DESC;
