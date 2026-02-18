# AGENTS.md — Kompact Context Optimization Proxy

## What is Kompact?

A transparent proxy that optimizes LLM context through multi-layer transforms.
Sits between agents (Claude Code, Cursor, etc.) and providers (Anthropic, OpenAI).

## Architecture

```
Request → Proxy → [Layer 1: Schema] → [Layer 2: Content] → [Layer 3: History] → [Layer 4: Cache] → Provider
```

## Entry Points

| What | Where | Notes |
|------|-------|-------|
| CLI | `src/kompact/__main__.py` | `kompact proxy --port 7878` |
| Proxy server | `src/kompact/proxy/server.py` | FastAPI, intercepts API requests |
| Transform pipeline | `src/kompact/transforms/pipeline.py` | Orchestrates all transforms |
| Configuration | `src/kompact/config.py` | Pydantic settings |
| Core types | `src/kompact/types.py` | Message, ToolOutput, TransformResult |

## Transforms (each is independent, pure function)

| Transform | File | Layer | Typical Savings |
|-----------|------|-------|-----------------|
| TOON format | `src/kompact/transforms/toon.py` | 2 (Content) | 30-60% on JSON arrays |
| Observation masker | `src/kompact/transforms/observation_masker.py` | 3 (History) | 50% on old tool outputs |
| Cache aligner | `src/kompact/transforms/cache_aligner.py` | 4 (Cache) | Enables provider caching |
| JSON crusher | `src/kompact/transforms/json_crusher.py` | 2 (Content) | 40-80% on structured data |
| Schema optimizer | `src/kompact/transforms/schema_optimizer.py` | 1 (Schema) | 50-90% on tool defs |
| Code compressor | `src/kompact/transforms/code_compressor.py` | 2 (Content) | ~70% on code blocks |
| Log compressor | `src/kompact/transforms/log_compressor.py` | 2 (Content) | 60-90% on log output |

## Key Invariants

1. **All transforms are pure functions**: `list[Message] → TransformResult`
2. **No transform modifies user messages** — only assistant/tool/system content
3. **Every transform tracks `tokens_saved`** via `TransformResult`
4. **Transforms are composable** — pipeline runs them in sequence

## Documentation

| Doc | Path | Purpose |
|-----|------|---------|
| PRD | `docs/prd.md` | Product requirements |
| SDD | `docs/sdd.md` | System design |
| Architecture | `docs/architecture.md` | Layer details |
| Benchmarks | `docs/benchmarks.md` | Evaluation strategy |
| Quality | `docs/quality.md` | Quality grades per domain |
| Research | `docs/research/` | SOTA survey, competitors, economics |

## Testing

```bash
uv run pytest                           # All tests
uv run pytest tests/test_toon.py        # Single transform
uv run python benchmarks/compression_ratio.py  # Benchmarks
```

## Quick Start

```bash
uv sync
uv run kompact proxy --port 7878
# Then: ANTHROPIC_BASE_URL=http://localhost:7878 claude
```
