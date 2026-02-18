# Benchmarks

## Real Dataset Benchmarks (Primary)

Runs compression approaches against industry-standard datasets — the same ones
Headroom, LLMLingua, and other competitors publish numbers on.

### Datasets

**Agentic / tool-calling (Kompact's target domain):**
- **BFCL** (Berkeley Function Calling Leaderboard) — real API schemas from the Gorilla project. The primary benchmark for tool-calling compression.
- **Glaive Function Calling v2** — 113K tool-calling conversations with JSON schemas in system prompts.

**QA / prose context (baseline comparison):**
- **HotpotQA** (distractor split) — multi-hop QA over Wikipedia paragraphs
- **LongBench v2** — long-context understanding across diverse domains

### What's measured

- **Compression ratio** — tokens after / tokens before (lower = more compression)
- **Answer preservation** — does the answer string survive compression? (higher = better)
- **Latency** — wall-clock time per example

No LLM calls required. Measures compression quality, not downstream task accuracy.

### Running

```bash
# All 4 datasets (100 examples each)
uv run python benchmarks/run_dataset_eval.py

# Just the agentic datasets (BFCL + Glaive)
uv run python benchmarks/run_dataset_eval.py --dataset agentic

# Just the QA datasets (HotpotQA + LongBench)
uv run python benchmarks/run_dataset_eval.py --dataset qa

# Single dataset with custom size
uv run python benchmarks/run_dataset_eval.py --dataset bfcl -n 200
```

Reports saved to `benchmarks/reports/dataset_eval_report.md`.

## Synthetic Benchmarks (Secondary)

6 synthetic agentic scenarios x 6 approaches. Useful for testing specific
transforms (TOON on JSON arrays, log compressor on logs, etc.).

```bash
uv run python benchmarks/run_comparison.py
uv run python benchmarks/run_comparison.py --scenario search
```

## Approaches Compared

| # | Approach | Description |
|---|----------|-------------|
| 1 | No Compression | Pass-through baseline |
| 2 | JSON Minification | Re-serialize JSON compactly |
| 3 | Truncation (50%) | Keep first half of each content block |
| 4 | Headroom CCR | Replace large JSON arrays with schema marker + first item |
| 5 | LLMLingua-style | Word frequency pruning — remove low-importance words |
| 6 | **Kompact Pipeline** | Full multi-transform pipeline |

## Legacy Benchmarks

- `compression_ratio.py` — per-transform compression ratios on test fixtures
- `accuracy_preservation.py` — NIAH test on synthetic data
