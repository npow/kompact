"""OpenTelemetry integration for Kompact.

Provides traces and metrics for the compression pipeline. Enabled by default,
disable with --no-otel.

Metrics: exported via Prometheus endpoint on :9464/metrics.
Traces: exported via OTLP to localhost:4317 (override with OTEL_EXPORTER_OTLP_ENDPOINT).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram, Meter
    from opentelemetry.trace import Tracer

logger = logging.getLogger("kompact")

_tracer: Tracer | None = None
_meter: Meter | None = None

# Metrics instruments
_request_counter: Counter | None = None
_tokens_saved_counter: Counter | None = None
_tokens_processed_counter: Counter | None = None
_compression_ratio_histogram: Histogram | None = None
_pipeline_latency_histogram: Histogram | None = None
_transform_latency_histogram: Histogram | None = None
_transform_tokens_saved_counter: Counter | None = None
_upstream_latency_histogram: Histogram | None = None


def init(service_name: str = "kompact", prometheus_port: int = 9464) -> None:
    """Initialize OpenTelemetry tracing and metrics."""
    global _tracer, _meter
    global _request_counter, _tokens_saved_counter, _tokens_processed_counter
    global _compression_ratio_histogram, _pipeline_latency_histogram
    global _transform_latency_histogram, _transform_tokens_saved_counter
    global _upstream_latency_histogram

    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from prometheus_client import start_http_server

    resource = Resource.create({"service.name": service_name})

    # Traces — OTLP export (to Jaeger/Tempo/etc if available)
    tracer_provider = TracerProvider(resource=resource)
    try:
        import socket

        otel_host = "localhost"
        otel_port = 4317
        # Quick check if the OTLP endpoint is reachable before registering
        sock = socket.create_connection((otel_host, otel_port), timeout=0.5)
        sock.close()
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        logger.info("OTLP trace exporter connected to %s:%d", otel_host, otel_port)
    except (OSError, Exception):
        logger.debug("OTLP endpoint not reachable, trace export disabled")
    trace.set_tracer_provider(tracer_provider)
    _tracer = trace.get_tracer("kompact")

    # Metrics — Prometheus exporter (scraped by Prometheus on :9464/metrics)
    prometheus_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(resource=resource, metric_readers=[prometheus_reader])
    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter("kompact")

    # Start Prometheus HTTP server
    start_http_server(prometheus_port)
    logger.info("Prometheus metrics at http://0.0.0.0:%d/metrics", prometheus_port)

    # Create instruments
    _request_counter = _meter.create_counter(
        "kompact.requests",
        description="Total proxy requests",
    )
    _tokens_saved_counter = _meter.create_counter(
        "kompact.tokens.saved",
        description="Total tokens saved by compression",
    )
    _tokens_processed_counter = _meter.create_counter(
        "kompact.tokens.processed",
        description="Total input tokens processed",
    )
    _compression_ratio_histogram = _meter.create_histogram(
        "kompact.compression.ratio",
        description="Compression ratio per request (lower = more savings)",
    )
    _pipeline_latency_histogram = _meter.create_histogram(
        "kompact.pipeline.latency_ms",
        description="Pipeline processing latency in milliseconds",
    )
    _transform_latency_histogram = _meter.create_histogram(
        "kompact.transform.latency_ms",
        description="Per-transform latency in milliseconds",
    )
    _transform_tokens_saved_counter = _meter.create_counter(
        "kompact.transform.tokens_saved",
        description="Tokens saved per transform",
    )
    _upstream_latency_histogram = _meter.create_histogram(
        "kompact.upstream.latency_ms",
        description="Upstream provider response latency in milliseconds",
    )

    logger.info("OpenTelemetry initialized (OTLP export enabled)")


def get_tracer() -> Tracer | None:
    return _tracer


def record_request(
    *,
    provider: str,
    model: str,
    tokens_before: int,
    tokens_saved: int,
    compression_ratio: float,
    pipeline_latency_ms: float,
    upstream_latency_ms: float | None = None,
) -> None:
    """Record metrics for a completed request."""
    if _request_counter is None:
        return

    attrs = {"provider": provider, "model": model}

    _request_counter.add(1, attrs)
    _tokens_saved_counter.add(tokens_saved, attrs)
    _tokens_processed_counter.add(tokens_before, attrs)
    _compression_ratio_histogram.record(compression_ratio, attrs)
    _pipeline_latency_histogram.record(pipeline_latency_ms, attrs)

    if upstream_latency_ms is not None and _upstream_latency_histogram is not None:
        _upstream_latency_histogram.record(upstream_latency_ms, attrs)


def record_transform(*, name: str, tokens_saved: int, latency_ms: float) -> None:
    """Record metrics for a single transform execution."""
    if _transform_tokens_saved_counter is None:
        return

    attrs = {"transform": name}
    _transform_tokens_saved_counter.add(tokens_saved, attrs)
    _transform_latency_histogram.record(latency_ms, attrs)
