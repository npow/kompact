# Benchmark Strategy

## Tier 1: Compression Quality (run always)

### Custom NIAH (Needle In A Haystack)
- Insert 1 critical item among 100 tool outputs
- Compress with each transform
- Verify critical item survives (or is retrievable)
- **Pass criteria**: 100% critical item preservation

### Custom QA
- 500 tool output + question pairs across content types
- JSON arrays, code files, log outputs, search results
- Compress, then verify answer extractability
- **Pass criteria**: < 2% accuracy regression

### Token Reduction
- Measure compression ratio on realistic fixtures
- Track per-transform and cumulative savings
- **Target**: > 50% overall reduction on agentic workloads

## Tier 2: Agent Accuracy (run weekly)

### GAIA Level 1-2
- 466 general agent questions
- Measure accuracy and cost-of-pass (total_cost / accuracy)
- Compare with/without Kompact
- **Target**: Equal or better cost-of-pass

### RULER
- 13 information retrieval tasks
- Tests long-context comprehension
- **Target**: No accuracy regression

## Tier 3: End-to-End (run for releases)

### SWE-bench Verified
- 500 real GitHub issues
- Coding agent accuracy with/without Kompact
- **Target**: Equal accuracy at lower cost

## Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| compression_ratio | compressed_tokens / original_tokens | < 0.5 |
| cost_of_pass | total_cost / accuracy | Lower than baseline |
| critical_item_preservation | survived_items / total_critical_items | 1.0 |
| retrieval_rate | retrieve_requests / total_requests | < 0.05 |
| latency_overhead | terse_latency - direct_latency | < 50ms |
