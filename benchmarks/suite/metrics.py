"""Token counting, cost estimation, and answer recall.

Kept metrics:
  - normalize_answer: lowercase, strip articles/punctuation, collapse whitespace
  - answer_recall: substring check with token recall fallback
  - count_tokens: tiktoken cl100k_base
  - PRICING / estimate_cost / estimate_monthly_cost: cost estimation
"""

from __future__ import annotations

import re
import string
from collections import Counter

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")

PRICING: dict[str, tuple[float, float]] = {
    "anthropic_sonnet": (3.00, 0.30),
    "anthropic_opus": (15.00, 1.50),
    "openai_gpt4o": (2.50, 1.25),
    "openai_o1": (15.00, 7.50),
}


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken cl100k_base."""
    return len(_enc.encode(text, disallowed_special=()))


def estimate_cost(tokens: int, model: str, cached: bool = False) -> float:
    """Estimate cost in USD for a given token count and model."""
    if model not in PRICING:
        raise ValueError(f"Unknown model {model!r}. Choose from: {list(PRICING)}")
    input_price, cached_price = PRICING[model]
    price_per_token = (cached_price if cached else input_price) / 1_000_000
    return tokens * price_per_token


def estimate_monthly_cost(tokens_per_request: int, requests_per_day: int, model: str) -> float:
    """Estimate monthly cost assuming given request volume."""
    return estimate_cost(tokens_per_request, model) * requests_per_day * 30


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------

def normalize_answer(text: str) -> str:
    """Lowercase, strip articles/punctuation, collapse whitespace (SQuAD standard)."""
    text = text.lower()
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = " ".join(text.split())
    return text


def answer_recall(answer: str, context: str) -> float:
    """Check if answer survives in context.

    Returns 1.0 for exact substring match (case-insensitive),
    otherwise falls back to token recall (|answer_tokens & context_tokens| / |answer_tokens|).
    """
    if not answer:
        return 1.0

    if answer.lower() in context.lower():
        return 1.0

    ans_tokens = normalize_answer(answer).split()
    ctx_tokens = normalize_answer(context).split()

    if not ans_tokens:
        return 1.0

    common = Counter(ans_tokens) & Counter(ctx_tokens)
    return sum(common.values()) / len(ans_tokens)
