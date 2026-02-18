"""Metrics tracking for Kompact proxy.

Tracks per-request and cumulative metrics:
- Tokens before/after per transform
- Compression ratio
- Transform latencies
- Request counts
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from kompact.types import PipelineResult


@dataclass
class RequestMetrics:
    """Metrics for a single request."""

    timestamp: float
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    compression_ratio: float
    transform_details: list[dict[str, Any]]
    latency_ms: float
    model: str = ""
    provider: str = ""


@dataclass
class MetricsTracker:
    """Tracks compression metrics across requests."""

    _requests: list[RequestMetrics] = field(default_factory=list)
    _max_history: int = 10000

    def record(
        self,
        pipeline_result: PipelineResult,
        tokens_before: int,
        latency_ms: float,
    ) -> RequestMetrics:
        """Record metrics from a pipeline run."""
        tokens_after = tokens_before - pipeline_result.total_tokens_saved

        metrics = RequestMetrics(
            timestamp=time.time(),
            tokens_before=tokens_before,
            tokens_after=max(0, tokens_after),
            tokens_saved=pipeline_result.total_tokens_saved,
            compression_ratio=(
                tokens_after / tokens_before if tokens_before > 0 else 1.0
            ),
            transform_details=[
                {
                    "name": r.transform_name,
                    "tokens_saved": r.tokens_saved,
                    **r.details,
                }
                for r in pipeline_result.transform_results
            ],
            latency_ms=latency_ms,
            model=pipeline_result.request.model,
            provider=pipeline_result.request.provider.value,
        )

        self._requests.append(metrics)
        if len(self._requests) > self._max_history:
            self._requests = self._requests[-self._max_history:]

        return metrics

    @property
    def summary(self) -> dict[str, Any]:
        """Get cumulative summary metrics."""
        if not self._requests:
            return {
                "total_requests": 0,
                "total_tokens_saved": 0,
                "total_tokens_processed": 0,
                "average_compression_ratio": 1.0,
                "average_latency_ms": 0.0,
                "transforms": {},
            }

        total_saved = sum(r.tokens_saved for r in self._requests)
        total_before = sum(r.tokens_before for r in self._requests)
        total_after = sum(r.tokens_after for r in self._requests)

        # Per-transform breakdown
        transform_stats: dict[str, dict[str, Any]] = {}
        for req in self._requests:
            for td in req.transform_details:
                name = td["name"]
                if name not in transform_stats:
                    transform_stats[name] = {"tokens_saved": 0, "invocations": 0}
                transform_stats[name]["tokens_saved"] += td.get("tokens_saved", 0)
                transform_stats[name]["invocations"] += 1

        return {
            "total_requests": len(self._requests),
            "total_tokens_saved": total_saved,
            "total_tokens_processed": total_before,
            "total_tokens_output": total_after,
            "average_compression_ratio": (
                total_after / total_before if total_before > 0 else 1.0
            ),
            "average_latency_ms": (
                sum(r.latency_ms for r in self._requests) / len(self._requests)
            ),
            "transforms": transform_stats,
        }

    @property
    def recent(self) -> list[dict[str, Any]]:
        """Get the last 20 request metrics."""
        return [
            {
                "timestamp": r.timestamp,
                "tokens_before": r.tokens_before,
                "tokens_after": r.tokens_after,
                "tokens_saved": r.tokens_saved,
                "compression_ratio": round(r.compression_ratio, 3),
                "latency_ms": round(r.latency_ms, 1),
                "model": r.model,
                "provider": r.provider,
                "transforms": r.transform_details,
            }
            for r in self._requests[-20:]
        ]

    def reset(self) -> None:
        """Clear all recorded metrics."""
        self._requests.clear()
