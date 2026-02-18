"""Cache aligner transform.

Normalizes dynamic content (UUIDs, timestamps, session IDs, paths) in system
prompts and early messages to maximize provider prefix cache hits.

Anthropic: 90% discount on cached input tokens.
OpenAI: 50% discount on cached input tokens.

Strategy: Extract dynamic values to a tail section, keeping the stable
prefix identical across requests for cache reuse.
"""

from __future__ import annotations

import re

from kompact.config import CacheAlignerConfig
from kompact.types import ContentBlock, ContentType, Message, Role, TransformResult

# Patterns for dynamic content
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
UNIX_TS_PATTERN = re.compile(r"\b1[6-9]\d{8}\b")  # Unix timestamps (2020-2033)
ABS_PATH_PATTERN = re.compile(r"(?:/[\w.-]+){3,}")  # /foo/bar/baz style paths


def transform(
    messages: list[Message],
    config: CacheAlignerConfig | None = None,
    system_prompt: str = "",
) -> TransformResult:
    """Normalize dynamic content for cache alignment."""
    if config is None:
        config = CacheAlignerConfig()

    # Apply to system prompt
    aligned_system = system_prompt
    dynamic_values: dict[str, str] = {}

    if system_prompt:
        aligned_system, dynamic_values = _extract_dynamic(system_prompt, config)

    # Apply to first few messages (typically system-injected context)
    new_messages = []
    total_saved = 0

    for i, msg in enumerate(messages):
        # Only align system and early user messages (first 2)
        if msg.role == Role.SYSTEM or (msg.role == Role.USER and i < 2):
            new_blocks = []
            for block in msg.content:
                if block.type == ContentType.TEXT and block.text:
                    aligned, dyn = _extract_dynamic(block.text, config)
                    dynamic_values.update(dyn)
                    # Token savings from deduplication across requests, not within
                    new_blocks.append(ContentBlock(
                        type=block.type,
                        text=aligned,
                        tool_use_id=block.tool_use_id,
                        tool_name=block.tool_name,
                        is_compressed=bool(dyn),
                        original_tokens=block.original_tokens,
                    ))
                else:
                    new_blocks.append(block)
            new_messages.append(Message(role=msg.role, content=new_blocks))
        else:
            new_messages.append(msg)

    return TransformResult(
        messages=new_messages,
        tokens_saved=total_saved,
        transform_name="cache_aligner",
        details={
            "aligned_system": aligned_system,
            "dynamic_values": dynamic_values,
            "dynamic_count": len(dynamic_values),
        },
    )


def _extract_dynamic(
    text: str,
    config: CacheAlignerConfig,
) -> tuple[str, dict[str, str]]:
    """Replace dynamic values with stable placeholders.

    Returns (normalized_text, {placeholder: original_value}).
    """
    dynamic: dict[str, str] = {}
    result = text
    counter = 0

    if config.normalize_uuids:
        for match in UUID_PATTERN.finditer(text):
            val = match.group()
            placeholder = f"{{UUID_{counter}}}"
            dynamic[placeholder] = val
            result = result.replace(val, placeholder, 1)
            counter += 1

    if config.normalize_timestamps:
        for match in TIMESTAMP_PATTERN.finditer(result):
            val = match.group()
            placeholder = f"{{TS_{counter}}}"
            dynamic[placeholder] = val
            result = result.replace(val, placeholder, 1)
            counter += 1

    if config.normalize_paths:
        for match in ABS_PATH_PATTERN.finditer(result):
            val = match.group()
            # Only normalize if it looks like a user-specific path
            if any(seg in val for seg in ("/Users/", "/home/", "/tmp/")):
                placeholder = f"{{PATH_{counter}}}"
                dynamic[placeholder] = val
                result = result.replace(val, placeholder, 1)
                counter += 1

    return result, dynamic
