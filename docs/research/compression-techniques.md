# SOTA Compression Techniques Survey

## 1. TOON (Token-Optimized Object Notation)
- **Source**: Research on structured data representation for LLMs
- **Mechanism**: Convert JSON arrays to tabular format with declared field headers
- **Savings**: 30-60% token reduction
- **Accuracy**: Can improve accuracy by reducing structural noise
- **Compute**: Zero — pure string manipulation

## 2. Observation Masking
- **Source**: JetBrains Mellum research
- **Mechanism**: Replace old tool outputs with summary placeholders
- **Savings**: ~50% on tool-heavy conversations
- **Accuracy**: Minimal impact — old outputs rarely re-referenced
- **Compute**: Zero — position tracking only

## 3. SWE-Pruner (Neural Skimming)
- **Source**: SWE-bench optimization research
- **Mechanism**: Lightweight classifier scores sentence importance, drops low-score content
- **Savings**: Variable, depends on content
- **Accuracy**: Trained to preserve task-relevant information
- **Compute**: Neural inference per chunk

## 4. Context Folding
- **Source**: LLM context management research
- **Mechanism**: Hierarchical summarization of conversation history
- **Savings**: 40-60% on long conversations
- **Accuracy**: Good for narrative, risky for precise data
- **Compute**: Requires LLM call for summarization

## 5. CCR (Compressed Context Retrieval)
- **Source**: Headroom proxy
- **Mechanism**: Replace content with markers, retrieve on demand via tool
- **Savings**: 40-80% on structured data
- **Accuracy**: Depends on retrieval rate — model must know to ask
- **Compute**: Minimal (hashing + storage)

## 6. Prefix Caching
- **Source**: Anthropic, OpenAI provider features
- **Mechanism**: Normalize early context for cache hits
- **Savings**: 50-90% cost discount on cached portion
- **Accuracy**: Zero impact — content identical
- **Compute**: Regex normalization

## Composition Strategy

Layer these techniques — they target different content types:
1. TOON + JSON Crusher → structured tool outputs
2. Observation Masker → conversation history
3. Cache Aligner → system prompts and tool definitions
4. Code Compressor → code file contents
5. Log Compressor → log/build output
