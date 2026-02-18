"""System implementations for context-bench integration.

Six systems wrapping compression approaches:
  1. NoCompression — pass-through baseline
  2. JSONMinification — re-serialize JSON compactly
  3. Truncation — keep first 50% of context
  4. HeadroomSystem — real headroom-ai SmartCrusher
  5. LLMLinguaSystem — real LLMLingua-2 compression
  6. KompactPipelineSystem — full kompact transform pipeline
"""

from __future__ import annotations

from typing import Any

from .baselines import (
    _extract_all_text,
    _get_headroom,
    _get_llmlingua,
    _minify_json_in_text,
    build_messages,
    count_tokens,
)


class NoCompression:
    """Pass-through baseline — no transformation."""

    @property
    def name(self) -> str:
        return "No Compression"

    def process(self, example: dict[str, Any]) -> dict[str, Any]:
        return dict(example)


class JSONMinification:
    """Minify JSON content in context."""

    @property
    def name(self) -> str:
        return "JSON Minification"

    def process(self, example: dict[str, Any]) -> dict[str, Any]:
        context = example.get("context", "")
        return {**example, "context": _minify_json_in_text(context)}


class Truncation:
    """Keep first 50% of context."""

    @property
    def name(self) -> str:
        return "Truncation (50%)"

    def process(self, example: dict[str, Any]) -> dict[str, Any]:
        context = example.get("context", "")
        half = len(context) // 2
        return {**example, "context": context[:half]}


class HeadroomSystem:
    """Real Headroom compression (headroom-ai SmartCrusher)."""

    @property
    def name(self) -> str:
        return "Headroom"

    def process(self, example: dict[str, Any]) -> dict[str, Any]:
        context = example.get("context", "")
        query = example.get("question", "")[:200]

        try:
            smart_crusher = _get_headroom()
            if count_tokens(context) < 200:
                return dict(example)
            result = smart_crusher.crush(context, query=query)
            compressed = result.compressed if result.was_modified else context
        except Exception:
            compressed = context

        return {**example, "context": compressed}


class LLMLinguaSystem:
    """Real LLMLingua-2 compression."""

    @property
    def name(self) -> str:
        return "LLMLingua-2"

    def process(self, example: dict[str, Any]) -> dict[str, Any]:
        context = example.get("context", "")

        try:
            compressor = _get_llmlingua()
            if len(context) > 50:
                result = compressor.compress_prompt(
                    context,
                    rate=0.5,
                    force_tokens=["\n", "?", ".", "!", ":", "{", "}", "[", "]"],
                )
                compressed = result["compressed_prompt"]
            else:
                compressed = context
        except Exception:
            compressed = context

        return {**example, "context": compressed}


class KompactPipelineSystem:
    """Full Kompact transform pipeline."""

    @property
    def name(self) -> str:
        return "Kompact Pipeline"

    def process(self, example: dict[str, Any]) -> dict[str, Any]:
        from kompact.config import KompactConfig
        from kompact.transforms.pipeline import run as kompact_run
        from kompact.types import Provider, Request

        messages = build_messages(example)
        request = Request(
            provider=Provider.ANTHROPIC,
            messages=messages,
            model="benchmark",
        )
        config = KompactConfig()
        result = kompact_run(request, config)
        compressed = _extract_all_text(result.request.messages)
        return {**example, "context": compressed}


ALL_SYSTEMS = [
    NoCompression(),
    JSONMinification(),
    Truncation(),
    HeadroomSystem(),
    LLMLinguaSystem(),
    KompactPipelineSystem(),
]
