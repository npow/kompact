"""Extractive content compressor transform.

Query-aware extractive compression for long text in tool results and messages.
Scores sentences by TF-IDF relevance, entity presence, position, and structure.
Keeps top-k sentences to hit a target retention ratio.

Protects code blocks, recent user messages, headings, and error lines.

Ported from compressor's ContentCompressor, adapted to Kompact's type system.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from kompact.config import ContentCompressorConfig
from kompact.types import ContentBlock, ContentType, Message, TransformResult


def transform(
    messages: list[Message],
    config: ContentCompressorConfig | None = None,
) -> TransformResult:
    """Compress long text content in tool results using extractive compression."""
    if config is None:
        config = ContentCompressorConfig()

    query = _extract_query(messages)
    all_text = " ".join(
        b.text for m in messages for b in m.content if b.text
    )
    idf = _compute_idf(all_text)

    # Protect recent user messages from compression
    user_msg_indices = {
        i for i, m in enumerate(messages)
        if any(b.type == ContentType.TEXT for b in m.content)
        and m.role.value == "user"
    }
    protected_indices = set()
    if user_msg_indices:
        sorted_user = sorted(user_msg_indices)
        protected_indices = set(sorted_user[-config.protect_recent_user_messages:])

    tokens_saved = 0
    new_messages = []

    for msg_idx, msg in enumerate(messages):
        new_blocks = []
        for block in msg.content:
            text = block.text
            est_tokens = len(text) // 4

            # Only compress substantial tool results / text blocks
            should_compress = (
                est_tokens >= config.min_tokens_to_compress
                and block.type in (ContentType.TOOL_RESULT, ContentType.TEXT)
                and msg_idx not in protected_indices
            )

            if should_compress:
                compressed = _compress_text(text, query, idf, config)
                saved = max(0, len(text) // 4 - len(compressed) // 4)
                tokens_saved += saved
                new_blocks.append(ContentBlock(
                    type=block.type,
                    text=compressed,
                    tool_use_id=block.tool_use_id,
                    tool_name=block.tool_name,
                    tool_input=block.tool_input,
                    is_compressed=block.is_compressed or saved > 0,
                    original_tokens=block.original_tokens or est_tokens,
                ))
            else:
                new_blocks.append(block)

        new_messages.append(Message(role=msg.role, content=new_blocks))

    return TransformResult(
        messages=new_messages,
        tokens_saved=tokens_saved,
        transform_name="content_compressor",
    )


def _tokenize(text: str) -> list[str]:
    """Simple word tokenization."""
    return [w.lower() for w in re.findall(r"\b\w+\b", text) if len(w) > 1]


def _compute_idf(corpus: str) -> dict[str, float]:
    """Compute IDF scores from paragraphs in corpus."""
    paragraphs = re.split(r"\n\n+", corpus)
    if not paragraphs:
        return {}

    n_docs = len(paragraphs)
    doc_freq: Counter[str] = Counter()
    for para in paragraphs:
        words = set(_tokenize(para))
        for w in words:
            doc_freq[w] += 1

    idf = {}
    for word, df in doc_freq.items():
        idf[word] = math.log((n_docs + 1) / (df + 1)) + 1
    return idf


def _extract_query(messages: list[Message]) -> str:
    """Extract query from the last user text message."""
    for msg in reversed(messages):
        for block in msg.content:
            if block.type == ContentType.TEXT and block.text:
                return block.text
    return ""


def _score_sentence(
    sentence: str,
    query_terms: set[str],
    idf: dict[str, float],
    is_first: bool,
    is_last: bool,
    config: ContentCompressorConfig,
) -> float:
    """Score a sentence for retention."""
    words = _tokenize(sentence)
    if not words:
        return 0.0

    # 1. Query relevance (TF-IDF weighted overlap)
    word_counts = Counter(words)
    query_score = 0.0
    for term in query_terms:
        if term in word_counts:
            tf = word_counts[term] / len(words)
            query_score += tf * idf.get(term, 1.0)

    # 2. Entity boost (numbers, dates, names, paths, issue refs)
    entity_patterns = [
        r"\d+\.?\d*",
        r"\b[A-Z][a-z]+\b",
        r"\b\d{4}[-/]\d{2}\b",
        r"[\w/]+\.\w+",
        r"#\d+",
    ]
    entity_count = sum(len(re.findall(p, sentence)) for p in entity_patterns)
    entity_score = min(entity_count * 0.3, 2.0)

    # 3. Position boost
    position_score = 0.0
    if is_first:
        position_score += 0.5
    if is_last:
        position_score += 0.3

    # 4. Structural importance
    structural_score = 0.0
    stripped = sentence.strip()
    if stripped.startswith(("#", "##", "###")):
        structural_score += 3.0
    if stripped.startswith(("-", "*", "1.", "2.")):
        structural_score += 0.5
    if re.match(r"^[A-Z][^.]*:\s", stripped):
        structural_score += 0.5
    if "error" in sentence.lower() or "fail" in sentence.lower():
        structural_score += 1.0

    return (
        query_score * 2.0
        + entity_score * config.entity_boost
        + position_score * config.position_boost
        + structural_score
    )


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving structure."""
    sentences = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) < 100:
            sentences.append(line)
        else:
            parts = re.split(r"(?<=[.!?])\s+", line)
            sentences.extend(p for p in parts if p.strip())
    return sentences


def _compress_text(
    text: str,
    query: str,
    idf: dict[str, float],
    config: ContentCompressorConfig,
) -> str:
    """Compress a text passage using extractive compression."""
    # Split, protecting code blocks
    parts = re.split(r"(```[\s\S]*?```)", text)
    query_terms = set(_tokenize(query))
    target_tokens = int(len(text) // 4 * config.target_ratio)

    # Score each block/sentence
    scored: list[tuple[float, int, str, bool]] = []
    idx = 0
    for part in parts:
        if not part.strip():
            continue
        if part.startswith("```"):
            if config.protect_code_blocks:
                scored.append((float("inf"), idx, part, True))
                idx += 1
            else:
                scored.append((0.0, idx, part, False))
                idx += 1
        else:
            sentences = _split_sentences(part)
            for j, sent in enumerate(sentences):
                score = _score_sentence(
                    sent,
                    query_terms,
                    idf,
                    is_first=(j == 0),
                    is_last=(j == len(sentences) - 1),
                    config=config,
                )
                scored.append((score, idx, sent, False))
                idx += 1

    # Select top sentences by score until we hit target
    by_score = sorted(scored, key=lambda x: x[0], reverse=True)
    selected: set[int] = set()
    current_tokens = 0
    for score, sidx, block_text, is_protected in by_score:
        block_tokens = len(block_text) // 4
        if is_protected or current_tokens + block_tokens <= target_tokens:
            selected.add(sidx)
            current_tokens += block_tokens

    # Reconstruct in original order with [...] markers for gaps
    by_order = sorted(scored, key=lambda x: x[1])
    result_parts = []
    prev_idx = -1
    for score, sidx, block_text, is_protected in by_order:
        if sidx in selected:
            if prev_idx >= 0 and sidx - prev_idx > 1:
                result_parts.append("[...]")
            result_parts.append(block_text)
            prev_idx = sidx

    return "\n".join(result_parts)
