"""TOON (Token-Optimized Object Notation) transform.

Converts JSON arrays of objects into a compact tabular format:

Input:
    [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]

Output:
    [FIELDS: name, age]
    Alice | 30
    Bob | 25

Typical savings: 30-60% token reduction on homogeneous JSON arrays.
Zero compute overhead — pure string manipulation.
"""

from __future__ import annotations

import json
from typing import Any

from kompact.config import ToonConfig
from kompact.types import ContentBlock, ContentType, Message, TransformResult


def transform(
    messages: list[Message],
    config: ToonConfig | None = None,
) -> TransformResult:
    """Apply TOON transformation to all JSON arrays in tool results."""
    if config is None:
        config = ToonConfig()

    tokens_saved = 0
    new_messages = []

    for msg in messages:
        new_blocks = []
        for block in msg.content:
            if block.type in (ContentType.TOOL_RESULT, ContentType.TEXT) and block.text:
                new_text, saved = _transform_text(block.text, config)
                tokens_saved += saved
                new_block = ContentBlock(
                    type=block.type,
                    text=new_text,
                    tool_use_id=block.tool_use_id,
                    tool_name=block.tool_name,
                    tool_input=block.tool_input,
                    is_compressed=saved > 0 or block.is_compressed,
                    original_tokens=block.original_tokens,
                )
                new_blocks.append(new_block)
            else:
                new_blocks.append(block)
        new_messages.append(Message(role=msg.role, content=new_blocks))

    return TransformResult(
        messages=new_messages,
        tokens_saved=tokens_saved,
        transform_name="toon",
    )


def _transform_text(text: str, config: ToonConfig) -> tuple[str, int]:
    """Find and convert JSON arrays/objects in text. Returns (new_text, tokens_saved)."""
    # Try to parse the entire text as JSON first
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) >= config.min_array_length:
            result = convert_array_to_toon(data, config.separator)
            if result is not None:
                saved = _estimate_token_diff(text, result)
                return result, saved
        # Single tool definition object
        if isinstance(data, dict) and "name" in data and "parameters" in data:
            result = _try_tool_schema_array([data])
            if result is not None:
                saved = _estimate_token_diff(text, result)
                return result, saved
        # Any dict: try JSON minification
        if isinstance(data, dict | list):
            minified = json.dumps(data, separators=(",", ":"))
            if len(minified) < len(text) * 0.85:
                saved = _estimate_token_diff(text, minified)
                return minified, saved
    except (json.JSONDecodeError, TypeError):
        # Try parsing as multiple concatenated JSON objects (JSONL / Glaive format)
        objects = _parse_concatenated_json(text)
        # Only use if: all dicts, at least 1 object, and we parsed most of the text
        if (objects
            and all(isinstance(o, dict) for o in objects)
            and sum(len(json.dumps(o)) for o in objects) > len(text) * 0.5):
            # Check if they're all tool definitions
            if all("name" in o and "parameters" in o for o in objects):
                result = _try_tool_schema_array(objects)
                if result is not None:
                    saved = _estimate_token_diff(text, result)
                    return result, saved
            # Fallback: minify each object
            minified_parts = [json.dumps(o, separators=(",", ":")) for o in objects]
            minified = "\n".join(minified_parts)
            if len(minified) < len(text) * 0.85:
                saved = _estimate_token_diff(text, minified)
                return minified, saved

    # Look for JSON arrays embedded in text
    result_text = text
    total_saved = 0
    for start, end in _find_json_arrays(text):
        try:
            fragment = text[start:end]
            data = json.loads(fragment)
            if isinstance(data, list) and len(data) >= config.min_array_length:
                converted = convert_array_to_toon(data, config.separator)
                if converted is not None:
                    saved = _estimate_token_diff(fragment, converted)
                    total_saved += saved
                    result_text = result_text.replace(fragment, converted, 1)
        except (json.JSONDecodeError, TypeError):
            continue

    return result_text, total_saved


def convert_array_to_toon(
    data: list[Any],
    separator: str = " | ",
) -> str | None:
    """Convert a JSON array of objects to TOON format.

    Returns None if the array is not suitable for TOON conversion
    (e.g., not all items are objects, or fields are too inconsistent).
    """
    if not data or not all(isinstance(item, dict) for item in data):
        return None

    # Check if this is a tool definition array — use compact schema format
    schema_result = _try_tool_schema_array(data)
    if schema_result is not None:
        return schema_result

    # Collect all field names in order of first appearance
    fields: list[str] = []
    seen: set[str] = set()
    for item in data:
        for key in item:
            if key not in seen:
                fields.append(key)
                seen.add(key)

    if not fields:
        return None

    # Build TOON output
    lines = [f"[FIELDS: {', '.join(fields)}]"]
    for item in data:
        values = []
        for field in fields:
            val = item.get(field, "")
            values.append(_format_value(val))
        lines.append(separator.join(values))

    return "\n".join(lines)


