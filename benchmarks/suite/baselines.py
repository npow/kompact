"""Helper functions for compression approaches.

Provides JSON minification, lazy-init singletons for Headroom/LLMLingua,
text extraction utilities, and message builders used by systems.py.
"""

from __future__ import annotations

import json
import re
from typing import Any

from kompact.types import ContentBlock, ContentType, Message, Role

from .metrics import count_tokens


def _extract_all_text(messages: list[Message]) -> str:
    """Get all text content from messages."""
    parts = []
    for msg in messages:
        for block in msg.content:
            if block.text:
                parts.append(block.text)
    return "\n".join(parts)


def build_messages(example: dict[str, Any]) -> list[Message]:
    """Convert a dict example into kompact Message format.

    Wraps the context as a tool_result (simulating a retrieval tool returning
    documents) and the question as a user text message.
    """
    messages = []
    context = example.get("context", "")
    question = example.get("question", "")

    if context:
        messages.append(Message(role=Role.ASSISTANT, content=[
            ContentBlock(
                type=ContentType.TOOL_USE,
                text="",
                tool_use_id="retrieve_1",
                tool_name="retrieve_context",
            ),
        ]))
        messages.append(Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=context,
                tool_use_id="retrieve_1",
            ),
        ]))
    if question:
        messages.append(Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=question),
        ]))
    return messages


# ---------------------------------------------------------------------------
# JSON Minification helpers
# ---------------------------------------------------------------------------

def _minify_json_in_text(text: str) -> str:
    """Re-serialize any JSON found in text with compact separators."""
    try:
        data = json.loads(text)
        return json.dumps(data, separators=(",", ":"))
    except (json.JSONDecodeError, TypeError):
        pass

    result = text
    for match in re.finditer(r"[\[{]", text):
        start = match.start()
        try:
            data = json.loads(text[start:])
            minified = json.dumps(data, separators=(",", ":"))
            end = _find_json_end(text, start)
            if end is not None:
                result = result[:start] + minified + result[end:]
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return result


def _find_json_end(text: str, start: int) -> int | None:
    """Find the end of a JSON value starting at position start."""
    opener = text[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
    return None


# ---------------------------------------------------------------------------
# Lazy-init singletons for Headroom and LLMLingua
# ---------------------------------------------------------------------------

_headroom_smart = None
_llmlingua_compressor = None


def _get_headroom():
    """Get or initialize Headroom SmartCrusher with recommended production defaults."""
    global _headroom_smart
    if _headroom_smart is None:
        from headroom import SmartCrusher, SmartCrusherConfig

        _headroom_smart = SmartCrusher(SmartCrusherConfig(
            enabled=True,
            min_tokens_to_crush=200,  # their production default
            max_items_after_crush=15,  # their default
            variance_threshold=2.0,  # standard 2-sigma
        ))
    return _headroom_smart


def _get_llmlingua():
    """Get or initialize the real LLMLingua-2 compressor."""
    global _llmlingua_compressor
    if _llmlingua_compressor is None:
        from llmlingua import PromptCompressor
        _llmlingua_compressor = PromptCompressor(
            model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            use_llmlingua2=True,
            device_map="cpu",
        )
    return _llmlingua_compressor
