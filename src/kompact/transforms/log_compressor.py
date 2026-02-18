"""Log compressor transform.

Deduplicates repetitive log patterns, keeping first and last occurrence
of repeated sequences and replacing the middle with a count.

Typical savings: 60-90% on build/test/server log output.

Strategy:
1. Normalize log lines (strip timestamps, PIDs)
2. Detect runs of similar lines
3. Replace runs with: first line + "[repeated N times]" + last line
4. Preserve error/warning lines always
"""

from __future__ import annotations

import re

from kompact.config import LogCompressorConfig
from kompact.types import ContentBlock, ContentType, Message, TransformResult

# Patterns for log line normalization
TIMESTAMP_PREFIX = re.compile(
    r"^\[?\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}[^\]]*\]?\s*"
)
PID_PREFIX = re.compile(r"^\[?\d+\]?\s*")
LOG_LEVEL = re.compile(r"\b(ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE|FATAL|CRITICAL)\b", re.IGNORECASE)

# Lines to always preserve
IMPORTANT_PATTERNS = [
    re.compile(
        r"\b(error|exception|traceback|failed|failure|panic|fatal|critical)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(warn(?:ing)?)\b", re.IGNORECASE),
    re.compile(r"^\s*(File |Traceback |  at |Caused by:)", re.IGNORECASE),
]


def transform(
    messages: list[Message],
    config: LogCompressorConfig | None = None,
) -> TransformResult:
    """Compress log output in tool results."""
    if config is None:
        config = LogCompressorConfig()

    tokens_saved = 0
    new_messages = []

    for msg in messages:
        new_blocks = []
        for block in msg.content:
            if block.type in (ContentType.TOOL_RESULT, ContentType.TEXT) and block.text:
                if _looks_like_log(block.text):
                    new_text, saved = compress_log(block.text, config)
                    tokens_saved += saved
                    new_blocks.append(ContentBlock(
                        type=block.type,
                        text=new_text,
                        tool_use_id=block.tool_use_id,
                        tool_name=block.tool_name,
                        is_compressed=saved > 0 or block.is_compressed,
                        original_tokens=block.original_tokens,
                    ))
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)
        new_messages.append(Message(role=msg.role, content=new_blocks))

    return TransformResult(
        messages=new_messages,
        tokens_saved=tokens_saved,
        transform_name="log_compressor",
    )


def compress_log(text: str, config: LogCompressorConfig) -> tuple[str, int]:
    """Compress log text by deduplicating similar lines."""
    lines = text.split("\n")
    if len(lines) < config.dedup_threshold:
        return text, 0

    output: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Always preserve important lines
        if _is_important(line):
            output.append(line)
            i += 1
            continue

        normalized = _normalize(line)

        # Look ahead for similar lines
        run_start = i
        while i + 1 < len(lines) and _normalize(lines[i + 1]) == normalized:
            i += 1

        run_length = i - run_start + 1

        if run_length >= config.dedup_threshold:
            if config.keep_first_last:
                output.append(lines[run_start])
                if run_length > 2:
                    output.append(f"  [... repeated {run_length - 2} more times ...]")
                if run_length > 1:
                    output.append(lines[i])
            else:
                output.append(lines[run_start])
                output.append(f"  [... repeated {run_length - 1} more times ...]")
        else:
            # Short run, keep all
            for j in range(run_start, i + 1):
                output.append(lines[j])

        i += 1

    result = "\n".join(output)
    saved = max(0, len(text) // 4 - len(result) // 4)
    return result, saved


def _normalize(line: str) -> str:
    """Normalize a log line for comparison (strip timestamps, PIDs, etc.)."""
    result = TIMESTAMP_PREFIX.sub("", line)
    result = PID_PREFIX.sub("", result)
    # Normalize all numeric sequences (including those adjacent to letters like 195ms, v1)
    result = re.sub(r"\d+", "N", result)
    return result.strip()


def _is_important(line: str) -> bool:
    """Check if a line should always be preserved."""
    return any(p.search(line) for p in IMPORTANT_PATTERNS)


def _looks_like_log(text: str) -> bool:
    """Heuristic: does this text look like log output?"""
    lines = text.split("\n")
    if len(lines) < 5:
        return False

    log_indicators = 0
    for line in lines[:20]:
        if TIMESTAMP_PREFIX.match(line):
            log_indicators += 1
        if LOG_LEVEL.search(line):
            log_indicators += 1

    return log_indicators >= 3
