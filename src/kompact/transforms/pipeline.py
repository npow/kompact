"""Transform pipeline orchestration.

Runs transforms in layer order:
  Layer 1: Schema Optimizer (tool definitions — TF-IDF selection)
  Layer 2: Content Compressors (TOON, JSON Crusher, Code, Logs)
  Layer 2b: Content Compressor (extractive text compression)
  Layer 3: Observation Masker (history management)
  Layer 4: Cache Aligner (prefix caching)

Each transform is independent and can be disabled via config.
Adaptive scaling adjusts parameters based on total context size.
"""

from __future__ import annotations

from kompact.config import KompactConfig
from kompact.transforms import (
    cache_aligner,
    code_compressor,
    content_compressor,
    json_crusher,
    log_compressor,
    observation_masker,
    schema_optimizer,
    toon,
)
from kompact.types import PipelineResult, Request, TransformResult


def _estimate_total_tokens(request: Request) -> int:
    """Rough token estimate for the full request."""
    total_chars = len(request.system)
    for msg in request.messages:
        for block in msg.content:
            total_chars += len(block.text)
    for tool in request.tools:
        total_chars += len(tool.description) + len(str(tool.input_schema))
    return total_chars // 4


def _adapt_params(config: KompactConfig, tokens: int, n_messages: int) -> None:
    """Adapt compression parameters based on context size.

    Short contexts (<500 tokens): skip content compressor
    Medium (2K-20K): conservative content compression
    Long (20K-100K): balanced compression
    Very long (100K+): aggressive observation masking
    """
    if tokens < 500:
        config.content_compressor.enabled = False
        return

    if tokens < 20_000:
        config.content_compressor.target_ratio = 0.75
        config.observation_masker.keep_last_n = max(5, n_messages // 3)
    elif tokens < 100_000:
        config.content_compressor.target_ratio = 0.60
        config.observation_masker.keep_last_n = max(4, n_messages // 4)
    else:
        config.content_compressor.target_ratio = 0.45
        config.observation_masker.keep_last_n = max(3, n_messages // 5)


def run(request: Request, config: KompactConfig) -> PipelineResult:
    """Run the full transform pipeline on a request."""
    results: list[TransformResult] = []
    total_saved = 0

    # Adaptive scaling
    tokens = _estimate_total_tokens(request)
    n_messages = len(request.messages)
    _adapt_params(config, tokens, n_messages)

    # Layer 1: Schema Optimization (TF-IDF tool selection)
    if config.schema_optimizer.enabled and request.tools:
        result = schema_optimizer.transform(request, config.schema_optimizer)
        results.append(result)
        total_saved += result.tokens_saved

    # Layer 2: Content Compression (order: TOON first, then JSON crusher, code, logs)
    messages = request.messages

    if config.toon.enabled:
        result = toon.transform(messages, config.toon)
        messages = result.messages
        results.append(result)
        total_saved += result.tokens_saved

    if config.json_crusher.enabled:
        result = json_crusher.transform(messages, config.json_crusher)
        messages = result.messages
        results.append(result)
        total_saved += result.tokens_saved

    if config.code_compressor.enabled:
        result = code_compressor.transform(messages, config.code_compressor)
        messages = result.messages
        results.append(result)
        total_saved += result.tokens_saved

    if config.log_compressor.enabled:
        result = log_compressor.transform(messages, config.log_compressor)
        messages = result.messages
        results.append(result)
        total_saved += result.tokens_saved

    # Layer 2b: Extractive content compression (for prose/long text)
    if config.content_compressor.enabled:
        result = content_compressor.transform(messages, config.content_compressor)
        messages = result.messages
        results.append(result)
        total_saved += result.tokens_saved

    # Layer 3: History Management
    if config.observation_masker.enabled:
        result = observation_masker.transform(messages, config.observation_masker)
        messages = result.messages
        results.append(result)
        total_saved += result.tokens_saved

    # Layer 4: Cache Alignment
    if config.cache_aligner.enabled:
        result = cache_aligner.transform(
            messages, config.cache_aligner, system_prompt=request.system
        )
        messages = result.messages
        results.append(result)
        total_saved += result.tokens_saved
        # Update system prompt if it was aligned
        if "aligned_system" in result.details:
            request.system = result.details["aligned_system"]

    request.messages = messages

    return PipelineResult(
        request=request,
        total_tokens_saved=total_saved,
        transform_results=results,
    )
