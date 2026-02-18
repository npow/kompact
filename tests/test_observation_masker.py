"""Tests for observation masker transform."""

from kompact.config import ObservationMaskerConfig
from kompact.transforms.observation_masker import transform
from kompact.types import ContentBlock, ContentType, Message, Role


def _make_tool_result(text: str, tool_id: str = "") -> Message:
    return Message(
        role=Role.USER,
        content=[ContentBlock(
            type=ContentType.TOOL_RESULT,
            text=text,
            tool_use_id=tool_id or f"tool_{id(text)}",
        )],
    )


def _make_text_message(text: str, role: Role = Role.USER) -> Message:
    return Message(
        role=role,
        content=[ContentBlock(type=ContentType.TEXT, text=text)],
    )


def test_masks_old_outputs():
    messages = [
        _make_tool_result("Old result 1 " * 100, "t1"),
        _make_text_message("Thanks", Role.ASSISTANT),
        _make_tool_result("Old result 2 " * 100, "t2"),
        _make_text_message("Got it", Role.ASSISTANT),
        _make_tool_result("Old result 3 " * 100, "t3"),
        _make_text_message("Processing", Role.ASSISTANT),
        _make_tool_result("Recent result " * 100, "t4"),
    ]
    config = ObservationMaskerConfig(keep_last_n=3)
    result = transform(messages, config)

    assert result.tokens_saved > 0
    # First tool result should be masked
    assert "[Output omitted" in result.messages[0].content[0].text
    # Last 3 should be preserved
    assert "Recent result" in result.messages[6].content[0].text


def test_keeps_all_when_under_threshold():
    messages = [
        _make_tool_result("Result 1", "t1"),
        _make_tool_result("Result 2", "t2"),
    ]
    config = ObservationMaskerConfig(keep_last_n=3)
    result = transform(messages, config)

    assert result.tokens_saved == 0
    assert result.messages[0].content[0].text == "Result 1"
    assert result.messages[1].content[0].text == "Result 2"


def test_user_messages_not_modified():
    messages = [
        _make_text_message("User question"),
        _make_tool_result("Long tool output " * 200, "t1"),
        _make_tool_result("Another output " * 200, "t2"),
        _make_tool_result("Third output " * 200, "t3"),
        _make_tool_result("Fourth output " * 200, "t4"),
    ]
    config = ObservationMaskerConfig(keep_last_n=2)
    result = transform(messages, config)

    # User message must be untouched
    assert result.messages[0].content[0].text == "User question"


def test_summary_included():
    messages = [
        _make_tool_result("Search results for query: python async patterns", "t1"),
        _make_tool_result("Latest result", "t2"),
    ]
    config = ObservationMaskerConfig(keep_last_n=1, include_summary=True)
    result = transform(messages, config)

    masked = result.messages[0].content[0].text
    assert "[Output omitted" in masked
    assert "Search results" in masked


def test_masked_count_in_details():
    messages = [
        _make_tool_result("Old 1", "t1"),
        _make_tool_result("Old 2", "t2"),
        _make_tool_result("Old 3", "t3"),
        _make_tool_result("Recent", "t4"),
    ]
    config = ObservationMaskerConfig(keep_last_n=1)
    result = transform(messages, config)

    assert result.details["masked_count"] == 3
