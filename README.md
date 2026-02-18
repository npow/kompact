# Kompact

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-37%20passed-brightgreen.svg)](#development)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Multi-layer context optimization proxy for LLM agents. Reduces token usage by 40-70% with zero information loss.

```
Agent  ──>  Kompact Proxy (localhost:7878)  ──>  LLM Provider
              │
              ├─ Layer 1: Schema Optimizer     (TF-IDF tool selection)
              ├─ Layer 2: Content Compressors   (TOON, JSON, code, logs)
              ├─ Layer 2b: Extractive Compressor (query-aware sentence selection)
              ├─ Layer 3: Observation Masker    (history management)
              └─ Layer 4: Cache Aligner        (prefix cache optimization)
```

## Quick Start

```bash
# Install
uv sync

# Start proxy
uv run kompact proxy --port 7878

# Point your agent at it
export ANTHROPIC_BASE_URL=http://localhost:7878
claude  # or any Anthropic/OpenAI-compatible agent
```

## How It Works

Kompact is a transparent HTTP proxy. No code changes needed — just change your base URL. It intercepts LLM API requests, applies a pipeline of transforms to compress the context, then forwards the optimized request to the provider.

| Transform | Target | Savings | Cost |
|-----------|--------|--------:|------|
| **TOON** | JSON arrays of objects | 30-60% | Zero (string manipulation) |
| **JSON Crusher** | Structured JSON data | 40-80% | Minimal (Counter stats) |
| **Code Compressor** | Code in tool results | ~70% | Regex parse |
| **Log Compressor** | Repetitive log output | 60-90% | Regex dedup |
| **Content Compressor** | Long prose/text | 25-55% | TF-IDF scoring |
| **Schema Optimizer** | Tool definitions | 50-90% | TF-IDF cosine similarity |
| **Observation Masker** | Old tool outputs | ~50% | Zero (placeholder swap) |
| **Cache Aligner** | System prompts | Provider cache discount | Regex substitution |

The pipeline adapts automatically — short contexts get light compression, long contexts get aggressive optimization.

## Configuration

```bash
# Disable specific transforms
uv run kompact proxy --port 7878 --disable toon --disable log_compressor

# Verbose mode
uv run kompact proxy --port 7878 --verbose

# View live dashboard
open http://localhost:7878/dashboard
```

## Benchmarks

Tested against Headroom and LLMLingua-2 on real datasets (BFCL, HotpotQA, Glaive, LongBench) using [context-bench](https://github.com/context-bench/context-bench).

**Search-heavy scenario (100 JSON results, 3 needles):**

| System | Compression | NIAH | Effective Ratio |
|--------|------------:|-----:|----------------:|
| Headroom | 0.0% | 100% | 0.0% |
| LLMLingua-2 | 55.4% | 0% | -44.6% |
| Truncation (50%) | 50.0% | 33% | -16.6% |
| **Kompact** | **47.7%** | **100%** | **47.7%** |

*Effective ratio* accounts for retry cost: if compression destroys information (NIAH miss), you pay for both the failed attempt and the retry with full context. Negative = worse than no compression.

```bash
# Run on real datasets
uv run python benchmarks/run_dataset_eval.py --dataset bfcl -n 100

# Run synthetic scenarios
uv run python benchmarks/run_comparison.py --scenario search

# Exclude slow baselines
uv run python benchmarks/run_comparison.py --scenario search --exclude llmlingua headroom
```

See [`benchmarks/README.md`](benchmarks/README.md) for full methodology.

## Development

```bash
# Install with dev deps
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Run single transform test
uv run pytest tests/test_toon.py -v
```

## Architecture

```
src/kompact/
├── proxy/server.py          # FastAPI proxy (Anthropic + OpenAI)
├── parser/messages.py       # Provider format ↔ internal types
├── transforms/
│   ├── pipeline.py          # Orchestration + adaptive scaling
│   ├── toon.py              # JSON array → tabular (TOON format)
│   ├── json_crusher.py      # Statistical JSON compression
│   ├── code_compressor.py   # Code → skeleton extraction
│   ├── log_compressor.py    # Log deduplication
│   ├── content_compressor.py # Extractive text compression (TF-IDF)
│   ├── schema_optimizer.py  # TF-IDF tool selection
│   ├── observation_masker.py # History management
│   └── cache_aligner.py     # Prefix cache optimization
├── cache/store.py           # Compression store + artifact index
├── config.py                # Per-transform configuration
├── types.py                 # Core data models
└── metrics/tracker.py       # Per-request metrics
```

## License

MIT
