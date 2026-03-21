# Kompact

[![CI](https://github.com/npow/kompact/actions/workflows/ci.yml/badge.svg)](https://github.com/npow/kompact/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/kompact.svg)](https://pypi.org/project/kompact/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![Docs](https://img.shields.io/badge/docs-mintlify-18a34a?style=flat-square)](https://mintlify.com/npow/kompact)

Context compression proxy for LLM agents. Sits between your agent and the LLM provider, compresses context on the fly, and cuts your token bill 40-70% — with zero code changes.

## Save real money

For a team running 1,000 agentic requests/day with ~10K token contexts:

| Model | Without Kompact | With Kompact | Monthly Savings |
|-------|----------------:|-------------:|----------------:|
| Sonnet ($3/M) | $900/mo | $405/mo | **$495/mo** |
| Opus ($15/M) | $4,500/mo | $2,025/mo | **$2,475/mo** |
| GPT-4o ($2.50/M) | $750/mo | $338/mo | **$412/mo** |

Savings scale linearly. 10K requests/day = 10x the numbers above.

## Get started in 30 seconds

```bash
pip install kompact   # or: uv add kompact
kompact proxy --port 7878
```

```bash
export ANTHROPIC_BASE_URL=http://localhost:7878
# That's it. Your agent now uses fewer tokens.
```

No SDK changes. No prompt rewriting. Just point your base URL at the proxy.

## Quality stays intact

Evaluated on [BFCL](https://gorilla.cs.berkeley.edu/) (1,431 real API schemas) — the standard benchmark for tool-calling agents. End-to-end through Claude, scored with [context-bench](https://pypi.org/project/context-bench/).

Quality impact vs no compression (closer to 0% = better):

| Model | Kompact | [Headroom](https://github.com/headroom-ai/headroom) | [LLMLingua-2](https://github.com/microsoft/LLMLingua) |
|-------|--------:|--------:|---------:|
| Haiku | **-2.6%** | -3.0% | -23.4% |
| Sonnet | **-3.9%** | -3.5% | -20.6% |
| Opus | **-0.5%** | -0.5% | -27.3% |

Kompact and Headroom both stay within ~3% of baseline. LLMLingua-2 destroys tool schemas regardless of model (-20 to -27%).

## Compression across content types

Measured offline on 12,795 examples across 3 datasets:

| Dataset | Examples | Kompact | Headroom | LLMLingua-2 |
|---------|----------|--------:|---------:|------------:|
| BFCL (tool schemas) | 1,431 | **55.3%** | ~0% | 55.4% |
| Glaive (tool calling) | 3,959 | **56.6%** | ~0% | ~50% |
| HotpotQA (prose QA) | 7,405 | 17.9% | ~0% | 49.9% |

Headroom's SmartCrusher doesn't compress JSON — it's designed for prose. LLMLingua-2 compresses aggressively but destroys information (see quality table above).

## How it works

Kompact is a transparent HTTP proxy. It intercepts LLM API requests, compresses the context, then forwards to the provider.

```
        ┌──────────────────────────────────────────────┐
        │           Kompact Proxy (:7878)              │
        │                                              │
Agent ─>│  1. Schema Optimizer    (TF-IDF selection)   │─> LLM Provider
        │  2. Content Compressors (TOON, JSON, code)   │
        │  3. Extractive Compress (TF-IDF sentences)   │
        │  4. Observation Masker  (history mgmt)       │
        │  5. Cache Aligner       (prefix caching)     │
        │                                              │
        └──────────────────────────────────────────────┘
```

8 transforms, each targeting a different content type. The pipeline adapts automatically — short contexts get light compression, long contexts get aggressive optimization. Sub-millisecond overhead.

### Per-request control

Disable transforms for a single request without affecting other clients using the `X-Kompact-Disable` header:

```python
# Anthropic SDK
client.messages.create(..., extra_headers={"X-Kompact-Disable": "toon,code_compressor"})

# OpenAI SDK
client.chat.completions.create(..., extra_headers={"X-Kompact-Disable": "toon,code_compressor"})
```

Comma-separated transform names: `toon`, `json_crusher`, `code_compressor`, `log_compressor`, `content_compressor`, `observation_masker`, `cache_aligner`, `schema_optimizer`.

## Running benchmarks

```bash
# Offline compression (no LLM calls, measures compression + needle preservation)
uv run python benchmarks/run_dataset_eval.py --dataset bfcl

# End-to-end quality (sends through proxy chain, measures LLM answer quality)
# Requires: claude-relay running on :8084, kompact on :7878
uv run python benchmarks/run_e2e_eval.py --dataset bfcl --model haiku --workers 20
```

See [`benchmarks/README.md`](benchmarks/README.md) for full methodology.

## Development

```bash
uv sync --extra dev
uv run pytest          # 48 tests
uv run ruff check src/ tests/
```

## License

MIT