_TYPE_SHORT = {
    "string": "str",
    "integer": "int",
    "boolean": "bool",
    "number": "num",
    "array": "list",
    "object": "dict",
}


def _try_tool_schema_array(data: list[dict[str, Any]]) -> str | None:
    """Detect tool definition arrays and compress to function-signature format.

    Recognizes arrays where items have "name", "description", and "parameters" fields
    (the standard tool/function schema format used by OpenAI, Anthropic, BFCL, etc).

    Output format (Python-signature-like, which LLMs understand natively):
        tool_name(*, required_param: str, optional_param: int = 0) -> description
          param_name: param description (only if non-trivial)
    """
    if len(data) < 1:
        return None

    # Check: do most items look like tool definitions?
    tool_count = sum(
        1 for item in data
        if isinstance(item.get("name"), str) and "parameters" in item
    )
    if tool_count < len(data) * 0.5:
        return None

    lines: list[str] = []
    for item in data:
        name = item.get("name", "")
        desc = item.get("description", "")
        params = item.get("parameters", {})

        sig = _build_param_signature(params)
        lines.append(f"{name}({sig})")
        if desc:
            lines.append(f"  {_shorten_description(desc)}")

        # Add parameter descriptions (only if they add info beyond the name)
        props = params.get("properties", {})
        for pname, pspec in props.items():
            if not isinstance(pspec, dict):
                continue
            pdesc = pspec.get("description", "")
            if pdesc and not _description_is_trivial(pname, pdesc):
                pdesc = _shorten_description(pdesc)
                # Include enum values if present (skip if already in signature)
                enum = pspec.get("enum")
                if enum and len(enum) > 3:
                    enum_str = "|".join(str(e) for e in enum)
                    lines.append(f"  {pname}({enum_str}): {pdesc}")
                else:
                    lines.append(f"  {pname}: {pdesc}")

                # Handle nested properties (e.g., dict params with sub-fields)
                nested_props = pspec.get("properties")
                if isinstance(nested_props, dict):
                    nested_sig = _build_param_signature(pspec)
                    lines[-1] += f" {{{nested_sig}}}"

    # Remove trailing blank line
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def _build_param_signature(params: dict[str, Any]) -> str:
    """Build a Python-like parameter signature from a JSON schema parameters block."""
    props = params.get("properties", {})
    required = set(params.get("required", []))

    if not props:
        return ""

    parts: list[str] = []
    for pname, pspec in props.items():
        if not isinstance(pspec, dict):
            continue
        ptype = _TYPE_SHORT.get(pspec.get("type", ""), pspec.get("type", ""))

        # Inline enum values in type position for compact representation
        enum = pspec.get("enum")
        if enum and len(enum) <= 5:
            ptype = "|".join(str(e) for e in enum)

        if pname in required:
            parts.append(f"{pname}:{ptype}")
        else:
            default = pspec.get("default")
            if default is not None and default != "":
                if isinstance(default, str):
                    parts.append(f"{pname}:{ptype}=\"{default}\"")
                else:
                    parts.append(f"{pname}:{ptype}={json.dumps(default, separators=(',', ':'))}")
            else:
                parts.append(f"{pname}?:{ptype}")

    return ", ".join(parts)


def _description_is_trivial(param_name: str, description: str) -> bool:
    """Check if a parameter description is just a restatement of the parameter name."""
    # Normalize: lowercase, strip, remove punctuation
    name_words = set(param_name.lower().replace("_", " ").replace("-", " ").split())
    desc_lower = description.lower().strip().rstrip(".")

    # Very short descriptions that just restate the name
    if len(desc_lower.split()) <= 4:
        desc_words = set(desc_lower.replace(",", " ").replace(".", " ").split())
        filler = {"the", "a", "an", "of", "for", "to", "in", "is", "that", "this", "be", "as"}
        meaningful_desc = desc_words - filler
        if not meaningful_desc:
            return True
        if len(name_words & meaningful_desc) >= len(meaningful_desc) * 0.5:
            return True

    # If description is mostly param name words plus filler
    desc_words = set(desc_lower.replace(",", " ").replace(".", " ").split())
    filler = {"the", "a", "an", "of", "for", "to", "in", "is", "that", "this", "be", "as",
              "it", "its", "by", "on", "at", "or", "and", "with", "from", "which", "will",
              "should", "can", "used", "value", "specify", "specifies", "specified",
              "parameter", "field", "input", "output", "given", "provided", "set", "sets",
              "whether", "if", "when", "not", "no", "yes", "true", "false", "default"}
    meaningful_desc = desc_words - filler
    if not meaningful_desc:
        return True
    if len(name_words & meaningful_desc) >= len(meaningful_desc) * 0.6:
        return True
    return False


