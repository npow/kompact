# Benchmarks

## Real Dataset Results

Industry-standard datasets, full size, no subsampling.

### BFCL — Berkeley Function Calling Leaderboard (1,431 examples)

Real API schemas from the [Gorilla project](https://gorilla.cs.berkeley.edu/). Subsets: live_multiple, live_simple, rest, exec_multiple.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 97% | 96.6% | -1.5% | 931 |
| JSON Minification | 32.9% | 97% | 96.5% | 31.4% | 625 |
| Truncation (50%) | 49.7% | 97% | 96.6% | 48.2% | 469 |
| **Kompact** | **55.3%** | **90%** | **90.9%** | **48.2%** | **443** |

### Glaive Function Calling v2 (3,959 examples)

Tool-calling conversations with JSON schemas in system prompts.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 157 |
| JSON Minification | 35.3% | 100% | 100.0% | 35.3% | 101 |
| Truncation (50%) | 47.8% | 100% | 100.0% | 47.8% | 82 |
| **Kompact** | **56.6%** | **100%** | **100.0%** | **56.6%** | **68** |

### HotpotQA — distractor split (7,405 examples)

Multi-hop QA over Wikipedia paragraphs. Standard benchmark for Headroom and LLMLingua.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 97% | 97.1% | -2.5% | 1,363 |
| JSON Minification | 0.0% | 97% | 97.1% | -2.5% | 1,363 |
| Truncation (50%) | 49.9% | 63% | 71.4% | 13.0% | 1,004 |
| **Kompact** | **17.9%** | **91%** | **93.1%** | **8.8%** | **1,183** |

*12,795 total examples across 3 datasets. No LLM calls — offline compression quality.*

---

## End-to-End Quality (8,836 examples)

Does compression change the LLM's answers? Each example sent through Claude (via [claude-relay](https://github.com/npow/claude-relay)) with no compression, Kompact, and Headroom (SmartCrusher + ToolCrusher). **Contains** = answer found in LLM response.

| Dataset | Examples | Baseline | Kompact | Headroom |
|---------|----------|--------:|--------:|---------:|
| **BFCL** | 1,431 | 29.3% | **36.4%** | 31.4% |
| **HotpotQA** | 7,405 | 80.6% | 80.3% | 80.6% |

Kompact improves answer quality on agentic workloads (+7.1% vs baseline, +5.0% vs Headroom on BFCL). Quality is preserved on prose (HotpotQA within 0.3%).

---

## Synthetic Scenario Results

6 controlled scenarios, 3 needles each. Tests individual transforms.

### Overall (6 scenarios combined)

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 14,372 |
| JSON Minification | 3.9% | 100% | 100.0% | 3.9% | 13,806 |
| Truncation (50%) | 50.9% | 28% | 39.5% | -23.8% | 25,387 |
| **Kompact** | **45.5%** | **83%** | **86.3%** | **33.7%** | **9,405** |

*18 examples across 6 scenarios, 3 needles each.*

### search_heavy

100 JSON search results (~50K chars). Tests TOON + JSON Crusher.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 14,223 |
| JSON Minification | 23.9% | 100% | 100.0% | 23.9% | 10,824 |
| Truncation (50%) | 50.0% | 33% | 36.7% | -16.6% | 21,318 |
| **Kompact** | **47.7%** | **100%** | **100.0%** | **47.7%** | **7,440** |

### code_heavy

4 Python files (~39K chars). Tests Code Compressor.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 9,794 |
| JSON Minification | 0.0% | 100% | 100.0% | 0.0% | 9,794 |
| Truncation (50%) | 50.9% | 33% | 40.7% | -15.8% | 14,439 |
| **Kompact** | **81.8%** | **100%** | **100.0%** | **81.8%** | **1,784** |

### log_heavy

500+ line server log (~68K chars). Tests Log Compressor.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 23,940 |
| JSON Minification | 0.0% | 100% | 100.0% | 0.0% | 23,940 |
| Truncation (50%) | 50.0% | 33% | 40.6% | -16.7% | 35,916 |
| **Kompact** | **22.2%** | **100%** | **100.0%** | **22.2%** | **18,621** |

### schema_heavy

60 tool definitions + conversation (~85K chars). Tests Schema Optimizer.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 20,925 |
| JSON Minification | 0.0% | 100% | 100.0% | 0.0% | 20,925 |
| Truncation (50%) | 50.5% | 0% | 19.0% | -49.5% | N/A |
| **Kompact** | **50.4%** | **100%** | **100.0%** | **50.4%** | **10,373** |

### conversation_heavy

25 turns, 8 tool calls (~17K chars). Tests Observation Masker.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 4,237 |
| JSON Minification | 0.0% | 100% | 100.0% | 0.0% | 4,237 |
| Truncation (50%) | 43.6% | 33% | 55.1% | -23.1% | 7,170 |
| **Kompact** | **62.2%** | **67%** | **75.8%** | **28.9%** | **2,400** |

### mixed_realistic

System prompt + tools + code + JSON + logs (~42K chars). Tests all transforms.

| System | Compression | NIAH | Recall | Effective Ratio | Cost-of-Pass |
|--------|------------:|-----:|-------:|----------------:|-------------:|
| No Compression | 0.0% | 100% | 100.0% | 0.0% | 13,113 |
| JSON Minification | 0.0% | 100% | 100.0% | 0.0% | 13,113 |
| Truncation (50%) | 56.7% | 33% | 44.9% | -10.0% | 17,040 |
| Kompact | 45.0% | 33% | 42.2% | -21.6% | 21,618 |

## Metrics

- **Compression** — `1 - output_tokens / input_tokens`. Higher = more compression.
- **NIAH** (Needle In A Haystack) — binary: did the answer substring survive in the compressed output? Averaged across needles.
- **Recall** — substring match first, then token recall fallback (`|answer_tokens & context_tokens| / |answer_tokens|`).
- **Effective Ratio** — retry-adjusted compression. If NIAH misses (needle lost), effective cost = compressed + original (wasted attempt + retry). Negative means worse than no compression.
- **Cost-of-Pass** — total output tokens / number of examples with recall >= 0.7. Lower = more efficient. From [arXiv:2504.13359](https://arxiv.org/abs/2504.13359).

## Datasets

### Synthetic scenarios (this page)

6 scenarios designed to stress-test specific transforms:

| Scenario | Content Type | Size | Primary Transform |
|----------|-------------|------|-------------------|
| search_heavy | 100 JSON search results | ~50K chars | TOON + JSON Crusher |
| code_heavy | 4 Python files | ~39K chars | Code Compressor |
| log_heavy | 500+ server log lines | ~68K chars | Log Compressor |
| schema_heavy | 60 tool definitions | ~85K chars | Schema Optimizer |
| conversation_heavy | 25 turns, 8 tool calls | ~17K chars | Observation Masker |
| mixed_realistic | All content types | ~42K chars | Full pipeline |

### Real datasets

Industry-standard datasets for comparison with published results:

**Agentic / tool-calling (Kompact's target domain):**
- **BFCL** (Berkeley Function Calling Leaderboard) — 1,431 real API schemas from the Gorilla project
- **Glaive Function Calling v2** — 3,959 tool-calling conversations with JSON schemas

**Coding agents:**
- **SWE-bench Verified** — 500 human-validated GitHub issues (the standard for coding agent eval)
- **SWE-bench Full** — 2,294 GitHub issues from 12 Python repositories

**QA / prose context (baseline comparison):**
- **HotpotQA** (distractor split) — 7,405 multi-hop QA over Wikipedia paragraphs
- **LongBench v2** — long-context understanding across diverse domains

## Approaches Compared

| # | Approach | Description |
|---|----------|-------------|
| 1 | No Compression | Pass-through baseline |
| 2 | JSON Minification | Re-serialize JSON compactly |
| 3 | Truncation (50%) | Keep first half of each content block |
| 4 | Headroom | Real headroom-ai SmartCrusher (optional, `--exclude` to skip) |
| 5 | LLMLingua-2 | Real LLMLingua-2 compression (optional, `--exclude` to skip) |
| 6 | **Kompact Pipeline** | Full multi-transform pipeline |

## Running

```bash
# Synthetic scenarios (fast, no downloads)
uv run python benchmarks/run_comparison.py
uv run python benchmarks/run_comparison.py --scenario search

# Real datasets (requires HuggingFace downloads)
uv run python benchmarks/run_dataset_eval.py
uv run python benchmarks/run_dataset_eval.py --dataset bfcl -n 100
uv run python benchmarks/run_dataset_eval.py --dataset agentic

# Skip slow baselines
uv run python benchmarks/run_comparison.py --exclude llmlingua headroom
```
