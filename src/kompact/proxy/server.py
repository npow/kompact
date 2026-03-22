"""FastAPI proxy server for Kompact.

Intercepts LLM API requests, runs the transform pipeline, and forwards
optimized requests to the upstream provider.

Routes:
  POST /v1/messages         — Anthropic Messages API
  POST /v1/chat/completions — OpenAI Chat Completions API
  GET  /dashboard           — Metrics dashboard
  GET  /health              — Health check
"""

from __future__ import annotations

import copy
import json
import logging
import time
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from kompact.cache.store import CompressionStore
from kompact.config import KompactConfig
from kompact.metrics.telemetry import get_tracer, record_request, record_transform
from kompact.metrics.tracker import MetricsTracker
from kompact.parser.messages import parse_request, serialize_request
from kompact.transforms.pipeline import run as run_pipeline
from kompact.types import Provider

logger = logging.getLogger("kompact")


def create_app(config: KompactConfig | None = None) -> FastAPI:
    """Create the FastAPI application."""
    if config is None:
        config = KompactConfig()

    app = FastAPI(title="Kompact", version="0.1.0")
    tracker = MetricsTracker()
    store = CompressionStore(
        max_entries=config.store.max_entries,
        default_ttl_seconds=config.store.default_ttl_seconds,
        adaptive_ttl=config.store.adaptive_ttl,
    )

    # Store references on app state
    app.state.config = config
    app.state.tracker = tracker
    app.state.store = store

    @app.post("/v1/messages")
    async def anthropic_messages(request: Request) -> Response:
        """Handle Anthropic Messages API requests."""
        body = await request.json()
        response = await _proxy_request(
            request=request,
            body=body,
            provider=Provider.ANTHROPIC,
            upstream_url=f"{config.anthropic_base_url}/v1/messages",
            config=config,
            tracker=tracker,
        )
        # Fallback on 429: retry with alternate model if configured
        if response.status_code == 429 and config.model_fallbacks:
            model = body.get("model", "")
            fallback = config.model_fallbacks.get(model)
            if fallback:
                logger.info("Model %s returned 429, falling back to %s", model, fallback)
                body["model"] = fallback
                response = await _proxy_request(
                    request=request,
                    body=body,
                    provider=Provider.ANTHROPIC,
                    upstream_url=f"{config.anthropic_base_url}/v1/messages",
                    config=config,
                    tracker=tracker,
                )
        return response

    @app.post("/v1/chat/completions")
    async def openai_chat(request: Request) -> Response:
        """Handle OpenAI Chat Completions API requests."""
        body = await request.json()
        return await _proxy_request(
            request=request,
            body=body,
            provider=Provider.OPENAI,
            upstream_url=f"{config.openai_base_url}/v1/chat/completions",
            config=config,
            tracker=tracker,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/dashboard")
    async def dashboard() -> HTMLResponse:
        return HTMLResponse(_render_dashboard(tracker, store))

    @app.get("/api/metrics")
    async def api_metrics() -> JSONResponse:
        return JSONResponse({
            "summary": tracker.summary,
            "recent": tracker.recent,
            "store": store.stats,
        })

    return app


async def _proxy_request(
    request: Request,
    body: dict[str, Any],
    provider: Provider,
    upstream_url: str,
    config: KompactConfig,
    tracker: MetricsTracker,
) -> Response:
    """Process and forward a request to the upstream provider."""
    tracer = get_tracer()
    model = body.get("model", "unknown")

    def _run(span=None):
        """Run pipeline, optionally recording transform spans."""
        nonlocal config
        start = time.monotonic()

        # Per-request transform overrides via X-Kompact-Disable header
        disable_header = request.headers.get("x-kompact-disable", "")
        if disable_header:
            config = copy.deepcopy(config)
            for name in (n.strip() for n in disable_header.split(",")):
                transform_config = getattr(config, name, None)
                if transform_config and hasattr(transform_config, "enabled"):
                    transform_config.enabled = False

        parsed = parse_request(body, provider)
        tokens_before = _estimate_tokens(body)
        pipeline_result = run_pipeline(parsed, config)
        optimized_body = serialize_request(pipeline_result.request)

        pipeline_latency_ms = (time.monotonic() - start) * 1000
        metrics = tracker.record(pipeline_result, tokens_before, pipeline_latency_ms)

        # Record per-transform telemetry
        for tr in pipeline_result.transform_results:
            record_transform(
                name=tr.transform_name,
                tokens_saved=tr.tokens_saved,
                latency_ms=tr.details.get("latency_ms", 0),
            )

        if span is not None:
            span.set_attribute("kompact.provider", provider.value)
            span.set_attribute("kompact.model", model)
            span.set_attribute("kompact.tokens_before", tokens_before)
            span.set_attribute("kompact.tokens_saved", metrics.tokens_saved)
            span.set_attribute("kompact.compression_ratio", metrics.compression_ratio)
            span.set_attribute("kompact.pipeline_latency_ms", pipeline_latency_ms)

        if config.verbose:
            logger.info(
                "Kompact: %d tokens saved (%.1f%% reduction) in %.1fms",
                metrics.tokens_saved,
                (1 - metrics.compression_ratio) * 100,
                metrics.latency_ms,
            )

        return optimized_body, metrics, tokens_before, pipeline_latency_ms

    if tracer is not None:
        with tracer.start_as_current_span(
            "kompact.proxy",
            attributes={"kompact.provider": provider.value, "kompact.model": model},
        ) as span:
            optimized_body, metrics, tokens_before, pipeline_latency_ms = _run(span)
            response = await _forward_upstream(
                request, upstream_url, optimized_body, body, metrics
            )
            record_request(
                provider=provider.value,
                model=model,
                tokens_before=tokens_before,
                tokens_saved=metrics.tokens_saved,
                compression_ratio=metrics.compression_ratio,
                pipeline_latency_ms=pipeline_latency_ms,
            )
            return response
    else:
        optimized_body, metrics, tokens_before, pipeline_latency_ms = _run()
        response = await _forward_upstream(
            request, upstream_url, optimized_body, body, metrics
        )
        record_request(
            provider=provider.value,
            model=model,
            tokens_before=tokens_before,
            tokens_saved=metrics.tokens_saved,
            compression_ratio=metrics.compression_ratio,
            pipeline_latency_ms=pipeline_latency_ms,
        )
        return response


async def _forward_upstream(
    request: Request,
    upstream_url: str,
    optimized_body: dict[str, Any],
    original_body: dict[str, Any],
    metrics: Any,
) -> Response:
    """Forward the optimized request to the upstream provider."""
    forward_headers = {}
    for key in ("authorization", "x-api-key", "anthropic-version",
                "anthropic-beta", "content-type"):
        val = request.headers.get(key)
        if val:
            forward_headers[key] = val

    if "content-type" not in forward_headers:
        forward_headers["content-type"] = "application/json"

    is_streaming = original_body.get("stream", False)

    # Headers that must not be forwarded from upstream — httpx already
    # handles content-encoding (decompresses gzip/deflate), so passing
    # these through would cause clients to try to decompress plain text.
    _hop_headers = frozenset({
        "content-encoding", "transfer-encoding", "content-length", "connection",
    })

    async with httpx.AsyncClient(timeout=300.0) as client:
        if is_streaming:
            upstream_resp = await client.send(
                client.build_request(
                    "POST",
                    upstream_url,
                    json=optimized_body,
                    headers=forward_headers,
                ),
                stream=True,
            )

            async def stream_response():
                async for chunk in upstream_resp.aiter_raw():
                    yield chunk
                await upstream_resp.aclose()

            response_headers = {
                k: v for k, v in upstream_resp.headers.items()
                if k.lower() not in _hop_headers
            }
            response_headers["x-kompact-tokens-saved"] = str(metrics.tokens_saved)
            response_headers["x-kompact-compression-ratio"] = f"{metrics.compression_ratio:.3f}"
            response_headers["x-kompact-latency-ms"] = f"{metrics.latency_ms:.1f}"

            return StreamingResponse(
                stream_response(),
                status_code=upstream_resp.status_code,
                headers=response_headers,
                media_type=upstream_resp.headers.get("content-type", "text/event-stream"),
            )
        else:
            upstream_resp = await client.post(
                upstream_url,
                json=optimized_body,
                headers=forward_headers,
            )

            response_headers = {
                k: v for k, v in upstream_resp.headers.items()
                if k.lower() not in _hop_headers
            }
            response_headers["x-kompact-tokens-saved"] = str(metrics.tokens_saved)
            response_headers["x-kompact-compression-ratio"] = f"{metrics.compression_ratio:.3f}"
            response_headers["x-kompact-latency-ms"] = f"{metrics.latency_ms:.1f}"

            return Response(
                content=upstream_resp.content,
                status_code=upstream_resp.status_code,
                headers=response_headers,
                media_type=upstream_resp.headers.get("content-type"),
            )


def _estimate_tokens(body: dict[str, Any]) -> int:
    """Rough token estimate from request body."""
    raw = json.dumps(body)
    return len(raw) // 4


def _render_dashboard(tracker: MetricsTracker, store: CompressionStore) -> str:
    """Render the metrics dashboard as HTML."""
    summary = tracker.summary
    store_stats = store.stats
    recent = tracker.recent

    recent_rows = ""
    for r in reversed(recent):
        savings_pct = (1 - r["compression_ratio"]) * 100
        recent_rows += f"""
        <tr>
            <td>{r['model']}</td>
            <td>{r['tokens_before']:,}</td>
            <td>{r['tokens_after']:,}</td>
            <td>{r['tokens_saved']:,}</td>
            <td>{savings_pct:.1f}%</td>
            <td>{r['latency_ms']:.1f}ms</td>
        </tr>"""

    transform_rows = ""
    for name, stats in summary.get("transforms", {}).items():
        transform_rows += f"""
        <tr>
            <td>{name}</td>
            <td>{stats['tokens_saved']:,}</td>
            <td>{stats['invocations']:,}</td>
        </tr>"""

    avg_savings = (1 - summary["average_compression_ratio"]) * 100

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Kompact Dashboard</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif;
               margin: 2em; background: #0d1117; color: #c9d1d9; }}
        h1 {{ color: #58a6ff; }}
        h2 {{ color: #8b949e; border-bottom: 1px solid #21262d; padding-bottom: 0.5em; }}
        .stats {{ display: flex; gap: 2em; flex-wrap: wrap; margin: 1em 0; }}
        .stat {{ background: #161b22; padding: 1em 1.5em;
                border-radius: 8px; border: 1px solid #21262d; }}
        .stat .value {{ font-size: 2em; font-weight: bold; color: #58a6ff; }}
        .stat .label {{ color: #8b949e; font-size: 0.9em; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
        th, td {{ padding: 0.6em 1em; text-align: left; border-bottom: 1px solid #21262d; }}
        th {{ color: #8b949e; font-weight: 600; }}
        tr:hover {{ background: #161b22; }}
    </style>
    <meta http-equiv="refresh" content="5">
</head>
<body>
    <h1>Kompact Dashboard</h1>

    <div class="stats">
        <div class="stat">
            <div class="value">{summary['total_requests']:,}</div>
            <div class="label">Total Requests</div>
        </div>
        <div class="stat">
            <div class="value">{summary['total_tokens_saved']:,}</div>
            <div class="label">Total Tokens Saved</div>
        </div>
        <div class="stat">
            <div class="value">{avg_savings:.1f}%</div>
            <div class="label">Avg Savings</div>
        </div>
        <div class="stat">
            <div class="value">{summary['average_latency_ms']:.1f}ms</div>
            <div class="label">Avg Latency</div>
        </div>
        <div class="stat">
            <div class="value">{store_stats['entries']:,}</div>
            <div class="label">Store Entries</div>
        </div>
    </div>

    <h2>Per-Transform Breakdown</h2>
    <table>
        <tr><th>Transform</th><th>Tokens Saved</th><th>Invocations</th></tr>
        {transform_rows}
    </table>

    <h2>Recent Requests</h2>
    <table>
        <tr><th>Model</th><th>Before</th><th>After</th><th>Saved</th><th>Savings</th><th>Latency</th></tr>
        {recent_rows}
    </table>
</body>
</html>"""
