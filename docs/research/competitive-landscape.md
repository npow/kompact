# Competitive Landscape

## Headroom
- **Approach**: JSON array compression via CCR (Compressed Context Retrieval)
- **Strengths**: Production-tested, good JSON handling
- **Gaps**: Only addresses JSON arrays (~20-30% of waste). Ignores tool schemas, conversation history, code, logs, cache alignment.
- **Pricing**: Commercial proxy service

## LLMLingua / LongLLMLingua
- **Approach**: Token-level pruning using small LM perplexity scores
- **Strengths**: Works on any text
- **Gaps**: Requires GPU, adds latency, can damage structured data
- **Status**: Research project

## Compresr (Context Gateway)
- **Approach**: Proxy that pre-computes LLM summaries of conversation history in the background
- **Strengths**: Drop-in proxy (like Kompact), high compression via summarization, async so latency is hidden
- **Gaps**: Lossy (summarization discards detail), requires LLM calls (cost), Go-only
- **Status**: YC-backed, open source ([GitHub](https://github.com/Compresr-ai/Context-Gateway))

## Prompt Compression (various)
- **Approach**: Summarize/rewrite prompts to be shorter
- **Strengths**: General purpose
- **Gaps**: Requires LLM call (cost + latency), lossy, hard to control
- **Status**: Various implementations

## Provider Features
- **Anthropic**: Prompt caching (90% discount), extended thinking
- **OpenAI**: Prefix caching (50% discount)
- **Status**: Built-in but passive — requires user to structure prompts correctly

## Kompact Differentiation

1. **Multi-layer**: Addresses ALL sources of waste, not just one
2. **Zero-compute core**: TOON, observation masking, cache alignment need no ML
3. **Composable**: Each layer is independent, stackable
4. **Transparent**: Drop-in proxy, no agent changes needed
5. **Measurable**: Per-transform metrics, dashboard