def _shorten_description(desc: str, max_words: int = 20) -> str:
    """Shorten a verbose description while preserving key information.

    Keeps first sentence. Adds format/constraint info if it fits.
    """
    if not desc:
        return desc

    words = desc.split()
    if len(words) <= max_words:
        return desc

    # Split into sentences
    sentences = []
    current = []
    for word in words:
        current.append(word)
        if word.endswith((".", "!", "?")) and len(current) > 2:
            sentences.append(" ".join(current))
            current = []
    if current:
        sentences.append(" ".join(current))

    if not sentences:
        # No sentence boundary found — just truncate
        return " ".join(words[:max_words])

    # Keep first sentence if short enough, otherwise truncate it
    result = sentences[0]
    if len(result.split()) > max_words:
        result = " ".join(result.split()[:max_words])

    # Add constraint/format sentences if they fit
    for s in sentences[1:]:
        s_lower = s.lower()
        has_info = any(kw in s_lower for kw in [
            "format", "e.g.", "eg.", "example", "such as",
            "must be", "cannot", "range", "between",
            "one of", "either", "valid", "enum",
        ])
        if has_info and len(result.split()) + len(s.split()) <= max_words + 8:
            result += " " + s

    return result


def _format_value(val: Any) -> str:
    """Format a value for TOON output."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, int | float):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # Check if this looks like a tool schema parameters block
        compact = _try_compact_params(val)
        if compact is not None:
            return compact
        return json.dumps(val, separators=(",", ":"))
    if isinstance(val, list):
        return json.dumps(val, separators=(",", ":"))
    return str(val)


def _try_compact_params(obj: dict[str, Any]) -> str | None:
    """Try to compact a tool schema parameters object.

    Recognizes the pattern:
      {"type": "...", "properties": {"p1": {"type": ..., "description": ...}, ...}}
    and converts properties to a compact table format.
    """
    props = obj.get("properties")
    if not isinstance(props, dict) or len(props) < 2:
        return None

    # Check that all properties are dicts with at least "type"
    if not all(isinstance(v, dict) and "type" in v for v in props.values()):
        return None

    # Collect all property field names
    prop_fields: list[str] = []
    seen: set[str] = set()
    for spec in props.values():
        for key in spec:
            if key not in seen:
                prop_fields.append(key)
                seen.add(key)

    # Build compact output
    parts: list[str] = []

    # Include non-properties fields (type, required, etc.)
    for k, v in obj.items():
        if k == "properties":
            continue
        if isinstance(v, list | dict):
            parts.append(f"{k}={json.dumps(v, separators=(',', ':'))}")
        else:
            parts.append(f"{k}={v}")

    header = ",".join(parts)

    # Convert properties to table
    rows = [f"[PARAMS: {', '.join(prop_fields)}]"]
    for pname, spec in props.items():
        vals = []
        for f in prop_fields:
            v = spec.get(f, "")
            if isinstance(v, list | dict):
                vals.append(json.dumps(v, separators=(",", ":")))
            elif v is None:
                vals.append("")
            else:
                vals.append(str(v))
        rows.append(f"{pname}: {' | '.join(vals)}")

    return f"{{{header}}}\n" + "\n".join(rows)


def _parse_concatenated_json(text: str) -> list[Any]:
    """Parse text containing multiple concatenated JSON objects/arrays."""
    objects = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        # Skip whitespace
        while idx < len(text) and text[idx] in " \t\n\r":
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            objects.append(obj)
            idx += end_idx
        except json.JSONDecodeError:
            break
    return objects


def _find_json_arrays(text: str) -> list[tuple[int, int]]:
    """Find start/end positions of JSON arrays in text."""
    arrays = []
    i = 0
    while i < len(text):
        if text[i] == "[":
            depth = 0
            in_string = False
            escape = False
            j = i
            while j < len(text):
                c = text[j]
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"' and not escape:
                    in_string = not in_string
                elif not in_string:
                    if c == "[":
                        depth += 1
                    elif c == "]":
                        depth -= 1
                        if depth == 0:
                            arrays.append((i, j + 1))
                            break
                j += 1
        i += 1
    return arrays


def _estimate_token_diff(original: str, compressed: str) -> int:
    """Estimate token savings. Rough heuristic: ~4 chars per token."""
    original_tokens = len(original) // 4
    compressed_tokens = len(compressed) // 4
    return max(0, original_tokens - compressed_tokens)
