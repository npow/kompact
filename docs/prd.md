# Product Requirements Document — Kompact

## Problem

LLM agents waste 40-80% of context tokens on:
- **JSON array verbosity**: Repeated keys in tool outputs (e.g., 100 search results each repeating `{"title":, "url":, "description":}`)
- **Stale tool outputs**: Old tool results still in context but never referenced again
- **Tool schema bloat**: Sending all tool definitions when only 2-3 are relevant
- **Cache misalignment**: Dynamic content (timestamps, UUIDs) preventing provider prefix caching
- **Verbose code/logs**: Full file contents and log dumps when summaries suffice

This waste increases cost, reduces effective context, and can degrade accuracy (needle-in-haystack problem).

## Solution

Kompact is a transparent HTTP proxy that intercepts LLM API requests and applies multi-layer optimizations before forwarding to the provider. No agent code changes required — just change the base URL.

## Target Users

1. **LLM agent developers** (Claude Code, Cursor, custom agents) who want to reduce costs
2. **Enterprise teams** running high-volume agentic workloads
3. **Researchers** benchmarking context optimization techniques

## Requirements

### Functional

1. **Proxy**: Accept Anthropic and OpenAI API format requests, forward to real provider
2. **TOON Transform**: Convert JSON arrays to tabular notation (30-60% savings)
3. **Observation Masking**: Replace old tool outputs with placeholders (50% savings)
4. **Cache Alignment**: Normalize dynamic content for prefix caching
5. **JSON Crushing**: Statistical compression of structured data
6. **Schema Optimization**: Dynamic tool selection based on conversation context
7. **Code Compression**: AST-based skeleton extraction
8. **Log Compression**: Deduplicate repetitive log patterns
9. **Metrics**: Track tokens saved per transform, per request, cumulative
10. **Dashboard**: Web UI showing compression stats

### Non-Functional

1. **Latency**: < 50ms added per request for non-ML transforms
2. **Accuracy**: Zero information loss for NIAH-critical items
3. **Transparency**: All optimizations reversible, original content retrievable
4. **Compatibility**: Support Anthropic Messages API and OpenAI Chat Completions API

## Success Metrics

- **Compression ratio**: < 0.5 (50%+ reduction) on typical agentic workloads
- **Cost of pass**: Lower cost-per-correct-answer on GAIA benchmark
- **Accuracy preservation**: No regression on NIAH or QA benchmarks
- **Adoption**: Drop-in setup in < 5 minutes

## Non-Goals (v0.1)

- Response optimization (only request-side)
- Streaming response modification
- Multi-turn conversation rewriting
- Provider-specific prompt optimization
