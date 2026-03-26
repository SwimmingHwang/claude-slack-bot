#!/usr/bin/env python3
"""ClickHouse Traces Log Query Module - Optional integration for the Slack Bot."""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _get_client():
    """Create ClickHouse client from config."""
    import clickhouse_connect
    import config

    return clickhouse_connect.get_client(
        host=config.CLICKHOUSE_HOST,
        port=config.CLICKHOUSE_PORT,
        username=config.CLICKHOUSE_USER,
        password=config.CLICKHOUSE_PASSWORD,
        secure=config.CLICKHOUSE_SECURE
    )


def get_service_names(days=7):
    """List available ServiceName values."""
    client = _get_client()
    query = f"""
    SELECT DISTINCT ServiceName
    FROM default.otel_traces
    WHERE Timestamp >= now() - INTERVAL {days} DAY
      AND ServiceName != ''
    ORDER BY ServiceName
    LIMIT 1000
    """
    result = client.query(query)
    return [row[0] for row in result.result_rows if row[0]]


def query_http_500_errors(service_name, hours=24, limit=50):
    """Query HTTP 500 errors for a service."""
    client = _get_client()

    query = f"""
    SELECT
        Timestamp, SpanName, StatusCode, StatusMessage,
        Duration, TraceId, SpanId, SpanAttributes
    FROM default.otel_traces
    WHERE ServiceName = %(service)s
      AND Timestamp >= now() - INTERVAL {hours} HOUR
      AND has(SpanAttributes.keys, 'http.status_code')
      AND SpanAttributes['http.status_code'] = '500'
    ORDER BY Timestamp DESC
    LIMIT {limit}
    """
    result = client.query(query, parameters={"service": service_name})

    output = []
    output.append(f"\n*{service_name} HTTP 500 Error Log (last {hours}h)*")
    output.append(f"Total: {len(result.result_rows)} entries\n")

    if not result.result_rows:
        output.append("No HTTP 500 errors found!")
        return "\n".join(output)

    for row in result.result_rows:
        timestamp, span_name, status_code, status_message, duration, trace_id, span_id, span_attrs = row
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "N/A"
        duration_ms = duration / 1_000_000 if duration else 0

        output.append(f"x {ts_str} | {span_name}")
        output.append(f"   Status: {status_code}")
        if status_message:
            msg_preview = status_message[:100] + "..." if len(status_message) > 100 else status_message
            output.append(f"   Message: {msg_preview}")
        output.append(f"   Duration: {duration_ms:.2f}ms")
        output.append(f"   TraceId: {trace_id}")

        if span_attrs:
            http_method = span_attrs.get('http.method', '')
            http_path = span_attrs.get('http.target', '') or span_attrs.get('http.url', '')
            if http_method or http_path:
                output.append(f"   Request: {http_method} {http_path}")
        output.append("")

    # Error summary
    summary_query = f"""
    SELECT SpanName, count() as error_count
    FROM default.otel_traces
    WHERE ServiceName = %(service)s
      AND Timestamp >= now() - INTERVAL {hours} HOUR
      AND has(SpanAttributes.keys, 'http.status_code')
      AND SpanAttributes['http.status_code'] = '500'
    GROUP BY SpanName
    ORDER BY error_count DESC
    LIMIT 20
    """
    summary_result = client.query(summary_query, parameters={"service": service_name})

    output.append("\n*HTTP 500 Error Summary by Type*")
    for row in summary_result.result_rows:
        span_name, count = row
        output.append(f"- {span_name}: {count}")

    return "\n".join(output)


def query_slow_requests(service_name, hours=24, threshold_ms=1000, limit=50):
    """Query slow requests for a service."""
    client = _get_client()
    threshold_ns = threshold_ms * 1_000_000

    query = f"""
    SELECT Timestamp, SpanName, Duration, TraceId, SpanAttributes
    FROM default.otel_traces
    WHERE ServiceName = %(service)s
      AND Timestamp >= now() - INTERVAL {hours} HOUR
      AND Duration > {threshold_ns}
    ORDER BY Duration DESC
    LIMIT {limit}
    """
    result = client.query(query, parameters={"service": service_name})

    output = []
    output.append(f"\n*{service_name} Slow Requests (>{threshold_ms}ms, last {hours}h)*")
    output.append(f"Total: {len(result.result_rows)} entries\n")

    for row in result.result_rows:
        timestamp, span_name, duration, trace_id, span_attrs = row
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "N/A"
        duration_ms = duration / 1_000_000 if duration else 0

        output.append(f"  {ts_str} | {span_name}")
        output.append(f"   Duration: {duration_ms:.2f}ms")
        output.append(f"   TraceId: {trace_id}")

        if span_attrs:
            http_method = span_attrs.get('http.method', '')
            http_path = span_attrs.get('http.target', '') or span_attrs.get('http.url', '')
            if http_method or http_path:
                output.append(f"   Request: {http_method} {http_path}")
        output.append("")

    return "\n".join(output)


