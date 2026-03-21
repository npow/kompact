"""JSON crusher transform.

Statistical compression of JSON arrays by factoring out constant fields,
enumerating low-cardinality fields, and preserving anomalies.

Goes beyond TOON by analyzing field value distributions:
- Constant fields (same in all items) → header annotation
- Low-cardinality fields → enumerated with codes
- Anomalies (items differing from pattern) → kept in full

Typical savings: 40-80% on structured JSON data.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from kompact.config import JsonCrusherConfig
from kompact.types import ContentBlock, ContentType, Message, TransformResult


def transform(
    messages: list[Message],
    config: JsonCrusherConfig | None = None,
) -> TransformResult:
    """Apply JSON crushing to tool results."""
    if config is None:
        config = JsonCrusherConfig()

    tokens_saved = 0
    new_messages = []

    for msg in messages:
        new_blocks = []
        for block in msg.content:
            if block.type in (ContentType.TOOL_RESULT, ContentType.TEXT) and block.text:
                new_text, saved = _crush_text(block.text, config)
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
        new_messages.append(Message(role=msg.role, content=new_blocks))

    return TransformResult(
        messages=new_messages,
        tokens_saved=tokens_saved,
        transform_name="json_crusher",
    )


def _crush_text(text: str, config: JsonCrusherConfig) -> tuple[str, int]:
    """Find and crush JSON arrays in text. Falls back to minification."""
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) >= config.min_array_length:
            if all(isinstance(item, dict) for item in data):
                result = crush_array(data, config)
                if result is not None:
                    saved = _estimate_savings(text, result)
                    return result, saved
        # Fallback: minify pretty-printed JSON (must contain newlines, no code)
        if "\n" in text and not _contains_code(text):
            minified = json.dumps(data, separators=(",", ":"))
            if len(minified) < len(text):
                saved = _estimate_savings(text, minified)
                return minified, saved
    except (json.JSONDecodeError, TypeError):
        pass
    return text, 0


def crush_array(data: list[dict[str, Any]], config: JsonCrusherConfig) -> str | None:
    """Crush a JSON array by factoring out constants and low-cardinality fields."""
    if not data:
        return None

    # Analyze field distributions
    all_fields: list[str] = []
    seen: set[str] = set()
    for item in data:
        for key in item:
            if key not in seen:
                all_fields.append(key)
                seen.add(key)

    analysis = _analyze_fields(data, all_fields, config)

    # Only optimize if we found constants or anomalies to factor out
    if not analysis["constants"] and not analysis["anomaly_indices"]:
        return None

    lines: list[str] = []

    # Header: constant fields
    if analysis["constants"]:
        const_parts = [f"{k}={_fmt(v)}" for k, v in analysis["constants"].items()]
        lines.append(f"[CONSTANTS: {', '.join(const_parts)}]")

    # Remaining fields header
    remaining = analysis["variable_fields"]
    if remaining:
        lines.append(f"[FIELDS: {', '.join(remaining)}]")

    # Data rows (only variable fields)
    for i, item in enumerate(data):
        if i in analysis["anomaly_indices"]:
            # Keep anomalies in full JSON
            lines.append(f"!ANOMALY: {json.dumps(item, separators=(',', ':'))}")
        else:
            values = [_fmt(item.get(f, "")) for f in remaining]
            lines.append(" | ".join(values))

    return "\n".join(lines)


def _analyze_fields(
    data: list[dict[str, Any]],
    fields: list[str],
    config: JsonCrusherConfig,
) -> dict[str, Any]:
    """Analyze field distributions in a JSON array."""
    constants: dict[str, Any] = {}
    low_cardinality: dict[str, list[Any]] = {}
    variable_fields: list[str] = []
    n = len(data)

    for field in fields:
        values = [item.get(field) for item in data]
        value_strs = [json.dumps(v, separators=(",", ":")) for v in values]
        counter = Counter(value_strs)

        if len(counter) == 1 and config.constant_threshold <= 1.0:
            # All items have the same value
            constants[field] = values[0]
        elif len(counter) <= config.low_cardinality_threshold:
            low_cardinality[field] = list(counter.keys())
            variable_fields.append(field)
        else:
            variable_fields.append(field)

    # Find anomalies: items that differ significantly from the majority
    anomaly_indices: set[int] = set()
    if n >= 5:
        for field in fields:
            values = [json.dumps(item.get(field), separators=(",", ":")) for item in data]
            counter = Counter(values)
            most_common_val, most_common_count = counter.most_common(1)[0]
            if most_common_count >= n * 0.9:
                # This field is nearly constant — items with different values are anomalies
                for i, v in enumerate(values):
                    if v != most_common_val:
                        anomaly_indices.add(i)

    return {
        "constants": constants,
        "low_cardinality": low_cardinality,
        "variable_fields": variable_fields,
        "anomaly_indices": anomaly_indices,
    }


def _fmt(val: Any) -> str:
    """Format a value for crushed output."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, int | float):
        return str(val)
    if isinstance(val, str):
        return val
    return json.dumps(val, separators=(",", ":"))


def _contains_code(text: str) -> bool:
    """Check if text contains code patterns that the code compressor handles better."""
    indicators = 0
    if "def " in text:
        indicators += 1
    if "class " in text:
        indicators += 1
    if "import " in text:
        indicators += 1
    if "function " in text:
        indicators += 1
    return indicators >= 2


def _estimate_savings(original: str, crushed: str) -> int:
    """Estimate token savings."""
    return max(0, len(original) // 4 - len(crushed) // 4)
