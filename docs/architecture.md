# Architecture — Transform Layers

## Layer 1: Schema Optimization

**Problem**: Tool definitions consume 10-40% of context. Agents often have 50+ tools but use 2-3 per turn.

**Approach**: Score tool relevance against current conversation, include only top-K tools.

**Fallback**: Without embedding model, use keyword matching or include all tools.

## Layer 2: Content Compression

Multiple independent transforms targeting different content types:

### TOON (Token-Optimized Object Notation)
Converts JSON arrays to tabular format:
```json
[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
```
→
```
[FIELDS: name, age]
Alice | 30
Bob | 25
```
30-60% token reduction. Zero compute. Can improve accuracy by reducing noise.

### JSON Crusher
Statistical analysis of JSON fields:
- Constant fields (same value in all items) → factored out as header
- Low-cardinality fields → enumerated
- High-uniqueness fields → kept as-is
- Anomaly preservation: items differing from pattern kept in full

### Code Compressor
AST-based skeleton extraction:
- Keep: imports, class/function signatures, type annotations, docstrings
- Drop: function bodies, inline comments, blank lines
- Result: structural overview that preserves API surface

### Log Compressor
Pattern-based deduplication:
- Detect repeated log patterns (timestamp + level + similar message)
- Replace N identical lines with `[repeated N times]`
- Keep first and last occurrence
- Preserve unique/error entries

## Layer 3: History Management

### Observation Masking
Replace old tool outputs beyond a recency window:
```
tool_result: [Output omitted — 2,847 tokens. Key: search results for "python async". Use kompact_retrieve to get full content.]
```
- Configurable window (default: keep last 3 tool outputs)
- Store full content in compression store for retrieval
- Include brief summary in placeholder

## Layer 4: Cache Alignment

### Prefix Cache Optimization
Normalize dynamic content in early messages for provider cache hits:
- Extract UUIDs, timestamps, session IDs to a `dynamic_values` section at message end
- Stable prefix → provider caches it (Anthropic: 90% discount, OpenAI: 50%)
- Dynamic tail → small, uncached portion

Pattern:
```
[STABLE CONTENT — cacheable]
System prompt, tool definitions, instructions...

[DYNAMIC TAIL — not cached but small]
session_id: abc-123
timestamp: 2024-01-15T10:30:00Z
```
