# Quality Grades by Content Domain

Each transform has different effectiveness depending on content type.

## Grade Matrix

| Content Type | TOON | JSON Crusher | Obs. Masker | Cache Aligner | Code Comp. | Log Comp. |
|-------------|------|-------------|-------------|---------------|-----------|-----------|
| JSON arrays (homogeneous) | A+ | A | — | — | — | — |
| JSON arrays (heterogeneous) | B | A | — | — | — | — |
| JSON objects (nested) | C | B+ | — | — | — | — |
| Code files | — | — | — | — | A | — |
| Log output | — | — | — | — | — | A |
| Search results | A | A | B+ | — | — | — |
| API responses | A | A+ | A | — | — | — |
| System prompts | — | — | — | A+ | — | — |
| Tool definitions | — | — | — | B | — | — |
| Conversation history | — | — | A+ | — | — | — |

## Grades

- **A+**: > 60% savings, high confidence, no accuracy impact
- **A**: 40-60% savings, high confidence
- **B+**: 30-40% savings, moderate confidence
- **B**: 20-30% savings
- **C**: < 20% savings or accuracy risk
- **—**: Not applicable

## Composite Savings (Typical Agentic Session)

A typical Claude Code session context:
- 30% tool definitions → Schema Optimizer (50-90% savings on this portion)
- 25% tool outputs (JSON) → TOON + JSON Crusher (40-70% savings)
- 20% old tool outputs → Observation Masker (100% savings on this portion)
- 15% code content → Code Compressor (70% savings)
- 10% conversation text → No compression (preserve fidelity)

**Expected overall**: 45-65% token reduction
