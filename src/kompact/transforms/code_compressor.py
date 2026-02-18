"""Code compressor transform.

AST-aware compression that extracts code skeletons: signatures, imports,
type annotations, and docstrings while dropping function bodies.

Typical savings: ~70% on Python code content.

Uses regex-based extraction by default (no tree-sitter dependency).
Falls back gracefully for non-Python code.
"""

from __future__ import annotations

import re

from kompact.config import CodeCompressorConfig
from kompact.types import ContentBlock, ContentType, Message, TransformResult

# Patterns for detecting code blocks in text
CODE_FENCE_PATTERN = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

# Python-specific patterns
IMPORT_PATTERN = re.compile(r"^(import .+|from .+ import .+)$", re.MULTILINE)
CLASS_PATTERN = re.compile(r"^(class \w+.*?:)", re.MULTILINE)
FUNC_PATTERN = re.compile(r"^( *def \w+\(.*?\)(?:\s*->.*?)?:)", re.MULTILINE | re.DOTALL)
DECORATOR_PATTERN = re.compile(r"^( *@\w+.*?)$", re.MULTILINE)
DOCSTRING_PATTERN = re.compile(r'(""".*?"""|\'\'\'.*?\'\'\')', re.DOTALL)
TYPE_ALIAS_PATTERN = re.compile(
    r"^(\w+\s*(?::.*?)?=\s*(?:TypeVar|TypeAlias|Union|Optional).*?)$", re.MULTILINE
)


def transform(
    messages: list[Message],
    config: CodeCompressorConfig | None = None,
) -> TransformResult:
    """Compress code content in tool results."""
    if config is None:
        config = CodeCompressorConfig()

    tokens_saved = 0
    new_messages = []

    for msg in messages:
        new_blocks = []
        for block in msg.content:
            if block.type in (ContentType.TOOL_RESULT, ContentType.TEXT) and block.text:
                new_text, saved = _compress_code_in_text(block.text, config)
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
        transform_name="code_compressor",
    )


def _compress_code_in_text(text: str, config: CodeCompressorConfig) -> tuple[str, int]:
    """Find code blocks and compress them."""
    total_saved = 0

    # Handle fenced code blocks
    def replace_fence(match: re.Match) -> str:
        nonlocal total_saved
        lang = match.group(1).lower()
        code = match.group(2)

        if lang in ("python", "py", ""):
            compressed = compress_python(code, config)
            if compressed != code:
                saved = max(0, len(code) // 4 - len(compressed) // 4)
                total_saved += saved
                return f"```{lang}\n{compressed}```"
        return match.group(0)

    result = CODE_FENCE_PATTERN.sub(replace_fence, text)

    # If no fenced blocks, check if the whole text looks like Python code
    if total_saved == 0 and _looks_like_python(text):
        compressed = compress_python(text, config)
        if compressed != text:
            total_saved = max(0, len(text) // 4 - len(compressed) // 4)
            result = compressed

    return result, total_saved


def compress_python(code: str, config: CodeCompressorConfig) -> str:
    """Compress Python code to a skeleton."""
    lines = code.split("\n")
    output_lines: list[str] = []
    in_function_body = False
    function_indent = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        indent = len(line) - len(line.lstrip()) if stripped else 0

        # Always keep imports
        if config.keep_imports and IMPORT_PATTERN.match(stripped):
            in_function_body = False
            output_lines.append(stripped)
            i += 1
            continue

        # Always keep decorators
        if DECORATOR_PATTERN.match(stripped):
            if not in_function_body or indent <= function_indent:
                in_function_body = False
                output_lines.append(stripped)
                i += 1
                continue

        # Keep class definitions
        if CLASS_PATTERN.match(stripped):
            in_function_body = False
            output_lines.append(stripped)
            i += 1
            continue

        # Keep function signatures
        if re.match(r" *def \w+", stripped):
            # Collect full signature (may span multiple lines)
            sig_lines = [stripped]
            while not stripped.endswith(":") and i + 1 < len(lines):
                i += 1
                stripped = lines[i].rstrip()
                sig_lines.append(stripped)

            if config.keep_signatures:
                output_lines.extend(sig_lines)

            function_indent = indent
            in_function_body = True
            i += 1

            # Check for docstring on next line
            if config.keep_docstrings and i < len(lines):
                next_stripped = lines[i].strip()
                if next_stripped.startswith('"""') or next_stripped.startswith("'''"):
                    quote = next_stripped[:3]
                    if next_stripped.endswith(quote) and len(next_stripped) > 6:
                        output_lines.append(lines[i].rstrip())
                        i += 1
                    else:
                        while i < len(lines):
                            output_lines.append(lines[i].rstrip())
                            if lines[i].strip().endswith(quote):
                                i += 1
                                break
                            i += 1

            # Add body placeholder
            body_indent = " " * (function_indent + 4)
            output_lines.append(f"{body_indent}...")
            continue

        # Skip function bodies
        if in_function_body and indent > function_indent:
            i += 1
            continue

        if in_function_body and indent <= function_indent and stripped:
            in_function_body = False

        # Keep type aliases and module-level assignments
        if not in_function_body and stripped:
            if TYPE_ALIAS_PATTERN.match(stripped):
                output_lines.append(stripped)
            elif indent == 0 and stripped and not stripped.startswith("#"):
                output_lines.append(stripped)

        i += 1

    return "\n".join(output_lines)


def _looks_like_python(text: str) -> bool:
    """Heuristic: does this text look like Python source code?"""
    indicators = 0
    if "import " in text:
        indicators += 1
    if "def " in text:
        indicators += 1
    if "class " in text:
        indicators += 1
    if "self." in text:
        indicators += 1
    if text.strip().startswith("#!") and "python" in text.split("\n")[0]:
        indicators += 2
    return indicators >= 2
