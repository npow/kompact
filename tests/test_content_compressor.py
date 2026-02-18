"""Tests for extractive content compressor transform."""

from kompact.config import ContentCompressorConfig
from kompact.transforms.content_compressor import transform
from kompact.types import ContentBlock, ContentType, Message, Role


def _make_long_tool_result(n_lines: int = 50) -> str:
    """Generate a long text block for compression testing."""
    lines = []
    for i in range(n_lines):
        lines.append(
            f"Line {i}: This is a verbose log entry with various details about "
            f"request processing, including timestamps and status codes."
        )
    # Insert a critical line
    lines[25] = "ERROR: Database connection failed at 2024-01-15 with timeout after 5000ms"
    return "\n".join(lines)


def test_compresses_long_tool_results():
    long_text = _make_long_tool_result(80)
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="What errors occurred?"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=long_text,
                tool_use_id="t1",
            ),
        ]),
    ]
    config = ContentCompressorConfig(
        enabled=True,
        target_ratio=0.3,
        min_tokens_to_compress=50,
    )
    result = transform(messages, config)

    assert result.tokens_saved > 0
    compressed_text = result.messages[1].content[0].text
    assert len(compressed_text) < len(long_text)
    # Error line should be preserved (structural importance)
    assert "ERROR" in compressed_text


def test_protects_recent_user_messages():
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TEXT,
                text="This is a long user message with lots of context. " * 30,
            ),
        ]),
    ]
    config = ContentCompressorConfig(
        enabled=True,
        target_ratio=0.3,
        min_tokens_to_compress=50,
        protect_recent_user_messages=1,
    )
    result = transform(messages, config)

    # Last user message should be protected
    assert result.tokens_saved == 0


def test_protects_code_blocks():
    text_with_code = (
        "Here is some context.\n\n"
        "```python\ndef hello():\n    print('world')\n```\n\n"
        "And more verbose text that could be compressed. " * 20
    )
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=text_with_code,
                tool_use_id="t1",
            ),
        ]),
    ]
    config = ContentCompressorConfig(
        enabled=True,
        target_ratio=0.3,
        min_tokens_to_compress=50,
        protect_code_blocks=True,
    )
    result = transform(messages, config)

    compressed = result.messages[0].content[0].text
    assert "def hello():" in compressed


def test_skips_short_content():
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text="Short result",
                tool_use_id="t1",
            ),
        ]),
    ]
    config = ContentCompressorConfig(
        min_tokens_to_compress=200,
    )
    result = transform(messages, config)

    assert result.tokens_saved == 0
    assert result.messages[0].content[0].text == "Short result"


def test_preserves_headings():
    text = (
        "# Important Section\n\n" + "Filler text. " * 50
        + "\n\n## Another Section\n\n" + "More filler. " * 50
    )
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=text,
                tool_use_id="t1",
            ),
        ]),
    ]
    config = ContentCompressorConfig(
        target_ratio=0.3,
        min_tokens_to_compress=50,
    )
    result = transform(messages, config)

    compressed = result.messages[0].content[0].text
    assert "# Important Section" in compressed
    assert "## Another Section" in compressed
