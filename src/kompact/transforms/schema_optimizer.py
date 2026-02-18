"""Schema optimizer transform — TF-IDF tool selection.

Dynamically selects relevant tool definitions based on conversation context
using TF-IDF cosine similarity scoring. Irrelevant tools are removed,
keeping only top-K plus recently-used tools.

Ported from compressor's ToolSelector, adapted to Kompact's type system.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from kompact.config import SchemaOptimizerConfig
from kompact.types import Message, Request, ToolDefinition, TransformResult


def transform(
    request: Request,
    config: SchemaOptimizerConfig | None = None,
) -> TransformResult:
    """Select the most relevant tools for the current conversation."""
    if config is None:
        config = SchemaOptimizerConfig()

    if not request.tools or len(request.tools) <= config.max_tools:
        return TransformResult(
            messages=request.messages,
            tokens_saved=0,
            transform_name="schema_optimizer",
        )

    # Extract query from recent messages
    query = _extract_query(request.messages)

    # Score all tools using TF-IDF
    scored_tools = _score_tools(request.tools, query, request.messages, config)

    # Sort by relevance, keep top K
    scored_tools.sort(key=lambda x: x[0], reverse=True)
    selected = [tool for _, tool in scored_tools[: config.max_tools]]

    # Always include tools that were just called (in last assistant message)
    recently_used = _get_recently_used_tools(request.messages)
    for tool in request.tools:
        if tool.name in recently_used and tool not in selected:
            selected.append(tool)

    # Calculate savings
    removed_count = len(request.tools) - len(selected)
    removed_tools = [tool for _, tool in scored_tools[config.max_tools :]]
    tokens_saved = sum(
        _estimate_tool_tokens(t) for t in removed_tools if t not in selected
    )

    request.tools = selected

    return TransformResult(
        messages=request.messages,
        tokens_saved=tokens_saved,
        transform_name="schema_optimizer",
        details={
            "original_count": len(scored_tools),
            "selected_count": len(selected),
            "removed_count": removed_count,
        },
    )


def _tokenize(text: str) -> list[str]:
    """Simple tokenization: lowercase and split on word boundaries."""
    return re.findall(r"\b\w+\b", text.lower())


def _tool_to_text(tool: ToolDefinition) -> str:
    """Convert tool definition to searchable text."""
    parts = [tool.name, tool.description]
    schema = tool.input_schema
    if schema:
        props = schema.get("properties", {})
        for pname, pdef in props.items():
            parts.append(pname)
            if isinstance(pdef, dict):
                parts.append(pdef.get("description", ""))
    return " ".join(parts)


def _compute_idf(tools: list[ToolDefinition]) -> dict[str, float]:
    """Compute IDF scores for all terms across tools."""
    term_doc_count: dict[str, int] = {}
    total_docs = len(tools)

    for tool in tools:
        unique_terms = set(_tokenize(_tool_to_text(tool)))
        for term in unique_terms:
            term_doc_count[term] = term_doc_count.get(term, 0) + 1

    idf = {}
    for term, doc_count in term_doc_count.items():
        idf[term] = math.log(total_docs / (1 + doc_count))
    return idf


def _tfidf_cosine(
    query_tf: Counter[str],
    doc_tf: Counter[str],
    idf: dict[str, float],
) -> float:
    """Compute cosine similarity between query and document TF-IDF vectors."""
    dot_product = 0.0
    for term, qcount in query_tf.items():
        if term in doc_tf:
            q_tfidf = qcount * idf.get(term, 0.0)
            d_tfidf = doc_tf[term] * idf.get(term, 0.0)
            dot_product += q_tfidf * d_tfidf

    query_mag = math.sqrt(
        sum((c * idf.get(t, 0.0)) ** 2 for t, c in query_tf.items())
    )
    doc_mag = math.sqrt(
        sum((c * idf.get(t, 0.0)) ** 2 for t, c in doc_tf.items())
    )

    if query_mag == 0 or doc_mag == 0:
        return 0.0
    return dot_product / (query_mag * doc_mag)


def _extract_query(messages: list[Message]) -> str:
    """Extract query text from recent messages (last 5)."""
    parts = []
    for msg in messages[-5:]:
        parts.append(msg.text)
    return " ".join(parts)


def _score_tools(
    tools: list[ToolDefinition],
    query: str,
    messages: list[Message],
    config: SchemaOptimizerConfig,
) -> list[tuple[float, ToolDefinition]]:
    """Score tools by TF-IDF relevance to query."""
    if not query:
        return [(1.0, tool) for tool in tools]

    query_terms = Counter(_tokenize(query))
    idf = _compute_idf(tools)

    scored = []
    for tool in tools:
        tool_text = _tool_to_text(tool)
        tool_terms = Counter(_tokenize(tool_text))

        tfidf_score = _tfidf_cosine(query_terms, tool_terms, idf)

        # Boost for recently used tools
        recent_boost = _recent_usage_boost(tool, messages)

        scored.append((tfidf_score + recent_boost, tool))

    return scored


def _recent_usage_boost(tool: ToolDefinition, messages: list[Message]) -> float:
    """Boost score for tools used in recent messages."""
    for msg in messages[-3:]:
        for block in msg.content:
            if block.tool_name == tool.name:
                return 0.5
    return 0.0


def _get_recently_used_tools(messages: list[Message]) -> set[str]:
    """Get tool names used in the last assistant message."""
    used = set()
    for msg in reversed(messages):
        for block in msg.content:
            if block.tool_name:
                used.add(block.tool_name)
        if used:
            break
    return used


def _estimate_tool_tokens(tool: ToolDefinition) -> int:
    """Estimate tokens used by a tool definition."""
    import json

    raw = json.dumps(
        tool.raw
        or {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
    )
    return len(raw) // 4
