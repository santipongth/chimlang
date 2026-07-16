"""PII-safe traces, Prometheus metrics, and provider-health persistence."""

from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import urlsplit

from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from core.db import connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_call_events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    operation TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    error_kind TEXT NOT NULL DEFAULT '',
    model_version TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS provider_call_events_ts ON provider_call_events (ts DESC);
CREATE INDEX IF NOT EXISTS provider_call_events_provider
    ON provider_call_events (provider, ts DESC);
"""

LLM_CALLS = Counter(
    "chimlang_provider_calls_total",
    "Provider calls without prompts or response bodies",
    ("provider", "operation", "tier", "status", "error_kind"),
)
LLM_LATENCY = Histogram(
    "chimlang_provider_call_seconds",
    "Provider call latency",
    ("provider", "operation", "tier"),
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
RETRIEVAL_QUERIES = Counter(
    "chimlang_retrieval_queries_total",
    "Retrieval requests by requested and effective mode",
    ("requested_mode", "effective_mode", "status"),
)
QUEUE_LATENCY = Histogram(
    "chimlang_queue_latency_seconds",
    "Time between queued and worker start",
    ("engine",),
    buckets=(0.1, 0.5, 1, 2, 5, 15, 30, 60, 300, 900),
)
RUN_FAILURES = Counter(
    "chimlang_run_failures_total", "Run failures by safe taxonomy", ("engine", "reason")
)

_configured = False


def configure_telemetry(service_name: str, endpoint: str = "") -> None:
    """Configure one process-wide tracer provider; blank endpoint keeps local spans."""

    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    if endpoint.strip():
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.strip())))
    trace.set_tracer_provider(provider)
    _configured = True


@contextmanager
def traced(name: str, **attributes):
    safe = {
        key: value
        for key, value in attributes.items()
        if value is not None and isinstance(value, (str, bool, int, float))
    }
    with trace.get_tracer("chimlang").start_as_current_span(name, attributes=safe) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc, attributes={"exception.message": type(exc).__name__})
            raise


def inject_trace_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    propagate.inject(headers)
    return headers


@contextmanager
def extracted_trace(headers: dict | None):
    token = otel_context.attach(propagate.extract(headers or {}))
    try:
        yield
    finally:
        otel_context.detach(token)


def provider_name(base_url: str) -> str:
    try:
        return urlsplit(base_url).hostname or "local"
    except ValueError:
        return "custom"


def record_provider_call(
    dsn: str,
    *,
    run_id: str,
    provider: str,
    operation: str,
    tier: str,
    status: str,
    latency_s: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0,
    error_kind: str = "",
    model_version: str = "",
) -> None:
    safe_error = error_kind[:80]
    LLM_CALLS.labels(provider, operation, tier, status, safe_error).inc()
    LLM_LATENCY.labels(provider, operation, tier).observe(max(0.0, latency_s))
    try:
        with connection(dsn) as conn:
            conn.execute(
                "INSERT INTO provider_call_events "
                "(run_id, provider, operation, tier, status, latency_ms, input_tokens, "
                "output_tokens, cost_usd, error_kind, model_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id[:160],
                    provider[:160],
                    operation[:40],
                    tier[:40],
                    status[:40],
                    round(max(0.0, latency_s) * 1000, 3),
                    max(0, input_tokens),
                    max(0, output_tokens),
                    max(0.0, cost_usd),
                    safe_error,
                    model_version[:240],
                ),
            )
    except Exception:
        pass  # Telemetry must not change simulation results or retry provider calls.


def observe_retrieval(requested: str, effective: str, status: str) -> None:
    RETRIEVAL_QUERIES.labels(requested[:20], effective[:40], status[:40]).inc()


def prometheus_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def provider_health(dsn: str, *, hours: int = 24) -> dict:
    """Aggregate only operational metadata; prompts and response text are never stored."""

    with connection(dsn) as conn:
        providers = conn.execute(
            "SELECT provider, operation, count(*), "
            "count(*) FILTER (WHERE status = 'success'), "
            "round(avg(latency_ms)::numeric, 1), "
            "round(sum(cost_usd)::numeric, 6), max(ts) "
            "FROM provider_call_events WHERE ts >= now() - (%s * interval '1 hour') "
            "GROUP BY provider, operation ORDER BY provider, operation",
            (max(1, min(24 * 30, hours)),),
        ).fetchall()
        failures = conn.execute(
            "SELECT error_kind, count(*) FROM provider_call_events "
            "WHERE ts >= now() - (%s * interval '1 hour') AND status <> 'success' "
            "GROUP BY error_kind ORDER BY count(*) DESC LIMIT 12",
            (max(1, min(24 * 30, hours)),),
        ).fetchall()
        queue = conn.execute(
            "SELECT count(*) FILTER (WHERE status = 'queued'), "
            "count(*) FILTER (WHERE status = 'running'), "
            "count(*) FILTER (WHERE status = 'error'), "
            "round(avg(extract(epoch FROM (started_at - queued_at))) "
            "FILTER (WHERE started_at IS NOT NULL)::numeric, 2) FROM sim_runs "
            "WHERE created_at >= now() - (%s * interval '1 hour')",
            (max(1, min(24 * 30, hours)),),
        ).fetchone()
    return {
        "window_hours": max(1, min(24 * 30, hours)),
        "providers": [
            {
                "provider": row[0],
                "operation": row[1],
                "calls": row[2],
                "successes": row[3],
                "success_rate": round(row[3] / row[2], 4) if row[2] else 0,
                "avg_latency_ms": float(row[4] or 0),
                "cost_usd": float(row[5] or 0),
                "last_call_at": row[6].isoformat() if row[6] else None,
            }
            for row in providers
        ],
        "failure_taxonomy": [{"reason": row[0] or "unknown", "count": row[1]} for row in failures],
        "queue": {
            "queued": queue[0],
            "running": queue[1],
            "errors": queue[2],
            "avg_latency_seconds": float(queue[3] or 0),
        },
        "pii_policy": "metadata_only_no_prompt_or_response",
    }