def query_trace_by_id(trace_id, limit=100):
    """Query all spans for a trace ID."""
    client = _get_client()

    query = f"""
    SELECT
        Timestamp, ServiceName, SpanName, SpanKind,
        StatusCode, StatusMessage, Duration, ParentSpanId, SpanId
    FROM default.otel_traces
    WHERE TraceId = %(trace_id)s
    ORDER BY Timestamp ASC
    LIMIT {limit}
    """
    result = client.query(query, parameters={"trace_id": trace_id})

    output = []
    output.append(f"\n*TraceId: {trace_id}*")
    output.append(f"Total: {len(result.result_rows)} spans\n")

    for row in result.result_rows:
        timestamp, service_name, span_name, span_kind, status_code, status_message, duration, parent_id, span_id = row
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "N/A"
        duration_ms = duration / 1_000_000 if duration else 0
        indent = "  " if parent_id else ""
        status_icon = "x" if status_code == "STATUS_CODE_ERROR" else "ok"

        output.append(f"{indent}[{status_icon}] {ts_str} | {service_name} | {span_name}")
        output.append(f"{indent}   Kind: {span_kind}, Duration: {duration_ms:.2f}ms")
        if status_message:
            msg_preview = status_message[:80] + "..." if len(status_message) > 80 else status_message
            output.append(f"{indent}   Message: {msg_preview}")
        output.append("")

    return "\n".join(output)


def query_service_stats(service_name, hours=24):
    """Query service statistics."""
    client = _get_client()

    total = client.query(f"""
        SELECT count() FROM default.otel_traces
        WHERE ServiceName = %(service)s AND Timestamp >= now() - INTERVAL {hours} HOUR
    """, parameters={"service": service_name}).result_rows[0][0]

    errors = client.query(f"""
        SELECT count() FROM default.otel_traces
        WHERE ServiceName = %(service)s AND Timestamp >= now() - INTERVAL {hours} HOUR
          AND StatusCode = 'STATUS_CODE_ERROR'
    """, parameters={"service": service_name}).result_rows[0][0]

    http_500 = client.query(f"""
        SELECT count() FROM default.otel_traces
        WHERE ServiceName = %(service)s AND Timestamp >= now() - INTERVAL {hours} HOUR
          AND has(SpanAttributes.keys, 'http.status_code')
          AND SpanAttributes['http.status_code'] = '500'
    """, parameters={"service": service_name}).result_rows[0][0]

    avg_dur = client.query(f"""
        SELECT avg(Duration) FROM default.otel_traces
        WHERE ServiceName = %(service)s AND Timestamp >= now() - INTERVAL {hours} HOUR
          AND Duration > 0
    """, parameters={"service": service_name}).result_rows[0][0]
    avg_ms = avg_dur / 1_000_000 if avg_dur else 0

    p95_dur = client.query(f"""
        SELECT quantile(0.95)(Duration) FROM default.otel_traces
        WHERE ServiceName = %(service)s AND Timestamp >= now() - INTERVAL {hours} HOUR
          AND Duration > 0
    """, parameters={"service": service_name}).result_rows[0][0]
    p95_ms = p95_dur / 1_000_000 if p95_dur else 0

    output = []
    output.append(f"\n*{service_name} Stats (last {hours}h)*")
    output.append(f"- Total requests: {total:,}")
    output.append(f"- Errors (StatusCode=Error): {errors:,}")
    output.append(f"- HTTP 500: {http_500:,}")
    output.append(f"- Avg response time: {avg_ms:.2f}ms")
    output.append(f"- P95 response time: {p95_ms:.2f}ms")

    return "\n".join(output)


# CLI
if __name__ == "__main__":
    import sys
    # Load config from .env when running standalone
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    import config

    if len(sys.argv) < 2:
        print("Usage: python query_clickhouse.py <command> [args]")
        print("Commands:")
        print("  services              - List service names")
        print("  500 <service> [hours] - HTTP 500 errors")
        print("  slow <service> [hours] [threshold_ms] - Slow requests")
        print("  trace <trace_id>      - Trace by ID")
        print("  stats <service> [hours] - Service stats")
        sys.exit(1)

    cmd = sys.argv[1]
    default_svc = config.CLICKHOUSE_DEFAULT_SERVICE or "my-service"

    if cmd == "services":
        for s in get_service_names():
            print(f"- {s}")
    elif cmd == "500":
        svc = sys.argv[2] if len(sys.argv) > 2 else default_svc
        hrs = int(sys.argv[3]) if len(sys.argv) > 3 else 24
        print(query_http_500_errors(svc, hrs))
    elif cmd == "slow":
        svc = sys.argv[2] if len(sys.argv) > 2 else default_svc
        hrs = int(sys.argv[3]) if len(sys.argv) > 3 else 24
        thr = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
        print(query_slow_requests(svc, hrs, thr))
    elif cmd == "trace":
        print(query_trace_by_id(sys.argv[2]))
    elif cmd == "stats":
        svc = sys.argv[2] if len(sys.argv) > 2 else default_svc
        hrs = int(sys.argv[3]) if len(sys.argv) > 3 else 24
        print(query_service_stats(svc, hrs))
